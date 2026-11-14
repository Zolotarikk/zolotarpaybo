from collections import Counter
from datetime import datetime, time, timedelta

import config
import database
import timetable

PERIODS = {
    "week": "Последние 7 дней",
    "month": "Последние 30 дней",
    "ahead": "Ближайшие 7 дней",
}


def window(period: str):
    """Границы периода [от, до) и признак «это будущее»."""
    now = timetable.now_local()
    today = datetime.combine(now.date(), time(0, 0))
    if period == "week":
        return today - timedelta(days=6), now, False
    if period == "month":
        return today - timedelta(days=29), now, False
    return now, today + timedelta(days=7), True


def overlap_min(a_start, a_end, b_start, b_end) -> int:
    """Сколько минут пересекаются два отрезка времени."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(int((end - start).total_seconds() // 60), 0)


def capacity_minutes(from_dt, to_dt, blocks) -> int:
    """Сколько рабочих минут в периоде (без выходных и закрытого времени)."""
    total = 0
    day = from_dt.date()
    last_day = (to_dt - timedelta(seconds=1)).date()
    while day <= last_day:
        if day.weekday() in config.WORK_WEEKDAYS:
            work_start = datetime.combine(day, time(config.WORK_START_HOUR))
            work_end = datetime.combine(day, time(config.WORK_END_HOUR))
            total += overlap_min(work_start, work_end, from_dt, to_dt)
        day += timedelta(days=1)
    for block_start, block_end in blocks:
        total -= overlap_min(block_start, block_end, from_dt, to_dt)
    return max(total, 0)


async def collect(period: str) -> dict:
    """Собирает цифры за период."""
    from_dt, to_dt, future = window(period)
    rows = await database.get_period_bookings(from_dt, to_dt)
    blocks = await database.get_period_blocks(from_dt, to_dt)
    first_visits = await database.get_first_visit_dates()

    # В строках: 0 клиент, 1 услуга, 2 цена, 3 начало, 4 конец, 5 статус
    active = [row for row in rows if row[5] == "active"]
    cancelled = [row for row in rows if row[5] == "cancelled"]

    clients = {row[0] for row in active}
    new_clients = {
        user_id
        for user_id in clients
        if user_id in first_visits and from_dt <= first_visits[user_id] < to_dt
    }
    by_service = Counter()
    revenue_by_service = Counter()
    for row in active:
        by_service[row[1]] += 1
        revenue_by_service[row[1]] += row[2]

    return {
        "future": future,
        "count": len(active),
        "cancelled": len(cancelled),
        "revenue": sum(row[2] for row in active),
        "booked_min": sum(
            int((row[4] - row[3]).total_seconds() // 60) for row in active
        ),
        "capacity_min": capacity_minutes(from_dt, to_dt, blocks),
        "clients": len(clients),
        "new_clients": len(new_clients),
        "top": [
            (name, count, revenue_by_service[name])
            for name, count in by_service.most_common(3)
        ],
    }


def format_stats(period: str, data: dict) -> str:
    """Текст экрана статистики (HTML)."""
    from html import escape

    lines = [f"📊 <b>{PERIODS[period]}</b>", ""]
    if data["count"] == 0:
        lines.append("Записей за этот период нет.")
    else:
        average = round(data["revenue"] / data["count"])
        lines.append(f"📅 Записей: <b>{data['count']}</b>")
        lines.append(
            f"👥 Клиентов: {data['clients']} (новых: {data['new_clients']})"
        )
        lines.append(
            f"💰 {'Ожидаемая выручка' if data['future'] else 'Выручка'}: "
            f"<b>{data['revenue']} BYN</b> (средний чек: {average} BYN)"
        )

    capacity = data["capacity_min"]
    booked = data["booked_min"]
    if capacity:
        load = round(100 * booked / capacity)
        lines.append(
            f"📈 Загрузка: {booked / 60:.1f} ч из {capacity / 60:.0f} ч ({load}%)"
        )
        if data["future"]:
            free = max(capacity - booked, 0)
            lines.append(f"🟢 Свободно: {free / 60:.1f} ч")
    if not data["future"]:
        lines.append(f"❌ Отменено записей: {data['cancelled']}")

    if data["top"]:
        lines += ["", "🏆 <b>Популярные услуги:</b>"]
        for number, (name, count, revenue) in enumerate(data["top"], start=1):
            lines.append(f"{number}. {escape(name)}: {count} ({revenue} BYN)")

    if not data["future"]:
        lines += [
            "",
            "<i>Все прошедшие записи считаются состоявшимися: "
            "неявки бот не отслеживает.</i>",
        ]
    return "\n".join(lines)