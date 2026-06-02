"""
Middleware — автоматическая регистрация пользователей
"""
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database.engine import async_session
from database.repository import UserRepo


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        if user and not user.is_bot:
            async with async_session() as session:
                user_repo = UserRepo(session)
                db_user, is_new = await user_repo.get_or_create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code,
                )
                data["db_user"] = db_user
                data["is_new_user"] = is_new

        return await handler(event, data)
