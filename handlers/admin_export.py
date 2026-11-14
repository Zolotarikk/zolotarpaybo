from datetime import datetime, time, timedelta

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
import database
import exporter
import timetable

router = Router()
# Как и вся админка, работает только для владельца
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)

PERIODS = {"month": "Этот месяц", "prev": "Прошлый месяц", "all": "Всё время"}


def export_window(period: str):
    """Границы периода [от, до)."""
    today = timetable.now_local().date()
    first = datetime.combine(today.replace(day=1), time(0, 0))
    if period == "month":
        return first, (first + timedelta(days=32)).replace(day=1)
    if period == "prev":
        return (first - timedelta(days=1)).replace(day=1), first
    return datetime(2000, 1, 1), datetime(2100, 1, 1)


@router.callback_query(F.data == "adm:exm")
async def export_menu(callback: CallbackQuery):
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"adm:ex:{key}")]
        for key, label in PERIODS.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="⬅ В админ-панель", callback_data="adm:menu")]
    )
    await callback.message.edit_text(
        "📥 <b>Выгрузка записей в Excel</b>\n\nЗа какой период подготовить файл?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ex:"))
async def export_file(callback: CallbackQuery):
    period = callback.data.split(":")[2]
    if period not in PERIODS:
        await callback.answer()
        return
    from_dt, to_dt = export_window(period)
    rows = await database.get_export_rows(from_dt, to_dt)
    if not rows:
        await callback.answer("За этот период записей нет", show_alert=True)
        return

    await callback.answer("Готовлю файл…")
    content = exporter.build_xlsx(rows)
    filename = f"zapisi_{config.CLIENT}_{timetable.now_local():%Y-%m-%d}.xlsx"
    await callback.message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=(
            f"📥 {PERIODS[period]}: записей — {len(rows)}.\n"
            "В файле данные клиентов, не пересылайте его посторонним."
        ),
    )