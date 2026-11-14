import logging
from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database
import timetable
from notifications import send_to_user

logger = logging.getLogger(__name__)


def rating_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Пять кнопок оценки: 1⭐ … 5⭐."""
    buttons = [
        InlineKeyboardButton(text=f"{number}⭐", callback_data=f"rv:{booking_id}:{number}")
        for number in range(1, 6)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def send_review_requests(bot):
    """Спрашивает оценку у клиентов, чей визит закончился."""
    if not config.REVIEWS_ENABLED:
        return
    due = await database.get_due_review_requests(
        timetable.now_local(), config.REVIEW_DELAY_MIN
    )
    for booking_id, user_id, name, start in due:
        text = (
            "💬 Как всё прошло?\n\n"
            f"Вы были у нас: {name}, {start:%d.%m} в {start:%H:%M}.\n"
            "Оцените визит, это займёт секунду:"
        )
        delivered = await send_to_user(
            bot, user_id, text, reply_markup=rating_keyboard(booking_id)
        )
        if not delivered:
            logger.warning("Запрос оценки по записи %s не доставлен", booking_id)
        # Отмечаем в любом случае, чтобы не пытаться бесконечно каждую минуту
        await database.mark_review_requested(booking_id)