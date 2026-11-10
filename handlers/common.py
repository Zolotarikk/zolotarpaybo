from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import database
from keyboards import main_menu_for

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await database.add_user(user.id, user.full_name, user.username)
    await message.answer(
        f"Здравствуйте, {user.full_name}! Это студия массажа «Релакс». "
        "Выберите раздел в меню ниже.",
           reply_markup=main_menu_for(user.id),
    )


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(F.text == "📖 О нас")
async def about(message: Message):
    await message.answer(
        "Студия массажа «Релакс». Работаем с 2020 года. "
        "Здесь будет описание студии."
    )


@router.message(F.text == "📞 Контакты")
async def contacts(message: Message):
    await message.answer(
        "Телефон: +375 00 000 00 00\n"
        "Адрес: г. Минск, тестовая улица, 1\n"
        "Работаем: пн–сб, 10:00–20:00"
    )