from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

import config
import database
from keyboards import main_menu_for

router = Router()

# После первой отправки Telegram запоминает фото: дальше передаём только его
# идентификатор, и приветствие появляется мгновенно
_photo_file_id: str | None = None


@router.message(CommandStart())
async def cmd_start(message: Message):
    global _photo_file_id
    user = message.from_user
    await database.add_user(user.id, user.full_name, user.username)
    text = (
        f"Здравствуйте, <b>{escape(user.full_name)}</b>! 👋\n\n"
        f"Это бот онлайн-записи: <b>{escape(config.STUDIO_NAME)}</b>.\n"
        "Выберите услугу, удобное время и запишитесь за минуту. "
        "Всё остальное в меню ниже."
    )
    keyboard = main_menu_for(user.id)
    photo = config.WELCOME_PHOTO
    if photo and photo.exists():
        sent = await message.answer_photo(
            _photo_file_id or FSInputFile(photo),
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        if sent.photo:
            _photo_file_id = sent.photo[-1].file_id
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(F.text == "📖 О нас")
async def about(message: Message):
    await message.answer(
        f"<b>{escape(config.STUDIO_NAME)}</b>\n\n{escape(config.STUDIO_ABOUT)}",
        parse_mode="HTML",
    )


@router.message(F.text == "📞 Контакты")
async def contacts(message: Message):
    if config.STUDIO_LATITUDE is not None and config.STUDIO_LONGITUDE is not None:
        # Карточка с картой: по нажатию открывается навигатор
        await message.answer_venue(
            latitude=config.STUDIO_LATITUDE,
            longitude=config.STUDIO_LONGITUDE,
            title=config.STUDIO_NAME,
            address=config.STUDIO_ADDRESS,
        )
        await message.answer(f"📞 {config.STUDIO_PHONE}\n🕒 {config.STUDIO_HOURS}")
    else:
        await message.answer(
            f"📍 {config.STUDIO_ADDRESS}\n"
            f"📞 {config.STUDIO_PHONE}\n"
            f"🕒 {config.STUDIO_HOURS}"
        )