from aiogram import F, Router
from aiogram.types import Message

import database

router = Router()


@router.message(F.text == "💰 Услуги и цены")
async def show_services(message: Message):
    services = await database.get_services()
    if not services:
        await message.answer("Список услуг пока пуст.")
        return
    lines = [
        f"• {name} — {duration} мин — {price} BYN"
        for _, name, duration, price in services
    ]
    await message.answer("Наши услуги:\n\n" + "\n".join(lines))


@router.message(F.text.in_({"💆 Записаться", "📋 Мои записи"}))
async def coming_soon(message: Message):
    await message.answer("Этот раздел скоро появится.")