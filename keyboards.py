from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

import config

ADMIN_BUTTON = "⚙️ Админ-панель"


def main_menu_for(user_id: int) -> ReplyKeyboardMarkup:
    """Главное меню. Администратор видит дополнительную кнопку."""
    rows = [
        [KeyboardButton(text="💆 Записаться")],
        [
            KeyboardButton(text="📋 Мои записи"),
            KeyboardButton(text="💰 Услуги и цены"),
        ],
        [KeyboardButton(text="📖 О нас"), KeyboardButton(text="📞 Контакты")],
    ]
    if user_id == config.ADMIN_ID:
        rows.append([KeyboardButton(text=ADMIN_BUTTON)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)