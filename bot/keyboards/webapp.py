"""Кнопки открытия Telegram Mini App."""
from aiogram.types import InlineKeyboardButton, WebAppInfo

from bot.config import Config

config = Config()

_PLACEHOLDER_HOSTS = ("your-domain.com", "example.com", "localhost")


def is_miniapp_available() -> bool:
    url = config.MINI_APP_URL
    if not url or not url.startswith("https://"):
        return False
    host = url.split("/")[2].split(":")[0].lower()
    return host not in _PLACEHOLDER_HOSTS


def cabinet_button(text: str | None = None) -> InlineKeyboardButton:
    label = text or f"🌐 {config.BRAND_NAME}"
    return InlineKeyboardButton(
        text=label,
        web_app=WebAppInfo(url=config.MINI_APP_URL),
    )
