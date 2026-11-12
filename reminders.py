import asyncio
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database
import timetable
from handlers.booking import format_day
from notifications import send_to_user

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 60  # как часто проверяем, не пора ли напомнить


async def send_reminders(bot, kind: str, hours: int):
    """Отправляет напоминания одного вида (первое или второе)."""
    now = timetable.now_local()
    due = await database.get_due_reminders(now, kind, hours)
    for booking_id, user_id, name, start, end in due:
        details = (
            f"№{booking_id}: {name}\n"
            f"📅 {format_day(start.date())}\n"
            f"🕒 {start:%H:%M}–{end:%H:%M}\n"
            f"📍 {config.STUDIO_ADDRESS}"
        )
        if kind == "24h":
            text = (
                f"⏰ Напоминаем о вашей записи {details}\n\n"
                "Ждём вас! Если планы изменились, отмените запись заранее: "
                "время достанется другому клиенту."
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отменить запись",
                            callback_data=f"cancel:{booking_id}",
                        )
                    ]
                ]
            )
        else:
            text = f"⏰ Скоро ваша запись {details}\n\nЖдём вас!"
            keyboard = None

        delivered = await send_to_user(bot, user_id, text, reply_markup=keyboard)
        if not delivered:
            logger.warning("Напоминание по записи %s не доставлено", booking_id)
        # Отмечаем в любом случае, чтобы не пытаться бесконечно каждую минуту
        await database.mark_reminded(booking_id, kind)


async def reminder_loop(bot):
    """Бесконечный цикл: раз в минуту проверяет, не пора ли отправить напоминания."""
    while True:
        try:
            await send_reminders(bot, "24h", config.REMIND_FIRST_HOURS)
            await send_reminders(bot, "2h", config.REMIND_SECOND_HOURS)
        except Exception:
            # Ошибка в одной проверке не должна остановить весь цикл
            logger.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(CHECK_INTERVAL_SEC)