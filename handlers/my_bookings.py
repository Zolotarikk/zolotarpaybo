from datetime import timedelta

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
from handlers.booking import format_day
from notifications import send_to_admin

router = Router()


async def render_my_bookings(user_id: int):
    """Собирает текст и кнопки списка записей клиента."""
    bookings = await database.get_user_bookings(user_id, timetable.now_local())
    if not bookings:
        return (
            "У вас нет предстоящих записей. "
            "Нажмите «💆 Записаться», чтобы выбрать время.",
            None,
        )
    lines = ["📋 Ваши предстоящие записи:\n"]
    rows = []
    for booking_id, name, start, end in bookings:
        lines.append(
            f"№{booking_id} — {name}\n"
            f"📅 {format_day(start.date())}\n"
            f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔁 Перенести №{booking_id}",
                    callback_data=f"mv:{booking_id}",
                ),
                InlineKeyboardButton(
                    text=f"❌ Отменить №{booking_id}",
                    callback_data=f"cancel:{booking_id}",
                ),
            ]
        )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def get_cancellable_booking(callback: CallbackQuery, booking_id: int):
    """Возвращает запись, если её можно отменить. Иначе показывает причину."""
    booking = await database.get_booking(booking_id)
    # Проверяем, что запись существует, принадлежит этому клиенту и активна
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.answer("Эта запись не найдена или уже отменена", show_alert=True)
        return None
    start = booking[4]
    if start - timetable.now_local() < timedelta(hours=config.CANCEL_MIN_HOURS):
        await callback.answer(
            f"Отмена возможна не позднее чем за {config.CANCEL_MIN_HOURS} ч. "
            "до начала. Пожалуйста, позвоните в студию.",
            show_alert=True,
        )
        return None
    return booking


@router.message(F.text == "📋 Мои записи")
async def my_bookings(message: Message):
    text, keyboard = await render_my_bookings(message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "mybookings")
async def back_to_list(callback: CallbackQuery):
    text, keyboard = await render_my_bookings(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def ask_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await get_cancellable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отменить", callback_data=f"cancel_yes:{booking_id}"
                )
            ],
            [InlineKeyboardButton(text="Нет, оставить", callback_data="mybookings")],
        ]
    )
    await callback.message.edit_text(
        f"Отменить запись №{booking_id}?\n\n"
        f"💆 {name}\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_yes:"))
async def do_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await get_cancellable_booking(callback, booking_id)
    if booking is None:
        return
    _, _, name, _price, start, end, _status = booking

    cancelled = await database.cancel_booking(booking_id, callback.from_user.id)
    if not cancelled:
        await callback.answer("Эта запись уже отменена", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ Запись №{booking_id} отменена.\n\n"
        "Чтобы выбрать другое время, нажмите «💆 Записаться»."
    )
    await callback.answer()

    user = callback.from_user
    username = f" (@{user.username})" if user.username else ""
    await send_to_admin(
        callback.bot,
        f"❌ Клиент отменил запись №{booking_id}\n\n"
        f"👤 {user.full_name}{username}\n"
        f"💆 {name}\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}",
    )