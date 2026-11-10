import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Telegram ID администратора (владельца студии)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# --- Расписание студии (демо) ---
TIMEZONE_OFFSET_HOURS = 3  # Беларусь: UTC+3 круглый год
WORK_START_HOUR = 10
WORK_END_HOUR = 20
WORK_WEEKDAYS = {0, 1, 2, 3, 4, 5}  # 0 = понедельник ... 5 = суббота
SLOT_STEP_MIN = 30  # шаг сетки времени, минут
BOOKING_DAYS_AHEAD = 14  # на сколько дней вперёд можно записаться
MIN_NOTICE_MIN = 60  # минимум за сколько минут до начала можно записаться
CANCEL_MIN_HOURS = 0  # отмена возможна не позднее чем за столько часов