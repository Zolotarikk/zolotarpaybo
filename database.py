from pathlib import Path

import aiosqlite

# Файл базы лежит рядом с кодом
DB_PATH = Path(__file__).parent / "bot.db"


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
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
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


async def add_order(user_id: int, item_id: int) -> int:
    """Создаёт заказ и возвращает его номер."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, item_id) VALUES (?, ?)",
            (user_id, item_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_orders(user_id: int):
    """Возвращает последние 10 заказов пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, item_id, created_at FROM orders "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        )
        return await cursor.fetchall()