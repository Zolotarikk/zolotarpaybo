from datetime import date, datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
import database
import timetable
from handlers.booking import HTML, calendar_keyboard, chunk, day_label, format_day
from notifications import send_to_admin
from ui import client_html

router = Router()


def title(name: str, start: datetime, end: datetime) -> str:
    return (
        "🔁 <b>Перенос записи</b>\n"
        f"💆 {escape(name)}\n"
        f"Сейчас: {format_day(start.date())}, {start:%H:%M}–{end:%H:%M}\n\n"
    )


def dates_markup(booking_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=day_label(day),
            callback_data=f"mvd:{booking_id}:{day.isoformat()}",
        )
        for day in timetable.available_dates()
    ]
    back = [InlineKeyboardButton(text="⬅ Назад", callback_data=f"card:{booking_id}")]
    return InlineKeyboardMarkup(inline_keyboard=chunk(buttons, 3) + [back])


async def get_movable_booking(callback: CallbackQuery, booking_id: int):
    """Возвращает запись, если её можно перенести. Иначе показывает причину."""
    booking = await database.get_booking(booking_id)
    # Запись должна существовать, принадлежать этому клиенту и быть активной
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.answer("Эта запись не найдена или уже отменена", show_alert=True)
        return None
    if booking[4] - timetable.now_local() < timedelta(hours=config.CANCEL_MIN_HOURS):
        await callback.message.answer(
            f"⏳ Перенести запись через бота можно не позднее чем за "
            f"{config.CANCEL_MIN_HOURS} ч. до начала.\n"
            f"Пожалуйста, позвоните в студию: {config.STUDIO_PHONE}"
        )
        await callback.answer("Перенос через бота уже недоступен")
        return None
    return booking


@router.callback_query(F.data.startswith("mv:"))
async def choose_new_date(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await get_movable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking
    await callback.message.edit_text(
        title(name, start, end) + "<i>Выберите новую дату</i>",
        reply_markup=dates_markup(booking_id),
        parse_mode=HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mvd:"))
async def choose_new_time(callback: CallbackQuery):
    _, booking_id, day_str = callback.data.split(":")
    booking_id = int(booking_id)
    booking = await get_movable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking
    day = date.fromisoformat(day_str)
    duration_min = int((end - start).total_seconds() // 60)

    # Саму переносимую запись при расчёте занятого времени не учитываем
    busy = await database.get_busy_intervals(day, exclude_booking_id=booking_id)
    slots = [
        slot
        for slot in timetable.free_slots(day, duration_min, busy)
        if slot != start  # перенос на то же самое время не нужен
    ]

    header = title(name, start, end) + f"📅 Новая дата: {format_day(day)}\n\n"
    if not slots:
        await callback.message.edit_text(
            header + "😔 На эту дату свободного времени нет.\n"
            "<i>Выберите другую дату:</i>",
            reply_markup=dates_markup(booking_id),
            parse_mode=HTML,
        )
    else:
        buttons = [
            InlineKeyboardButton(
                text=slot.strftime("%H:%M"),
                callback_data=f"mvs:{booking_id}:{day.isoformat()}:{slot:%H%M}",
            )
            for slot in slots
        ]
        back = [InlineKeyboardButton(text="⬅ Назад", callback_data=f"mv:{booking_id}")]
        await callback.message.edit_text(
            header + "<i>Выберите новое время</i>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=chunk(buttons, 4) + [back]
            ),
            parse_mode=HTML,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mvs:"))
async def confirm_move(callback: CallbackQuery):
    _, booking_id, day_str, hhmm = callback.data.split(":")
    booking_id = int(booking_id)
    booking = await get_movable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking
    new_start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")
    new_end = new_start + (end - start)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Перенести",
                    callback_data=f"mvc:{booking_id}:{day_str}:{hhmm}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад", callback_data=f"mvd:{booking_id}:{day_str}"
                )
            ],
        ]
    )
    await callback.message.edit_text(
        "🔁 <b>Проверьте перенос</b>\n"
        f"💆 {escape(name)}\n\n"
        f"<s>{format_day(start.date())}, {start:%H:%M}–{end:%H:%M}</s>\n"
        f"➡ <b>{format_day(new_start.date())}, "
        f"{new_start:%H:%M}–{new_end:%H:%M}</b>",
        reply_markup=keyboard,
        parse_mode=HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mvc:"))
async def do_move(callback: CallbackQuery):
    _, booking_id, day_str, hhmm = callback.data.split(":")
    booking_id = int(booking_id)
    booking = await get_movable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking
    duration = end - start
    new_start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")
    new_end = new_start + duration

    # Защита 1: новое время допустимо (рабочие часы, не прошло, не занято)
    busy = await database.get_busy_intervals(
        new_start.date(), exclude_booking_id=booking_id
    )
    duration_min = int(duration.total_seconds() // 60)
    slot_ok = new_start in timetable.free_slots(new_start.date(), duration_min, busy)

    # Защита 2: проверка и перенос в одной транзакции
    moved = slot_ok and await database.move_booking(
        booking_id, callback.from_user.id, new_start, new_end, timetable.now_local()
    )
    if not moved:
        await callback.message.edit_text(
            "😔 К сожалению, это время только что заняли. Выберите другую дату:",
            reply_markup=dates_markup(booking_id),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "✅ <b>Запись перенесена</b>\n\n"
        f"💆 {escape(name)}\n"
        f"📅 {format_day(new_start.date())}\n"
        f"🕒 {new_start:%H:%M}–{new_end:%H:%M}\n"
        f"📍 {escape(config.STUDIO_ADDRESS)}\n\n"
        "Напоминания придут по новому времени.",
        reply_markup=calendar_keyboard(booking_id),
        parse_mode=HTML,
    )
    await callback.answer()

    user = callback.from_user
    phone = await database.get_phone(user.id)
    await send_to_admin(
        callback.bot,
        "🔁 <b>Клиент перенёс запись</b>\n\n"
        f"👤 {client_html(user.id, user.full_name, user.username, phone)}\n"
        f"💆 {escape(name)}\n"
        f"❌ Было: {format_day(start.date())}, {start:%H:%M}–{end:%H:%M}\n"
        f"✅ Стало: {format_day(new_start.date())}, "
        f"{new_start:%H:%M}–{new_end:%H:%M}",
        parse_mode=HTML,
    )