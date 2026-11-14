from datetime import timedelta
from html import escape

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
from handlers.booking import HTML, format_day
from notifications import send_to_admin
from ui import client_html

router = Router()


def card_text(name: str, start, end) -> str:
    """Текст карточки записи."""
    return (
        f"💆 <b>{escape(name)}</b>\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}"
    )


def card_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Перенести", callback_data=f"mv:{booking_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data=f"cancel:{booking_id}"
                ),
            ]
        ]
    )


async def get_cancellable_booking(callback: CallbackQuery, booking_id: int):
    """Возвращает запись, если её можно отменить. Иначе показывает причину."""
    booking = await database.get_booking(booking_id)
    # Запись должна существовать, принадлежать этому клиенту и быть активной
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.answer("Эта запись не найдена или уже отменена", show_alert=True)
        return None
    start = booking[4]
    if start - timetable.now_local() < timedelta(hours=config.CANCEL_MIN_HOURS):
        # Объясняем обычным сообщением: всплывающее окно легко не заметить
        await callback.message.answer(
            f"⏳ Отменить запись через бота можно не позднее чем за "
            f"{config.CANCEL_MIN_HOURS} ч. до начала.\n"
            f"Пожалуйста, позвоните в студию: {config.STUDIO_PHONE}"
        )
        await callback.answer("Отмена через бота уже недоступна")
        return None
    return booking


@router.message(F.text == "📋 Мои записи")
async def my_bookings(message: Message):
    bookings = await database.get_user_bookings(
        message.from_user.id, timetable.now_local()
    )
    if not bookings:
        await message.answer(
            "У вас нет предстоящих записей. "
            "Нажмите «💆 Записаться», чтобы выбрать время."
        )
        return
    await message.answer("📋 <b>Ваши предстоящие записи</b>", parse_mode=HTML)
    for booking_id, name, start, end in bookings:
        await message.answer(
            card_text(name, start, end),
            reply_markup=card_keyboard(booking_id),
            parse_mode=HTML,
        )


@router.callback_query(F.data.startswith("card:"))
async def show_card(callback: CallbackQuery):
    """Возвращает карточку записи (кнопки «Назад» и «Нет, оставить»)."""
    booking_id = int(callback.data.split(":")[1])
    booking = await database.get_booking(booking_id)
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.message.edit_text("Эта запись уже отменена или перенесена.")
        await callback.answer()
        return
    _, _, name, _price, start, end, _status = booking
    await callback.message.edit_text(
        card_text(name, start, end),
        reply_markup=card_keyboard(booking_id),
        parse_mode=HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "mybookings")
async def legacy_back_to_list(callback: CallbackQuery):
    """Кнопка из старых сообщений: просто отправляем в раздел «Мои записи»."""
    await callback.message.edit_text(
        "Откройте раздел «📋 Мои записи» в меню, чтобы увидеть актуальные записи."
    )
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
            [
                InlineKeyboardButton(
                    text="Нет, оставить", callback_data=f"card:{booking_id}"
                )
            ],
        ]
    )
    await callback.message.edit_text(
        "Отменить эту запись?\n\n" + card_text(name, start, end),
        reply_markup=keyboard,
        parse_mode=HTML,
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
        "✅ Запись отменена.\n\n"
        "Чтобы выбрать другое время, нажмите «💆 Записаться»."
    )
    await callback.answer()

    user = callback.from_user
    phone = await database.get_phone(user.id)
    await send_to_admin(
        callback.bot,
        "❌ <b>Клиент отменил запись</b>\n\n"
        f"👤 {client_html(user.id, user.full_name, user.username, phone)}\n"
        f"💆 {escape(name)}\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}",
        parse_mode="HTML",
    )