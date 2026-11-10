from datetime import date, datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database
import timetable

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"


def chunk(buttons: list, size: int) -> list[list]:
    """Разбивает список кнопок на ряды по size штук."""
    return [buttons[i : i + size] for i in range(0, len(buttons), size)]


def services_keyboard(services) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{name} — {duration} мин — {price} BYN",
                callback_data=f"svc:{service_id}",
            )
        ]
        for service_id, name, duration, price in services
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dates_keyboard(service_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{WEEKDAYS[day.weekday()]} {day.strftime('%d.%m')}",
            callback_data=f"date:{service_id}:{day.isoformat()}",
        )
        for day in timetable.available_dates()
    ]
    back = [InlineKeyboardButton(text="⬅ Назад", callback_data="back:services")]
    return InlineKeyboardMarkup(inline_keyboard=chunk(buttons, 3) + [back])


def slots_keyboard(service_id: int, day: date, slots: list[datetime]):
    buttons = [
        InlineKeyboardButton(
            text=slot.strftime("%H:%M"),
            callback_data=f"slot:{service_id}:{day.isoformat()}:{slot:%H%M}",
        )
        for slot in slots
    ]
    # «Назад» возвращает к выбору даты для этой же услуги
    back = [InlineKeyboardButton(text="⬅ Назад", callback_data=f"svc:{service_id}")]
    return InlineKeyboardMarkup(inline_keyboard=chunk(buttons, 4) + [back])


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


@router.message(F.text == "💆 Записаться")
async def start_booking(message: Message):
    services = await database.get_services()
    if not services:
        await message.answer("Список услуг пока пуст.")
        return
    await message.answer("Выберите услугу:", reply_markup=services_keyboard(services))


@router.callback_query(F.data == "back:services")
async def back_to_services(callback: CallbackQuery):
    services = await database.get_services()
    await callback.message.edit_text(
        "Выберите услугу:", reply_markup=services_keyboard(services)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc:"))
async def choose_service(callback: CallbackQuery):
    service_id = int(callback.data.split(":")[1])
    service = await database.get_service(service_id)
    if service is None:
        await callback.answer("Эта услуга недоступна", show_alert=True)
        return
    _, name, duration, price = service
    await callback.message.edit_text(
        f"Услуга: {name} ({duration} мин, {price} BYN)\n\nВыберите дату:",
        reply_markup=dates_keyboard(service_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery):
    _, service_id, day_str = callback.data.split(":")
    service_id = int(service_id)
    day = date.fromisoformat(day_str)
    service = await database.get_service(service_id)
    if service is None:
        await callback.answer("Эта услуга недоступна", show_alert=True)
        return
    _, name, duration, _price = service

    busy = await database.get_busy_intervals(day)
    slots = timetable.free_slots(day, duration, busy)

    header = f"Услуга: {name}\nДата: {format_day(day)}\n\n"
    if not slots:
        await callback.message.edit_text(
            header + "На эту дату свободного времени нет. Выберите другую дату:",
            reply_markup=dates_keyboard(service_id),
        )
    else:
        await callback.message.edit_text(
            header + "Выберите время:",
            reply_markup=slots_keyboard(service_id, day, slots),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("slot:"))
async def choose_slot(callback: CallbackQuery):
    _, service_id, day_str, hhmm = callback.data.split(":")
    service = await database.get_service(int(service_id))
    if service is None:
        await callback.answer("Эта услуга недоступна", show_alert=True)
        return
    _, name, duration, price = service
    start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")

    await callback.message.edit_text(
        "Вы выбрали:\n"
        f"💆 {name} ({duration} мин, {price} BYN)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start.strftime('%H:%M')}\n\n"
        "Подтверждение записи добавим на следующем шаге."
    )
    await callback.answer()


@router.message(F.text == "📋 Мои записи")
async def coming_soon(message: Message):
    await message.answer("Этот раздел скоро появится.")