from aiogram import BaseMiddleware

import database


class UserTrackingMiddleware(BaseMiddleware):
    """Сохраняет пользователя при любом его действии и обновляет имя и username."""

    def __init__(self):
        # Кэш, чтобы не писать в базу при каждом нажатии кнопки
        self._seen: dict[int, tuple] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not user.is_bot:
            snapshot = (user.full_name, user.username)
            if self._seen.get(user.id) != snapshot:
                await database.add_user(user.id, user.full_name, user.username)
                self._seen[user.id] = snapshot
        return await handler(event, data)