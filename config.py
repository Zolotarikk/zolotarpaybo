import argparse
import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# Какого клиента запускаем: python main.py --client demo
# (или переменная окружения CLIENT; по умолчанию demo)
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--client", default=os.getenv("CLIENT", "demo"))
CLIENT = _parser.parse_known_args()[0].client
CLIENT_DIR = BASE_DIR / "clients" / CLIENT

if not CLIENT_DIR.is_dir():
    raise SystemExit(f"Папка клиента не найдена: {CLIENT_DIR}")

# Секреты (токен бота, ID владельца) лежат в .env внутри папки клиента
load_dotenv(CLIENT_DIR / ".env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Остальные настройки лежат в clients/<имя>/settings.toml
with open(CLIENT_DIR / "settings.toml", "rb") as _file:
    _settings = tomllib.load(_file)

_studio = _settings["studio"]
STUDIO_NAME = _studio["name"]
STUDIO_ABOUT = _studio["about"]
STUDIO_ADDRESS = _studio["address"]
STUDIO_PHONE = _studio["phone"]
STUDIO_HOURS = _studio["hours_text"]

_schedule = _settings["schedule"]
TIMEZONE_OFFSET_HOURS = _schedule["timezone_offset_hours"]
WORK_START_HOUR = _schedule["work_start_hour"]
WORK_END_HOUR = _schedule["work_end_hour"]
WORK_WEEKDAYS = set(_schedule["work_weekdays"])
SLOT_STEP_MIN = _schedule["slot_step_min"]
BOOKING_DAYS_AHEAD = _schedule["booking_days_ahead"]
MIN_NOTICE_MIN = _schedule["min_notice_min"]

_rules = _settings["rules"]
CANCEL_MIN_HOURS = _rules["cancel_min_hours"]
REMIND_FIRST_HOURS = _rules["remind_first_hours"]
REMIND_SECOND_HOURS = _rules["remind_second_hours"]

# Список услуг: [{"name": ..., "duration_min": ..., "price": ...}, ...]
SERVICES = _settings["services"]