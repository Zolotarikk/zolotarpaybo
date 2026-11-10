import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

import database

# Читаем токен из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()

# Главное меню: кнопки под полем ввода
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 О нас"), KeyboardButton(text="📞 Контакты")],
        [KeyboardButton(text="🛒 Каталог"), KeyboardButton(text="📦 Мои заказы")],
    ],
    resize_keyboard=True,
)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Срабатывает на /start: запоминает пользователя и показывает меню"""
    user = message.from_user
    await database.add_user(user.id, user.full_name, user.username)
    await message.answer(
        f"Привет, {user.full_name}! Выбери раздел в меню ниже.",
        reply_markup=main_menu,
    )


@dp.message(F.text == "📖 О нас")
async def about(message: Message):
    await message.answer("Мы тестовый магазин. Здесь будет описание бизнеса.")


@dp.message(F.text == "📞 Контакты")
async def contacts(message: Message):
    await message.answer("Телефон: +000 00 000 00 00\nАдрес: тестовая улица, 1")


@dp.message(F.text == "🛒 Каталог")
async def catalog(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Товар 1", callback_data="item_1")],
            [InlineKeyboardButton(text="Товар 2", callback_data="item_2")],
        ]
    )
    await message.answer("Выбери товар:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("item_"))
async def item_chosen(callback: CallbackQuery):
    """Нажатие на товар: создаём заказ в базе"""
    item_id = int(callback.data.split("_")[1])
    order_id = await database.add_order(callback.from_user.id, item_id)
    await callback.message.answer(
        f"Заказ №{order_id} создан: товар №{item_id}."
    )
    await callback.answer()  # убирает «часики» на кнопке


@dp.message(F.text == "📦 Мои заказы")
async def my_orders(message: Message):
    """Показывает последние заказы пользователя"""
    orders = await database.get_orders(message.from_user.id)
    if not orders:
        await message.answer("У тебя пока нет заказов.")
        return
    lines = [
        f"Заказ №{order_id}: товар №{item_id} ({created_at} UTC)"
        for order_id, item_id, created_at in orders
    ]
    await message.answer("Твои последние заказы:\n" + "\n".join(lines))


@dp.message()
async def echo(message: Message):
    """Ответ на всё остальное. Должен стоять последним."""
    await message.answer("Не понял. Воспользуйся меню или нажми /start.")


async def main():
    if not TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Проверь файл .env")
    logging.basicConfig(level=logging.INFO)
    await database.init_db()  # создаём таблицы при запуске
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())