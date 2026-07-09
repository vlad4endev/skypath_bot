"""Ссылки на веб-приложение (кабинет) и legacy Mini App."""
from aiogram.types import InlineKeyboardButton, WebAppInfo

from bot.config import Config

config = Config()

_PLACEHOLDER_HOSTS = ("your-domain.com", "example.com", "localhost")


def _cabinet_base() -> str:
    return config.CABINET_URL.rstrip("/")


def is_miniapp_available() -> bool:
    url = config.MINI_APP_URL
    if not url or not url.startswith("https://"):
        return False
    host = url.split("/")[2].split(":")[0].lower()
    return host not in _PLACEHOLDER_HOSTS


def is_cabinet_available() -> bool:
    url = _cabinet_base()
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


def cabinet_login_url() -> str:
    return f"{_cabinet_base()}/login"


def cabinet_register_url() -> str:
    return f"{_cabinet_base()}/register"


def cabinet_app_url(path: str = "") -> str:
    base = f"{_cabinet_base()}/app"
    if not path:
        return base
    return f"{base}/{path.lstrip('/')}"


def cabinet_payment_return_url(order_id: str, outcome: str = "success") -> str:
    base = cabinet_app_url()
    return f"{base}?payment={outcome}&order_id={order_id}"


def miniapp_payment_return_url(order_id: str, outcome: str = "success") -> str:
    base = config.MINI_APP_URL.rstrip("/")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}tab=home&payment={outcome}&order_id={order_id}"


def open_app_button(text: str | None = None, *, path: str = "", locale: str = "ru") -> InlineKeyboardButton:
    from bot.i18n import t

    label = text or t(locale, "menu.open_app")
    return InlineKeyboardButton(text=label, url=cabinet_app_url(path))


def register_app_button(text: str | None = None, locale: str = "ru") -> InlineKeyboardButton:
    from bot.i18n import t

    label = text or t(locale, "menu.register_app")
    return InlineKeyboardButton(text=label, url=cabinet_register_url())


def web_cabinet_button(text: str | None = None, locale: str = "ru") -> InlineKeyboardButton:
    from bot.i18n import t

    label = text or t(locale, "menu.open_app")
    return InlineKeyboardButton(text=label, url=cabinet_login_url())


# Legacy Mini App (не используется как основной канал)
def cabinet_button(text: str | None = None, locale: str = "ru") -> InlineKeyboardButton:
    return open_app_button(text, locale=locale)


def buy_vpn_button(text: str | None = None, locale: str = "ru") -> InlineKeyboardButton:
    from bot.i18n import t

    label = text or t(locale, "menu.buy_vpn")
    return open_app_button(label, path="plans", locale=locale)
