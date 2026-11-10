import logging

import config

logger = logging.getLogger(__name__)


async def send_to_admin(bot, text: str):
    """Отправляет сообщение администратору. Сбой не должен ломать основное действие."""
    if not config.ADMIN_ID:
        logger.warning("ADMIN_ID не задан, уведомление не отправлено")
        return
    try:
        await bot.send_message(config.ADMIN_ID, text)
    except Exception:
        logger.exception("Не удалось отправить уведомление администратору")


async def send_to_user(bot, user_id: int, text: str) -> bool:
    """Отправляет сообщение клиенту. Возвращает True, если оно доставлено."""
    try:
        await bot.send_message(user_id, text)
        return True
    except Exception:
        # Например, клиент заблокировал бота
        logger.exception("Не удалось отправить сообщение пользователю %s", user_id)
        return False