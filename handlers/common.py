from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import config
import database
from keyboards import main_menu_for

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await database.add_user(user.id, user.full_name, user.username)
    await message.answer(
        f"Здравствуйте, {user.full_name}! 👋\n\n"
        f"Это бот онлайн-записи: {config.STUDIO_NAME}.\n"
        "Выберите услугу, удобное время и запишитесь за минуту. "
        "Всё остальное в меню ниже.",
        reply_markup=main_menu_for(user.id),
    )


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(F.text == "📖 О нас")
async def about(message: Message):
    await message.answer(f"{config.STUDIO_NAME}\n\n{config.STUDIO_ABOUT}")


@router.message(F.text == "📞 Контакты")
async def contacts(message: Message):
    await message.answer(
        f"📍 {config.STUDIO_ADDRESS}\n"
        f"📞 {config.STUDIO_PHONE}\n"
        f"🕒 {config.STUDIO_HOURS}"
    )