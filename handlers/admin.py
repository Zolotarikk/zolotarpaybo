from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database
import timetable
from handlers.booking import WEEKDAYS, chunk, format_day
from keyboards import ADMIN_BUTTON
from notifications import send_to_user

router = Router()
# Все обработчики этого файла работают только для администратора
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)


def panel_keyboard() -> InlineKeyboardMarkup:
    today = timetable.now_local().date()
    tomorrow = today + timedelta(days=1)
    rows = [
        [
            InlineKeyboardButton(
                text="📅 Записи на сегодня",
                callback_data=f"adm:day:{today.isoformat()}",
            )
        ],
        [
            InlineKeyboardButton(
                text="📅 Записи на завтра",
                callback_data=f"adm:day:{tomorrow.isoformat()}",
            )
        ],
        [InlineKeyboardButton(text="🗓 Выбрать другую дату", callback_data="adm:dates")],
        [InlineKeyboardButton(text="🚫 Закрыть время", callback_data="adm:bl")],
        [InlineKeyboardButton(text="🔓 Закрытое время", callback_data="adm:ul")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_day(callback: CallbackQuery, day: date):
    """Показывает записи и закрытое время на день, с кнопками отмены."""
    bookings = await database.get_day_bookings(day)
    blocks = await database.get_day_blocks(day)

    entries = []  # (время начала, текст) для сортировки по времени
    rows = []
    for booking_id, full_name, username, service, start, end in bookings:
        who = full_name or "Клиент"
        if username:
            who += f" (@{username})"
        entries.append(
            (
                start,
                f"🕒 {start:%H:%M}–{end:%H:%M} · №{booking_id}\n"
                f"💆 {service}\n"
                f"👤 {who}\n",
            )
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Отменить №{booking_id} ({start:%H:%M})",
                    callback_data=f"adm:cx:{booking_id}",
                )
            ]
        )
    for _block_id, start, end in blocks:
        entries.append((start, f"🚫 {start:%H:%M}–{end:%H:%M} · закрыто\n"))
    entries.sort(key=lambda item: item[0])

    lines = [f"📅 {format_day(day)}\n"]
    if not entries:
        lines.append("Записей и закрытого времени нет.")
    lines += [text for _, text in entries]
    rows.append([InlineKeyboardButton(text="⬅ В админ-панель", callback_data="adm:menu")])
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.message(Command("admin"))
@router.message(F.text == ADMIN_BUTTON)
async def open_panel(message: Message):
    await message.answer("⚙️ Админ-панель", reply_markup=panel_keyboard())


@router.callback_query(F.data == "adm:menu")
async def back_to_panel(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ Админ-панель", reply_markup=panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "adm:dates")
async def choose_date(callback: CallbackQuery):
    buttons = [
        InlineKeyboardButton(
            text=f"{WEEKDAYS[day.weekday()]} {day:%d.%m}",
            callback_data=f"adm:day:{day.isoformat()}",
        )
        for day in timetable.available_dates()
    ]
    back = [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:menu")]
    await callback.message.edit_text(
        "Выберите дату:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=chunk(buttons, 3) + [back]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:day:"))
async def show_day(callback: CallbackQuery):
    day = date.fromisoformat(callback.data.split(":", 2)[2])
    await render_day(callback, day)


@router.callback_query(F.data.startswith("adm:cx:"))
async def ask_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[2])
    booking = await database.get_booking(booking_id)
    if booking is None or booking[6] != "active":
        await callback.answer("Запись не найдена или уже отменена", show_alert=True)
        return
    _, _, name, _price, start, end, _status = booking
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отменить", callback_data=f"adm:cy:{booking_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Нет, оставить",
                    callback_data=f"adm:day:{start.date().isoformat()}",
                )
            ],
        ]
    )
    await callback.message.edit_text(
        f"Отменить запись №{booking_id}?\n\n"
        f"💆 {name}\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n\n"
        "Клиент получит уведомление об отмене.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cy:"))
async def do_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[2])
    booking = await database.get_booking(booking_id)
    if booking is None or booking[6] != "active":
        await callback.answer("Запись не найдена или уже отменена", show_alert=True)
        return
    _, client_id, name, _price, start, end, _status = booking

    cancelled = await database.cancel_booking(booking_id, client_id)
    if not cancelled:
        await callback.answer("Запись уже отменена", show_alert=True)
        return

    delivered = await send_to_user(
        callback.bot,
        client_id,
        f"😔 К сожалению, студия вынуждена отменить вашу запись №{booking_id}:\n\n"
        f"💆 {name}\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n\n"
        "Приносим извинения. Выбрать другое время можно в разделе «💆 Записаться».",
    )
    result = f"✅ Запись №{booking_id} отменена."
    if delivered:
        result += " Клиенту отправлено уведомление."
    else:
        result += " Не удалось уведомить клиента, свяжитесь с ним лично."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅ К расписанию дня",
                    callback_data=f"adm:day:{start.date().isoformat()}",
                )
            ]
        ]
    )
    await callback.message.edit_text(result, reply_markup=keyboard)
    await callback.answer()