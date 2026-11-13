from datetime import date, datetime, timedelta

import aiosqlite

import config

# Файл базы лежит рядом с кодом
# У каждого клиента своя база в его папке: clients/<имя>/bot.db
DB_PATH = config.CLIENT_DIR / "bot.db"

# Формат времени, в котором храним записи в базе
DT_FORMAT = "%Y-%m-%d %H:%M"

# Колонки-отметки «напоминание отправлено» (название берём из этого списка)
REMINDER_COLUMNS = {"24h": "reminded_24h", "2h": "reminded_2h"}

def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, DT_FORMAT)


async def init_db():
    """Создаёт таблицы, если их ещё нет. Вызывается при запуске бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                duration_min INTEGER NOT NULL,
                price INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
                # Миграция: добавляем колонки напоминаний в таблицу bookings, если их нет
        cursor = await db.execute("PRAGMA table_info(bookings)")
        existing_columns = {row[1] for row in await cursor.fetchall()}
        for column in REMINDER_COLUMNS.values():
            if column not in existing_columns:
                await db.execute(
                    f"ALTER TABLE bookings "
                    f"ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
        
        await db.commit()


async def add_user(user_id: int, full_name: str, username: str | None):
    """Сохраняет пользователя. Если он уже есть, ничего не меняет."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username) "
            "VALUES (?, ?, ?)",
            (user_id, full_name, username),
        )
        await db.commit()


async def get_services():
    """Возвращает активные услуги: (id, название, длительность, цена)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, duration_min, price FROM services "
            "WHERE is_active = 1 ORDER BY id"
        )
        return await cursor.fetchall()


async def get_service(service_id: int):
    """Возвращает одну услугу или None, если её нет или она скрыта."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, duration_min, price FROM services "
            "WHERE id = ? AND is_active = 1",
            (service_id,),
        )
        return await cursor.fetchone()


async def get_busy_intervals(day: date) -> list[tuple[datetime, datetime]]:
    """Занятое время на день: активные записи и закрытое владельцем время."""
    pattern = f"{day.isoformat()}%"
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT start_at, end_at FROM bookings "
            "WHERE status = 'active' AND start_at LIKE ? "
            "UNION ALL "
            "SELECT start_at, end_at FROM blocks WHERE start_at LIKE ?",
            (pattern, pattern),
        )
        rows = await cursor.fetchall()
    return [(parse_dt(start), parse_dt(end)) for start, end in rows]


async def create_booking(
    user_id: int, service_id: int, start: datetime, end: datetime, now: datetime
) -> int | None:
    """Создаёт запись, если время свободно. Возвращает номер записи или None."""
    start_s = start.strftime(DT_FORMAT)
    end_s = end.strftime(DT_FORMAT)
    # Если до записи осталось меньше срока напоминания, оно уже не нужно
    until_start = start - now
    skip_first = int(until_start <= timedelta(hours=config.REMIND_FIRST_HOURS))
    skip_second = int(until_start <= timedelta(hours=config.REMIND_SECOND_HOURS))
    async with aiosqlite.connect(DB_PATH) as db:
        # Блокируем базу на запись, пока проверяем и сохраняем
        await db.execute("BEGIN IMMEDIATE")
        # Пересечение: существующая запись или блок начинается раньше нашего
        # конца и заканчивается позже нашего начала
        cursor = await db.execute(
            "SELECT 1 FROM bookings "
            "WHERE status = 'active' AND start_at < ? AND end_at > ? "
            "UNION ALL "
            "SELECT 1 FROM blocks WHERE start_at < ? AND end_at > ? LIMIT 1",
            (end_s, start_s, end_s, start_s),
        )
        if await cursor.fetchone():
            await db.rollback()
            return None
        cursor = await db.execute(
            "INSERT INTO bookings "
            "(user_id, service_id, start_at, end_at, reminded_24h, reminded_2h) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, service_id, start_s, end_s, skip_first, skip_second),
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_bookings(user_id: int, now: datetime):
    """Предстоящие активные записи клиента: (id, услуга, начало, конец)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT b.id, s.name, b.start_at, b.end_at "
            "FROM bookings b JOIN services s ON s.id = b.service_id "
            "WHERE b.user_id = ? AND b.status = 'active' AND b.start_at >= ? "
            "ORDER BY b.start_at LIMIT 10",
            (user_id, now.strftime(DT_FORMAT)),
        )
        rows = await cursor.fetchall()
    return [
        (booking_id, name, parse_dt(start), parse_dt(end))
        for booking_id, name, start, end in rows
    ]


async def get_booking(booking_id: int):
    """Одна запись: (id, user_id, услуга, цена, начало, конец, статус) или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT b.id, b.user_id, s.name, s.price, b.start_at, b.end_at, b.status "
            "FROM bookings b JOIN services s ON s.id = b.service_id "
            "WHERE b.id = ?",
            (booking_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    bid, user_id, name, price, start, end, status = row
    return (bid, user_id, name, price, parse_dt(start), parse_dt(end), status)


async def cancel_booking(booking_id: int, user_id: int) -> bool:
    """Отменяет запись клиента. Возвращает True, если отмена выполнена."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE bookings SET status = 'cancelled' "
            "WHERE id = ? AND user_id = ? AND status = 'active'",
            (booking_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_day_bookings(day: date):
    """Активные записи на день: (id, клиент, username, услуга, начало, конец)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT b.id, u.full_name, u.username, s.name, b.start_at, b.end_at "
            "FROM bookings b "
            "JOIN services s ON s.id = b.service_id "
            "LEFT JOIN users u ON u.user_id = b.user_id "
            "WHERE b.status = 'active' AND b.start_at LIKE ? "
            "ORDER BY b.start_at",
            (f"{day.isoformat()}%",),
        )
        rows = await cursor.fetchall()
    return [
        (booking_id, full_name, username, service, parse_dt(start), parse_dt(end))
        for booking_id, full_name, username, service, start, end in rows
    ]


async def create_block(start: datetime, end: datetime):
    """Закрывает время. Возвращает (id блока, []) или (None, [номера записей])."""
    start_s = start.strftime(DT_FORMAT)
    end_s = end.strftime(DT_FORMAT)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        # Нельзя закрыть время, в котором уже есть записи клиентов
        cursor = await db.execute(
            "SELECT id FROM bookings "
            "WHERE status = 'active' AND start_at < ? AND end_at > ?",
            (end_s, start_s),
        )
        conflicts = [row[0] for row in await cursor.fetchall()]
        if conflicts:
            await db.rollback()
            return None, conflicts
        cursor = await db.execute(
            "INSERT INTO blocks (start_at, end_at) VALUES (?, ?)",
            (start_s, end_s),
        )
        await db.commit()
        return cursor.lastrowid, []


async def get_day_blocks(day: date):
    """Закрытое время на день: (id, начало, конец)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, start_at, end_at FROM blocks "
            "WHERE start_at LIKE ? ORDER BY start_at",
            (f"{day.isoformat()}%",),
        )
        rows = await cursor.fetchall()
    return [(block_id, parse_dt(start), parse_dt(end)) for block_id, start, end in rows]


async def get_future_blocks(now: datetime):
    """Будущее закрытое время: (id, начало, конец), не более 20 штук."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, start_at, end_at FROM blocks "
            "WHERE end_at > ? ORDER BY start_at LIMIT 20",
            (now.strftime(DT_FORMAT),),
        )
        rows = await cursor.fetchall()
    return [(block_id, parse_dt(start), parse_dt(end)) for block_id, start, end in rows]


async def delete_block(block_id: int) -> bool:
    """Открывает время обратно. Возвращает True, если блок был удалён."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
        await db.commit()
        return cursor.rowcount > 0
    
async def get_due_reminders(now: datetime, kind: str, hours: int):
    """Записи, которым пора отправить напоминание.

    Возвращает (id, user_id, услуга, начало, конец).
    """
    # Название колонки в запрос через ? подставить нельзя, поэтому берём
    # его из заранее заданного словаря
    column = REMINDER_COLUMNS[kind]
    until = now + timedelta(hours=hours)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT b.id, b.user_id, s.name, b.start_at, b.end_at "
            "FROM bookings b JOIN services s ON s.id = b.service_id "
            f"WHERE b.status = 'active' AND b.{column} = 0 "
            "AND b.start_at > ? AND b.start_at <= ? "
            "ORDER BY b.start_at",
            (now.strftime(DT_FORMAT), until.strftime(DT_FORMAT)),
        )
        rows = await cursor.fetchall()
    return [
        (booking_id, user_id, name, parse_dt(start), parse_dt(end))
        for booking_id, user_id, name, start, end in rows
    ]


async def mark_reminded(booking_id: int, kind: str):
    """Отмечает, что напоминание по записи отправлено."""
    column = REMINDER_COLUMNS[kind]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE bookings SET {column} = 1 WHERE id = ?", (booking_id,)
        )
        await db.commit()
        
async def sync_services(services: list[dict]):
    """Приводит услуги в базе в соответствие со списком из settings.toml."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, name FROM services")
        existing = {name: service_id for service_id, name in await cursor.fetchall()}
        names_in_settings = set()
        for item in services:
            name = item["name"]
            names_in_settings.add(name)
            if name in existing:
                # Услуга уже есть: обновляем длительность и цену, включаем
                await db.execute(
                    "UPDATE services SET duration_min = ?, price = ?, is_active = 1 "
                    "WHERE id = ?",
                    (item["duration_min"], item["price"], existing[name]),
                )
            else:
                await db.execute(
                    "INSERT INTO services (name, duration_min, price) VALUES (?, ?, ?)",
                    (name, item["duration_min"], item["price"]),
                )
        # Услуги, которых больше нет в настройках, скрываем, а не удаляем:
        # старые записи клиентов продолжают на них ссылаться
        for name, service_id in existing.items():
            if name not in names_in_settings:
                await db.execute(
                    "UPDATE services SET is_active = 0 WHERE id = ?", (service_id,)
                )
        await db.commit()