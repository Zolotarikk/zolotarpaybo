"""Заполняет демо-базу тестовыми записями за последние 30 дней (только для demo)."""

import asyncio
import random
from datetime import datetime, time, timedelta

import aiosqlite

import config
import database
import timetable

FAKE_USER_START = 900_000_001  # тестовые клиенты имеют такие номера


async def main():
    if config.CLIENT != "demo":
        raise SystemExit("Скрипт разрешён только для клиента demo")
    await database.init_db()
    await database.sync_services(config.SERVICES)
    services = await database.get_services()
    today = timetable.now_local().date()
    random.seed(7)

    async with aiosqlite.connect(database.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE user_id >= ?", (FAKE_USER_START,)
        )
        if (await cursor.fetchone())[0] > 0:
            raise SystemExit("Тестовые записи уже добавлены")

        fake_users = range(FAKE_USER_START, FAKE_USER_START + 12)
        for number, user_id in enumerate(fake_users, start=1):
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, full_name, phone) "
                "VALUES (?, ?, ?)",
                (user_id, f"Тест Клиент {number}", f"+3752900{number:05d}"),
            )

        created = 0
        for days_ago in range(1, 31):
            day = today - timedelta(days=days_ago)
            if day.weekday() not in config.WORK_WEEKDAYS:
                continue
            minute = config.WORK_START_HOUR * 60
            for _ in range(random.randint(1, 5)):
                minute += random.choice([0, 30, 60])
                service_id, _name, duration, price = random.choice(services)
                if minute + duration > config.WORK_END_HOUR * 60:
                    break
                start = datetime.combine(day, time(minute // 60, minute % 60))
                end = start + timedelta(minutes=duration)
                status = "cancelled" if random.random() < 0.12 else "active"
                await db.execute(
                    "INSERT INTO bookings (user_id, service_id, start_at, end_at, "
                    "status, reminded_24h, reminded_2h, price) "
                    "VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
                    (
                        random.choice(list(fake_users)),
                        service_id,
                        start.strftime(database.DT_FORMAT),
                        end.strftime(database.DT_FORMAT),
                        status,
                        price,
                    ),
                )
                minute += duration
                created += 1
        await db.commit()
    print(f"Добавлено тестовых записей: {created}")


if __name__ == "__main__":
    asyncio.run(main())