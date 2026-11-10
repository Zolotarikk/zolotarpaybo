from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.text.in_({"💆 Записаться", "📋 Мои записи", "💰 Услуги и цены"}))
async def coming_soon(message: Message):
    await message.answer("Этот раздел скоро появится.")