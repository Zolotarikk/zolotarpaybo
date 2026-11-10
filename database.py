from datetime import date, datetime
from pathlib import Path

import aiosqlite

# Файл базы лежит рядом с кодом
DB_PATH = Path(__file__).parent / "bot.db"

# Формат времени, в котором храним записи в базе
DT_FORMAT = "%Y-%m-%d %H:%M"

# Демо-услуги: (название, длительность в минутах, цена в BYN)
DEFAULT_SERVICES = [
    ("Классический массаж", 60, 50),
    ("Массаж спины", 30, 30),
    ("Расслабляющий массаж", 90, 70),
]


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
        # Если услуг ещё нет, заполняем демо-списком
        cursor = await db.execute("SELECT COUNT(*) FROM services")
        (count,) = await cursor.fetchone()
        if count == 0:
            await db.executemany(
                "INSERT INTO services (name, duration_min, price) "
                "VALUES (?, ?, ?)",
                DEFAULT_SERVICES,
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
    """Занятое время на выбранный день: список (начало, конец)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT start_at, end_at FROM bookings "
            "WHERE status = 'active' AND start_at LIKE ?",
            (f"{day.isoformat()}%",),
        )
        rows = await cursor.fetchall()
    return [
        (datetime.strptime(start, DT_FORMAT), datetime.strptime(end, DT_FORMAT))
        for start, end in rows
    ]

async def create_booking(
    user_id: int, service_id: int, start: datetime, end: datetime
) -> int | None:
    """Создаёт запись, если время свободно. Возвращает номер записи или None."""
    start_s = start.strftime(DT_FORMAT)
    end_s = end.strftime(DT_FORMAT)
    async with aiosqlite.connect(DB_PATH) as db:
        # Блокируем базу на запись, пока проверяем и сохраняем
        await db.execute("BEGIN IMMEDIATE")
        # Пересечение: существующая запись начинается раньше нашего конца
        # и заканчивается позже нашего начала
        cursor = await db.execute(
            "SELECT 1 FROM bookings "
            "WHERE status = 'active' AND start_at < ? AND end_at > ? LIMIT 1",
            (end_s, start_s),
        )
        if await cursor.fetchone():
            await db.rollback()
            return None
        cursor = await db.execute(
            "INSERT INTO bookings (user_id, service_id, start_at, end_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, service_id, start_s, end_s),
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
        (
            booking_id,
            name,
            datetime.strptime(start, DT_FORMAT),
            datetime.strptime(end, DT_FORMAT),
        )
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
    return (
        bid,
        user_id,
        name,
        price,
        datetime.strptime(start, DT_FORMAT),
        datetime.strptime(end, DT_FORMAT),
        status,
    )

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
        (
            booking_id,
            full_name,
            username,
            service,
            datetime.strptime(start, DT_FORMAT),
            datetime.strptime(end, DT_FORMAT),
        )
        for booking_id, full_name, username, service, start, end in rows
    ]