import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

# Читаем токен из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Диспетчер получает сообщения и передаёт их нужным функциям
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Срабатывает, когда пользователь нажимает /start"""
    name = message.from_user.full_name
    await message.answer(f"Привет, {name}! Я работаю.")


@dp.message()
async def echo(message: Message):
    """Отвечает на любое другое сообщение"""
    if message.text:
        await message.answer(f"Ты написал: {message.text}")
    else:
        await message.answer("Пока я понимаю только текст.")


async def main():
    if not TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Проверь файл .env")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())