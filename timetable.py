from datetime import date, datetime, time, timedelta, timezone

import config

TZ = timezone(timedelta(hours=config.TIMEZONE_OFFSET_HOURS))


def now_local() -> datetime:
    """Текущее время студии (без часового пояса, для простого сравнения)."""
    return datetime.now(TZ).replace(tzinfo=None)


def available_dates() -> list[date]:
    """Ближайшие рабочие дни, на которые можно записаться."""
    today = now_local().date()
    days = []
    for offset in range(config.BOOKING_DAYS_AHEAD):
        day = today + timedelta(days=offset)
        if day.weekday() in config.WORK_WEEKDAYS:
            days.append(day)
    return days


def free_slots(
    day: date,
    duration_min: int,
    busy: list[tuple[datetime, datetime]],
) -> list[datetime]:
    """Свободное время начала сеанса на выбранный день."""
    slots = []
    step = timedelta(minutes=config.SLOT_STEP_MIN)
    duration = timedelta(minutes=duration_min)
    start = datetime.combine(day, time(config.WORK_START_HOUR))
    day_end = datetime.combine(day, time(config.WORK_END_HOUR))
    earliest = now_local() + timedelta(minutes=config.MIN_NOTICE_MIN)

    while start + duration <= day_end:
        end = start + duration
        in_future = start >= earliest
        is_free = all(end <= b_start or start >= b_end for b_start, b_end in busy)
        if in_future and is_free:
            slots.append(start)
        start += step
    return slots