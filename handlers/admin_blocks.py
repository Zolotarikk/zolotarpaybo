from datetime import date, datetime, time

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
import database
import timetable
from handlers.booking import WEEKDAYS, chunk, format_day

router = Router()
# Как и вся админка, работает только для владельца
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)


def hhmm(minutes: int) -> str:
    """Минуты от начала суток в вид ЧЧММ: 600 -> '1000'."""
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def pretty(minutes: int) -> str:
    """Минуты от начала суток в вид Ч:ММ: 600 -> '10:00'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def back_row(callback_data: str, text: str = "⬅ Назад"):
    return [InlineKeyboardButton(text=text, callback_data=callback_data)]


async def make_block(callback: CallbackQuery, day: date, start: datetime, end: datetime):
    """Создаёт блок и показывает результат."""
    block_id, conflicts = await database.create_block(start, end)
    if block_id is None:
        lines = []
        for conflict_id in conflicts:
            conflict = await database.get_booking(conflict_id)
            if conflict:
                lines.append(f"• {conflict[4]:%H:%M}–{conflict[5]:%H:%M}, {conflict[2]}")
        text = (
            "Нельзя закрыть это время: в нём уже есть записи:\n"
            + "\n".join(lines)
            + "\n\nОткройте расписание дня, отмените их и повторите."
        )
    else:
        text = (
            f"🚫 Время закрыто:\n{format_day(day)}, {start:%H:%M}–{end:%H:%M}\n\n"
            "Клиенты больше не смогут записаться на это время."
        )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Расписание дня",
                    callback_data=f"adm:day:{day.isoformat()}",
                )
            ],
            back_row("adm:menu", "⬅ В админ-панель"),
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "adm:bl")
async def block_choose_date(callback: CallbackQuery):
    buttons = [
        InlineKeyboardButton(
            text=f"{WEEKDAYS[day.weekday()]} {day:%d.%m}",
            callback_data=f"adm:bd:{day.isoformat()}",
        )
        for day in timetable.available_dates()
    ]
    await callback.message.edit_text(
        "Какую дату закрыть?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=chunk(buttons, 3) + [back_row("adm:menu")]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:bd:"))
async def block_options(callback: CallbackQuery):
    day = date.fromisoformat(callback.data.split(":", 2)[2])
    start_buttons = [
        InlineKeyboardButton(
            text=pretty(m), callback_data=f"adm:bs:{day.isoformat()}:{hhmm(m)}"
        )
        for m in range(
            config.WORK_START_HOUR * 60,
            config.WORK_END_HOUR * 60,
            config.SLOT_STEP_MIN,
        )
    ]
    rows = (
        [
            [
                InlineKeyboardButton(
                    text="🚫 Закрыть весь день",
                    callback_data=f"adm:ba:{day.isoformat()}",
                )
            ]
        ]
        + chunk(start_buttons, 4)
        + [back_row("adm:bl")]
    )
    await callback.message.edit_text(
        f"{format_day(day)}\n\n"
        "Закройте весь день или выберите время НАЧАЛА закрытия:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ba:"))
async def block_whole_day(callback: CallbackQuery):
    day = date.fromisoformat(callback.data.split(":", 2)[2])
    start = datetime.combine(day, time(config.WORK_START_HOUR))
    end = datetime.combine(day, time(config.WORK_END_HOUR))
    await make_block(callback, day, start, end)


@router.callback_query(F.data.startswith("adm:bs:"))
async def block_choose_end(callback: CallbackQuery):
    _, _, day_str, start_hhmm = callback.data.split(":")
    start_min = int(start_hhmm[:2]) * 60 + int(start_hhmm[2:])
    end_buttons = [
        InlineKeyboardButton(
            text=pretty(m), callback_data=f"adm:be:{day_str}:{start_hhmm}:{hhmm(m)}"
        )
        for m in range(
            start_min + config.SLOT_STEP_MIN,
            config.WORK_END_HOUR * 60 + 1,
            config.SLOT_STEP_MIN,
        )
    ]
    day = date.fromisoformat(day_str)
    await callback.message.edit_text(
        f"{format_day(day)}\nНачало: {pretty(start_min)}\n\n"
        "Выберите время ОКОНЧАНИЯ закрытия:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=chunk(end_buttons, 4) + [back_row(f"adm:bd:{day_str}")]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:be:"))
async def block_interval(callback: CallbackQuery):
    _, _, day_str, start_hhmm, end_hhmm = callback.data.split(":")
    start = datetime.strptime(f"{day_str} {start_hhmm}", "%Y-%m-%d %H%M")
    end = datetime.strptime(f"{day_str} {end_hhmm}", "%Y-%m-%d %H%M")
    await make_block(callback, start.date(), start, end)


async def render_blocks(callback: CallbackQuery):
    """Список будущего закрытого времени с кнопками «открыть»."""
    blocks = await database.get_future_blocks(timetable.now_local())
    rows = []
    if not blocks:
        text = "Закрытого времени нет."
    else:
        text = "🚫 Закрытое время. Нажмите на строку, чтобы открыть его:"
        for block_id, start, end in blocks:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=(
                            f"🔓 {WEEKDAYS[start.weekday()]} {start:%d.%m} "
                            f"{start:%H:%M}–{end:%H:%M}"
                        ),
                        callback_data=f"adm:ux:{block_id}",
                    )
                ]
            )
    rows.append(back_row("adm:menu", "⬅ В админ-панель"))
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:ul")
async def show_blocks(callback: CallbackQuery):
    await render_blocks(callback)


@router.callback_query(F.data.startswith("adm:ux:"))
async def unblock(callback: CallbackQuery):
    block_id = int(callback.data.split(":")[2])
    await database.delete_block(block_id)
    await render_blocks(callback)