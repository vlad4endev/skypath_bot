"""
Middleware — антиспам throttling
"""
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self.cache = TTLCache(maxsize=10_000, ttl=rate_limit)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = None
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, Update):
            user_id = (
                event.message.from_user.id if event.message else
                event.callback_query.from_user.id if event.callback_query else
                None
            )

        if user_id:
            if user_id in self.cache:
                if isinstance(event, Update) and event.callback_query:
                    try:
                        await event.callback_query.answer()
                    except Exception:
                        pass
                return
            self.cache[user_id] = True

        return await handler(event, data)
