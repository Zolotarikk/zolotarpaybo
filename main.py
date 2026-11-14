import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent

import config
import database
import reminders
from handlers import (
    admin,
    admin_blocks,
    admin_stats,
    admin_export,
    booking,
    calendar_ics,
    common,
    fallback,
    my_bookings,
    reschedule,
)
from middlewares import UserTrackingMiddleware

logger = logging.getLogger(__name__)


def setup_logging():
    """Журнал с временем событий: в окно терминала и в файл clients/<имя>/bot.log."""
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    log_file = RotatingFileHandler(
        config.CLIENT_DIR / "bot.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    log_file.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[console, log_file])


async def setup_commands(bot: Bot):
    """Меню команд рядом с полем ввода. Сбой здесь не должен мешать запуску."""
    try:
        await bot.set_my_commands(
            [BotCommand(command="start", description="Главное меню")]
        )
        if config.ADMIN_ID:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Главное меню"),
                    BotCommand(command="admin", description="Админ-панель"),
                    BotCommand(command="digest", description="Сводка на сегодня"),
                ],
                scope=BotCommandScopeChat(chat_id=config.ADMIN_ID),
            )
    except Exception:
        logger.warning("Не удалось настроить меню команд", exc_info=True)


def register_error_handler(dp: Dispatcher):
    """Единое место обработки ошибок: пользователь не видит «тишины»."""

    @dp.error()
    async def on_error(event: ErrorEvent):
        error = event.exception
        query = event.update.callback_query
        message = event.update.message

        # Двойное нажатие на ту же кнопку: Telegram не даёт изменить сообщение
        # на такое же. Это не ошибка, просто игнорируем
        if isinstance(error, TelegramBadRequest) and "message is not modified" in str(
            error
        ):
            if query:
                try:
                    await query.answer()
                except Exception:
                    pass
            return True

        logger.error("Необработанная ошибка", exc_info=error)
        text = "Что-то пошло не так. Попробуйте ещё раз или нажмите /start."
        try:
            if query:
                await query.answer(text, show_alert=True)
            elif message:
                await message.answer(text)
        except Exception:
            logger.warning("Не удалось сообщить пользователю об ошибке")
        return True


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError(
            f"Не найден BOT_TOKEN. Проверь файл {config.CLIENT_DIR / '.env'}"
        )
    setup_logging()
    logger.info("Запуск клиента: %s", config.CLIENT)
    await database.init_db()
    await database.sync_services(config.SERVICES)
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    register_error_handler(dp)

    # Запоминаем клиента при любом его действии
    tracker = UserTrackingMiddleware()
    dp.message.outer_middleware(tracker)
    dp.callback_query.outer_middleware(tracker)

    # Порядок важен: fallback должен идти последним
    dp.include_routers(
        common.router,
        booking.router,
        my_bookings.router,
        admin.router,
        admin_blocks.router,
        admin_stats.router,
        admin_export.router,
        reschedule.router,
        calendar_ics.router,
        fallback.router,
    )
    await setup_commands(bot)
    # Фоновая задача напоминаний работает параллельно с ботом
    reminders_task = asyncio.create_task(reminders.reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")