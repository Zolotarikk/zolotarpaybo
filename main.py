import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
import database
from handlers import admin, admin_blocks, booking, common, fallback, my_bookings


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Проверь файл .env")
    logging.basicConfig(level=logging.INFO)
    await database.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    # Порядок важен: fallback должен идти последним
    dp.include_routers(
        common.router,
        booking.router,
        my_bookings.router,
        admin.router,
        admin_blocks.router,
        fallback.router,
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")