from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import database
from notifications import send_to_admin
from ui import client_html

router = Router()

# Кнопки главного меню: их нельзя принимать за комментарий к отзыву
MENU_TEXTS = {
    "💆 Записаться",
    "📋 Мои записи",
    "💰 Услуги и цены",
    "📖 О нас",
    "📞 Контакты",
    "⚙️ Админ-панель",
}


class ReviewStates(StatesGroup):
    waiting_comment = State()


@router.callback_query(F.data.startswith("rv:"))
async def rate(callback: CallbackQuery, state: FSMContext):
    _, booking_id, rating = callback.data.split(":")
    booking_id, rating = int(booking_id), int(rating)
    if not 1 <= rating <= 5:
        await callback.answer()
        return

    booking = await database.get_booking(booking_id)
    # Оценить можно только свою активную запись
    if (
        booking is None
        or booking[1] != callback.from_user.id
        or booking[6] != "active"
    ):
        await callback.answer("Запись не найдена", show_alert=True)
        return
    name = booking[2]

    if not await database.save_review(booking_id, callback.from_user.id, rating):
        await callback.answer("Вы уже оставили оценку. Спасибо!", show_alert=True)
        return

    stars = "⭐" * rating
    if rating >= config.REVIEW_POSITIVE_FROM:
        text = f"Спасибо за оценку {stars}! Рады, что вам понравилось 🙌"
        keyboard = None
        # Заглушка: пока у студии нет публичной страницы, ссылки нет.
        # Когда она появится, её нужно вписать в settings.toml (public_url)
        if config.REVIEW_PUBLIC_URL:
            text += "\nЕсли не сложно, поделитесь впечатлением и в отзывах: это очень помогает нам."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⭐ Оставить отзыв", url=config.REVIEW_PUBLIC_URL
                        )
                    ]
                ]
            )
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return

    # Низкая оценка: просим рассказать, что не так, и сразу предупреждаем владельца
    await state.set_state(ReviewStates.waiting_comment)
    await state.update_data(booking_id=booking_id)
    await callback.message.edit_text(
        f"Спасибо за честную оценку {stars}. Нам жаль, что вы остались недовольны 😔\n\n"
        "Расскажите, что пошло не так: напишите одним сообщением, "
        "и мы передадим это владельцу.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Пропустить", callback_data="rvskip")]
            ]
        ),
    )
    await callback.answer()

    user = callback.from_user
    phone = await database.get_phone(user.id)
    await send_to_admin(
        callback.bot,
        f"⚠️ <b>Низкая оценка: {stars}</b>\n"
        f"Запись №{booking_id}, {escape(name)}\n"
        f"👤 {client_html(user.id, user.full_name, user.username, phone)}\n\n"
        "Стоит связаться с клиентом и разобраться.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "rvskip")
async def skip_comment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Спасибо за оценку! Мы обязательно её учтём.")
    await callback.answer()


@router.message(
    ReviewStates.waiting_comment,
    F.text,
    ~F.text.startswith("/"),
    F.text.not_in(MENU_TEXTS),
)
async def comment_received(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    booking_id = data.get("booking_id")
    if booking_id is None:
        await message.answer("Спасибо!")
        return

    comment = message.text.strip()[:500]
    await database.set_review_comment(booking_id, comment)
    await message.answer(
        "Спасибо, что рассказали. Мы передали ваш отзыв владельцу и постараемся "
        "стать лучше 🙏"
    )

    user = message.from_user
    phone = await database.get_phone(user.id)
    await send_to_admin(
        message.bot,
        f"💬 <b>Комментарий к оценке по записи №{booking_id}</b>\n"
        f"👤 {client_html(user.id, user.full_name, user.username, phone)}\n\n"
        f"«{escape(comment)}»",
        parse_mode="HTML",
    )