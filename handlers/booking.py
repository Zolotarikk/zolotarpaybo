import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database
import timetable

router = Router()
logger = logging.getLogger(__name__)

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


def confirm_keyboard(service_id: int, day: date, hhmm: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"confirm:{service_id}:{day.isoformat()}:{hhmm}",
            )
        ],
        # «Назад» возвращает к выбору времени на этот же день
        [
            InlineKeyboardButton(
                text="⬅ Назад",
                callback_data=f"date:{service_id}:{day.isoformat()}",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_slot_taken(callback: CallbackQuery, service_id: int):
    """Сообщает, что выбранное время уже недоступно, и предлагает другую дату."""
    await callback.message.edit_text(
        "К сожалению, это время уже занято. Выберите другую дату:",
        reply_markup=dates_keyboard(service_id),
    )
    await callback.answer()


async def notify_admin(bot, user, booking_id, name, price, start, end):
    """Отправляет владельцу студии уведомление о новой записи."""
    if not config.ADMIN_ID:
        logger.warning("ADMIN_ID не задан, уведомление не отправлено")
        return
    username = f" (@{user.username})" if user.username else ""
    text = (
        f"🔔 Новая запись №{booking_id}\n\n"
        f"👤 {user.full_name}{username}\n"
        f"💆 {name}, {price} BYN\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}"
    )
    try:
        await bot.send_message(config.ADMIN_ID, text)
    except Exception:
        # Запись уже сохранена, сбой уведомления не должен её ломать
        logger.exception("Не удалось отправить уведомление администратору")


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
    service_id = int(service_id)
    service = await database.get_service(service_id)
    if service is None:
        await callback.answer("Эта услуга недоступна", show_alert=True)
        return
    _, name, duration, price = service
    start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")
    end = start + timedelta(minutes=duration)

    await callback.message.edit_text(
        "Проверьте данные записи:\n\n"
        f"💆 {name} ({duration} мин)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        f"💰 {price} BYN",
        reply_markup=confirm_keyboard(service_id, start.date(), hhmm),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def confirm_booking(callback: CallbackQuery):
    _, service_id, day_str, hhmm = callback.data.split(":")
    service_id = int(service_id)
    service = await database.get_service(service_id)
    if service is None:
        await callback.answer("Эта услуга недоступна", show_alert=True)
        return
    _, name, duration, price = service
    start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")
    end = start + timedelta(minutes=duration)

    # Защита 1: время всё ещё допустимо (не прошло, в рабочие часы, не занято)
    busy = await database.get_busy_intervals(start.date())
    if start not in timetable.free_slots(start.date(), duration, busy):
        await show_slot_taken(callback, service_id)
        return

    # Защита 2: проверка и сохранение в одной транзакции
    booking_id = await database.create_booking(
    callback.from_user.id, service_id, start, end, timetable.now_local()
    )
    if booking_id is None:
        await show_slot_taken(callback, service_id)
        return

    await callback.message.edit_text(
        f"✅ Вы записаны! Запись №{booking_id}\n\n"
        f"💆 {name} ({duration} мин)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        f"💰 {price} BYN\n"
        f"📍 {config.STUDIO_ADDRESS}\n\n"
        "Отменить запись можно в разделе «📋 Мои записи»."
    )
    await callback.answer()

    await notify_admin(
        callback.bot, callback.from_user, booking_id, name, price, start, end
    )
