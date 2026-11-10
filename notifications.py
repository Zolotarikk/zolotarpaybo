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