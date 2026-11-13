import logging
from datetime import date, datetime, timedelta
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

router = Router()
logger = logging.getLogger(__name__)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
HTML = "HTML"  # режим разметки: <b>жирный</b>, <i>курсив</i>

SERVICE_PROMPT = "💆 <b>Запись на приём</b>\n<i>Шаг 1 из 4 · выберите услугу</i>"


def format_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"


def day_label(day: date) -> str:
    """Подпись даты на кнопке: «Сегодня», «Завтра» или «Пн 16.11»."""
    today = timetable.now_local().date()
    if day == today:
        return "Сегодня"
    if day == today + timedelta(days=1):
        return "Завтра"
    return f"{WEEKDAYS[day.weekday()]} {day:%d.%m}"


def chunk(buttons: list, size: int) -> list[list]:
    """Разбивает список кнопок на ряды по size штук."""
    return [buttons[i : i + size] for i in range(0, len(buttons), size)]


def services_keyboard(services, last_service=None) -> InlineKeyboardMarkup:
    rows = []
    if last_service:
        # Быстрая кнопка: услуга из прошлой записи клиента
        last_id, last_name = last_service
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⚡ Как в прошлый раз: {last_name}",
                    callback_data=f"svc:{last_id}",
                )
            ]
        )
    rows += [
        [
            InlineKeyboardButton(
                text=f"{name} · {duration} мин · {price} BYN",
                callback_data=f"svc:{service_id}",
            )
        ]
        for service_id, name, duration, price in services
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calendar_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Добавить в календарь",
                    callback_data=f"ics:{booking_id}",
                )
            ]
        ]
    )


def dates_keyboard(service_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=day_label(day),
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
        "😔 К сожалению, это время только что заняли. Выберите другую дату:",
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
    blocks = []
    for _, name, duration, price in services:
        block = f"<b>{escape(name)}</b> · {duration} мин · {price} BYN"
        description = config.SERVICE_DESCRIPTIONS.get(name)
        if description:
            block += f"\n<i>{escape(description)}</i>"
        blocks.append(block)
    await message.answer(
        "💰 <b>Услуги и цены</b>\n\n" + "\n\n".join(blocks), parse_mode=HTML
    )


@router.message(F.text == "💆 Записаться")
async def start_booking(message: Message):
    services = await database.get_services()
    if not services:
        await message.answer("Список услуг пока пуст.")
        return
    last_service = await database.get_last_service(message.from_user.id)
    await message.answer(
        SERVICE_PROMPT,
        reply_markup=services_keyboard(services, last_service),
        parse_mode=HTML,
    )


@router.callback_query(F.data == "back:services")
async def back_to_services(callback: CallbackQuery):
    services = await database.get_services()
    last_service = await database.get_last_service(callback.from_user.id)
    await callback.message.edit_text(
        SERVICE_PROMPT,
        reply_markup=services_keyboard(services, last_service),
        parse_mode=HTML,
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
    text = f"💆 <b>{escape(name)}</b>\n⏱ {duration} мин · 💰 {price} BYN\n"
    description = config.SERVICE_DESCRIPTIONS.get(name)
    if description:
        text += f"<i>{escape(description)}</i>\n"
    text += "\n<i>Шаг 2 из 4 · выберите дату</i>"
    await callback.message.edit_text(
        text, reply_markup=dates_keyboard(service_id), parse_mode=HTML
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

    header = f"💆 <b>{escape(name)}</b>\n📅 {format_day(day)}\n\n"
    if not slots:
        await callback.message.edit_text(
            header + "😔 На эту дату свободного времени нет.\n"
            "<i>Выберите другую дату:</i>",
            reply_markup=dates_keyboard(service_id),
            parse_mode=HTML,
        )
    else:
        await callback.message.edit_text(
            header + "<i>Шаг 3 из 4 · выберите время</i>",
            reply_markup=slots_keyboard(service_id, day, slots),
            parse_mode=HTML,
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
        "✅ <b>Проверьте запись</b>\n"
        "<i>Шаг 4 из 4 · осталось подтвердить</i>\n\n"
        f"💆 {escape(name)} ({duration} мин)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        f"💰 {price} BYN\n"
        f"📍 {escape(config.STUDIO_ADDRESS)}",
        reply_markup=confirm_keyboard(service_id, start.date(), hhmm),
        parse_mode=HTML,
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
        f"🎉 <b>Вы записаны!</b> Запись №{booking_id}\n\n"
        f"💆 {escape(name)} ({duration} мин)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        f"💰 {price} BYN\n"
        f"📍 {escape(config.STUDIO_ADDRESS)}\n\n"
        "Мы напомним о записи заранее. Посмотреть или отменить её можно "
        "в разделе «📋 Мои записи».",
        reply_markup=calendar_keyboard(booking_id),
        parse_mode=HTML,
    )
    await callback.answer()

    await notify_admin(
        callback.bot, callback.from_user, booking_id, name, price, start, end
    )