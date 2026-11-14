from datetime import date
from html import escape

import config
import database
import timetable
from handlers.booking import format_day
from notifications import send_to_admin
from ui import client_html


async def build_digest(day: date) -> str:
    """Текст сводки на день: записи, закрытое время, загрузка."""
    bookings = await database.get_day_bookings(day)
    blocks = await database.get_day_blocks(day)

    entries = []  # (время начала, текст) для сортировки по времени
    booked_min = 0
    for (
        _booking_id,
        client_id,
        full_name,
        username,
        phone,
        service,
        start,
        end,
    ) in bookings:
        booked_min += int((end - start).total_seconds() // 60)
        entries.append(
            (
                start,
                f"🕒 {start:%H:%M}–{end:%H:%M} · {escape(service)}\n"
                f"    👤 {client_html(client_id, full_name, username, phone)}",
            )
        )
    for _block_id, start, end in blocks:
        entries.append((start, f"🚫 {start:%H:%M}–{end:%H:%M} · закрыто"))
    entries.sort(key=lambda item: item[0])

    work_min = (config.WORK_END_HOUR - config.WORK_START_HOUR) * 60
    lines = ["☀️ <b>Сводка на сегодня</b>", f"📅 {format_day(day)}", ""]
    if not bookings:
        lines.append("Записей на сегодня пока нет.")
    else:
        load = round(100 * booked_min / work_min)
        lines.append(
            f"Записей: <b>{len(bookings)}</b> · "
            f"занято {booked_min / 60:.1f} ч из {work_min / 60:.0f} ч ({load}%)"
        )
    if entries:
        lines.append("")
        lines += [text for _, text in entries]
    return "\n".join(lines)


async def send_digest_if_due(bot):
    """Раз в день присылает владельцу сводку на сегодня."""
    if config.DIGEST_TIME is None or not config.ADMIN_ID:
        return
    now = timetable.now_local()
    today = now.date()
    if today.weekday() not in config.WORK_WEEKDAYS:
        return  # в выходной сводка не нужна
    if now.time() < config.DIGEST_TIME or now.hour >= config.WORK_END_HOUR:
        return
    if await database.get_state("last_digest") == today.isoformat():
        return  # сегодня уже отправляли

    # Отмечаем заранее: при сбое лучше пропустить сводку, чем слать её каждую минуту
    await database.set_state("last_digest", today.isoformat())
    await send_to_admin(bot, await build_digest(today), parse_mode="HTML")