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

# Читаем токен из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()

# Главное меню: кнопки под полем ввода
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 О нас"), KeyboardButton(text="📞 Контакты")],
        [KeyboardButton(text="🛒 Каталог")],
    ],
    resize_keyboard=True,  # делает кнопки компактными
)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Срабатывает на /start и показывает меню"""
    name = message.from_user.full_name
    await message.answer(
        f"Привет, {name}! Выбери раздел в меню ниже.",
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
    # Inline-кнопки под сообщением
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Товар 1", callback_data="item_1")],
            [InlineKeyboardButton(text="Товар 2", callback_data="item_2")],
        ]
    )
    await message.answer("Выбери товар:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("item_"))
async def item_chosen(callback: CallbackQuery):
    """Срабатывает при нажатии на inline-кнопку товара"""
    item_id = callback.data.split("_")[1]
    await callback.message.answer(
        f"Ты выбрал товар №{item_id}. Скоро здесь будет оформление заказа."
    )
    await callback.answer()  # убирает «часики» на кнопке


@dp.message()
async def echo(message: Message):
    """Ответ на всё остальное. Должен стоять последним."""
    await message.answer("Не понял. Воспользуйся меню или нажми /start.")


async def main():
    if not TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Проверь файл .env")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())