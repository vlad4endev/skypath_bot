"""Fetch Telegram profile data via Bot API."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


async def fetch_telegram_profile(bot: Bot, telegram_id: int) -> dict[str, Any]:
    """Load live profile from Telegram. Returns partial data on errors."""
    result: dict[str, Any] = {
        "available": False,
        "telegram_id": telegram_id,
        "first_name": None,
        "last_name": None,
        "username": None,
        "bio": None,
        "language_code": None,
        "is_premium": None,
        "has_photo": False,
        "photo_file_id": None,
        "profile_link": None,
        "error": None,
    }

    try:
        chat = await bot.get_chat(telegram_id)
        result["available"] = True
        result["first_name"] = chat.first_name
        result["last_name"] = chat.last_name
        result["username"] = chat.username
        result["bio"] = getattr(chat, "bio", None)
        result["language_code"] = getattr(chat, "language_code", None)
        result["is_premium"] = getattr(chat, "is_premium", None)
        if chat.username:
            result["profile_link"] = f"https://t.me/{chat.username}"
        else:
            result["profile_link"] = f"tg://user?id={telegram_id}"
    except TelegramAPIError as e:
        logger.info("getChat failed for %s: %s", telegram_id, e)
        result["error"] = str(e.message if hasattr(e, "message") else e)

    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if photos.photos:
            largest = photos.photos[0][-1]
            result["has_photo"] = True
            result["photo_file_id"] = largest.file_id
    except TelegramAPIError as e:
        logger.info("getUserProfilePhotos failed for %s: %s", telegram_id, e)
        if not result["error"]:
            result["error"] = str(e.message if hasattr(e, "message") else e)

    return result


async def download_profile_photo(bot: Bot, telegram_id: int) -> tuple[bytes, str] | None:
    """Download profile photo bytes. Returns (data, content_type) or None."""
    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if not photos.photos:
            return None
        file_id = photos.photos[0][-1].file_id
        file = await bot.get_file(file_id)
        if not file.file_path:
            return None
        from io import BytesIO

        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        data = buf.getvalue()
        if not data:
            return None
        ext = (file.file_path or "").rsplit(".", 1)[-1].lower()
        ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
            ext, "image/jpeg"
        )
        return data, ctype
    except TelegramAPIError as e:
        logger.info("download profile photo failed for %s: %s", telegram_id, e)
        return None
