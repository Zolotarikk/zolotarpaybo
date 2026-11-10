from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def fallback(message: Message):
    await message.answer("Не понял. Воспользуйтесь меню или нажмите /start.")