from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

import config
import database

router = Router()


def ics_escape(text: str) -> str:
    """Экранирует символы, которые в формате .ics имеют особый смысл."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(booking_id: int, name: str, start: datetime, end: datetime) -> str:
    offset = timedelta(hours=config.TIMEZONE_OFFSET_HOURS)

    def utc(moment: datetime) -> str:
        return (moment - offset).strftime("%Y%m%dT%H%M%SZ")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Booking bot//RU",
        "BEGIN:VEVENT",
        f"UID:booking-{booking_id}-{config.CLIENT}@bot",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{utc(start)}",
        f"DTEND:{utc(end)}",
        f"SUMMARY:{ics_escape(name + ' — ' + config.STUDIO_NAME)}",
        f"LOCATION:{ics_escape(config.STUDIO_ADDRESS)}",
        # Напоминание в календаре за то же время, что и второе напоминание бота
        "BEGIN:VALARM",
        f"TRIGGER:-PT{config.REMIND_SECOND_HOURS}H",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{ics_escape(name)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


@router.callback_query(F.data.startswith("ics:"))
async def send_ics(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await database.get_booking(booking_id)
    # Файл получает только владелец активной записи
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.answer("Запись не найдена или отменена", show_alert=True)
        return
    _, _, name, _price, start, end, _status = booking
    content = build_ics(booking_id, name, start, end).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(content, filename=f"booking-{booking_id}.ics"),
        caption="📅 Откройте файл, чтобы добавить запись в календарь телефона.",
    )
    await callback.answer()