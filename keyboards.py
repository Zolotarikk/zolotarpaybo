from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💆 Записаться")],
        [
            KeyboardButton(text="📋 Мои записи"),
            KeyboardButton(text="💰 Услуги и цены"),
        ],
        [KeyboardButton(text="📖 О нас"), KeyboardButton(text="📞 Контакты")],
    ],
    resize_keyboard=True,
)