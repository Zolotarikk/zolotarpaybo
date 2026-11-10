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