from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import config
import stats

router = Router()
# Как и вся админка, работает только для владельца
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)


def period_keyboard(current: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки выбора периода; текущий отмечен точкой."""
    rows = [
        [
            InlineKeyboardButton(
                text=("• " if key == current else "") + label,
                callback_data=f"adm:st:{key}",
            )
        ]
        for key, label in stats.PERIODS.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="⬅ В админ-панель", callback_data="adm:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:stm")
async def stats_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\nВыберите период:",
        reply_markup=period_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:st:"))
async def show_stats(callback: CallbackQuery):
    period = callback.data.split(":")[2]
    if period not in stats.PERIODS:
        await callback.answer()
        return
    data = await stats.collect(period)
    await callback.message.edit_text(
        stats.format_stats(period, data),
        reply_markup=period_keyboard(period),
        parse_mode="HTML",
    )
    await callback.answer()