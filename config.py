import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Telegram ID администратора (владельца студии). Заполним чуть позже.
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))