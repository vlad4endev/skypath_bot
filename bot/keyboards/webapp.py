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


def miniapp_url(tab: str | None = None) -> str:
    url = config.MINI_APP_URL
    if not tab:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tab={tab}"


def miniapp_payment_return_url(order_id: str, outcome: str = "success") -> str:
    """URL возврата в Mini App после оплаты Platega (success / failed)."""
    base = config.MINI_APP_URL.rstrip("/")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}tab=home&payment={outcome}&order_id={order_id}"


def cabinet_button(text: str | None = None) -> InlineKeyboardButton:
    label = text or f"🌐 {config.BRAND_NAME}"
    return InlineKeyboardButton(
        text=label,
        web_app=WebAppInfo(url=miniapp_url()),
    )


def buy_vpn_button(text: str = "💳 Купить VPN") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        web_app=WebAppInfo(url=miniapp_url("plans")),
    )
