import logging
from datetime import date, datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
import database
import timetable
from keyboards import main_menu_for
from notifications import send_to_admin
from phone import normalize_phone
from ui import client_html

router = Router()
logger = logging.getLogger(__name__)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
HTML = "HTML"  # режим разметки: <b>жирный</b>, <i>курсив</i>

SERVICE_PROMPT = "💆 <b>Запись на приём</b>\n<i>Шаг 1 из 4 · выберите услугу</i>"

PHONE_CANCEL = "⬅ Отмена"
# Текст, похожий на номер: цифры, пробелы, дефисы, скобки
PHONE_LIKE = r"^[+\d][\d\s\-()]{5,}$"
PHONE_PROMPT = (
    "📱 <b>Номер телефона</b>\n\n"
    "Чтобы мы могли связаться с вами, если что-то изменится, укажите номер. "
    "Нажмите кнопку ниже или введите номер текстом, например "
    "<code>+375291234567</code>.\n\n"
    "<i>Номер увидит только администратор студии.</i>"
)


class BookingStates(StatesGroup):
    waiting_phone = State()


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


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton(text=PHONE_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def notify_admin(bot, user, booking_id, name, price, start, end):
    """Отправляет владельцу студии уведомление о новой записи."""
    phone = await database.get_phone(user.id)
    text = (
        f"🔔 <b>Новая запись №{booking_id}</b>\n\n"
        f"👤 {client_html(user.id, user.full_name, user.username, phone)}\n"
        f"💆 {escape(name)}, {price} BYN\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}"
    )
    await send_to_admin(bot, text, parse_mode=HTML)


async def finish_booking(
    target: Message, user, bot, service_id: int, day_str: str, hhmm: str, edit: bool
):
    """Проверяет время, создаёт запись и показывает результат.

    edit=True: правим сообщение с кнопками (обычный путь).
    edit=False: отправляем новое сообщение (после ввода телефона).
    """

    async def show(text: str, markup=None):
        if edit:
            await target.edit_text(text, reply_markup=markup, parse_mode=HTML)
        else:
            await target.answer(text, reply_markup=markup, parse_mode=HTML)

    service = await database.get_service(service_id)
    if service is None:
        await show("Эта услуга недоступна. Нажмите «💆 Записаться», чтобы выбрать другую.")
        return
    _, name, duration, price = service
    start = datetime.strptime(f"{day_str} {hhmm}", "%Y-%m-%d %H%M")
    end = start + timedelta(minutes=duration)

    taken_text = "😔 К сожалению, это время только что заняли. Выберите другую дату:"

    # Защита 1: время всё ещё допустимо (не прошло, в рабочие часы, не занято)
    busy = await database.get_busy_intervals(start.date())
    if start not in timetable.free_slots(start.date(), duration, busy):
        await show(taken_text, dates_keyboard(service_id))
        return

    # Защита 2: проверка и сохранение в одной транзакции
    booking_id = await database.create_booking(
        user.id, service_id, start, end, timetable.now_local()
    )
    if booking_id is None:
        await show(taken_text, dates_keyboard(service_id))
        return

    await show(
        f"🎉 <b>Вы записаны!</b> Запись №{booking_id}\n\n"
        f"💆 {escape(name)} ({duration} мин)\n"
        f"📅 {format_day(start.date())}\n"
        f"🕒 {start:%H:%M}–{end:%H:%M}\n"
        f"💰 {price} BYN\n"
        f"📍 {escape(config.STUDIO_ADDRESS)}\n\n"
        "Мы напомним о записи заранее. Посмотреть или отменить её можно "
        "в разделе «📋 Мои записи».",
        calendar_keyboard(booking_id),
    )
    await notify_admin(bot, user, booking_id, name, price, start, end)


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
        reason = ""
        if day == timetable.now_local().date():
            # Объясняем, почему сегодня не осталось времени
            reason = (
                f"\nНа сегодня запись возможна не позднее чем за "
                f"{config.MIN_NOTICE_MIN} мин до начала, а услуга ({duration} мин) "
                f"должна закончиться до {config.WORK_END_HOUR}:00."
            )
        await callback.message.edit_text(
            header
            + "😔 На эту дату свободного времени нет."
            + reason
            + "\n<i>Выберите другую дату:</i>",
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
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    _, service_id, day_str, hhmm = callback.data.split(":")
    service_id = int(service_id)

    # Если телефон обязателен, а его ещё нет, сначала просим номер.
    # Выбранное время запоминаем и вернёмся к нему после ввода номера
    if config.PHONE_REQUIRED and not await database.get_phone(callback.from_user.id):
        await state.set_state(BookingStates.waiting_phone)
        await state.update_data(service_id=service_id, day=day_str, hhmm=hhmm)
        await callback.message.answer(
            PHONE_PROMPT, reply_markup=phone_keyboard(), parse_mode=HTML
        )
        await callback.answer()
        return

    await finish_booking(
        callback.message,
        callback.from_user,
        callback.bot,
        service_id,
        day_str,
        hhmm,
        edit=True,
    )
    await callback.answer()


async def save_phone_and_continue(message: Message, state: FSMContext, phone: str):
    """Сохраняет номер и продолжает прерванную запись."""
    data = await state.get_data()
    await state.clear()
    await database.set_phone(message.from_user.id, phone)
    await message.answer(
        f"✅ Номер {phone} сохранён.",
        reply_markup=main_menu_for(message.from_user.id),
    )
    if not data:
        # Выбранное время потерялось (например, бот перезапускали)
        await message.answer("Нажмите «💆 Записаться», чтобы выбрать время.")
        return
    await finish_booking(
        message,
        message.from_user,
        message.bot,
        data["service_id"],
        data["day"],
        data["hhmm"],
        edit=False,
    )


@router.message(BookingStates.waiting_phone, F.text == PHONE_CANCEL)
async def phone_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Хорошо, запись не создана. Нажмите «💆 Записаться», когда будете готовы.",
        reply_markup=main_menu_for(message.from_user.id),
    )


@router.message(BookingStates.waiting_phone, F.contact)
async def phone_from_contact(message: Message, state: FSMContext):
    # Принимаем только собственный контакт клиента, а не чужой
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "Пожалуйста, отправьте свой номер: нажмите кнопку «📱 Отправить мой номер»."
        )
        return
    phone = normalize_phone(message.contact.phone_number)
    if phone is None:
        await message.answer("Не получилось распознать номер. Введите его текстом.")
        return
    await save_phone_and_continue(message, state, phone)


@router.message(BookingStates.waiting_phone, F.text.regexp(PHONE_LIKE))
async def phone_from_text(message: Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer(
            "Не получилось распознать номер. Введите его в формате "
            "+375291234567 или нажмите «📱 Отправить мой номер»."
        )
        return
    await save_phone_and_continue(message, state, phone)


@router.message(BookingStates.waiting_phone, F.text, ~F.text.startswith("/"))
async def phone_not_understood(message: Message):
    await message.answer(
        "Это не похоже на номер телефона. Введите его в формате +375291234567, "
        "нажмите «📱 Отправить мой номер» или «⬅ Отмена»."
    )