"""Shared welcome text and main menu keyboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.i18n import t
from bot.keyboards.webapp import (
    is_cabinet_available,
    is_miniapp_available,
    open_app_button,
    register_app_button,
)

config = Config()


def main_keyboard(
    has_subscription: bool = False,
    *,
    web_registered: bool = False,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_cabinet_available():
        if not web_registered:
            builder.row(register_app_button(locale=locale))
            builder.row(open_app_button(t(locale, "menu.open_app"), locale=locale))
        elif has_subscription:
            builder.row(open_app_button(t(locale, "menu.cabinet"), locale=locale))
        else:
            builder.row(open_app_button(t(locale, "menu.buy_vpn"), path="plans", locale=locale))
    elif is_miniapp_available():
        from bot.keyboards.webapp import buy_vpn_button, cabinet_button

        if has_subscription:
            builder.row(cabinet_button(t(locale, "menu.cabinet"), locale=locale))
        else:
            builder.row(buy_vpn_button(t(locale, "menu.buy_vpn"), locale=locale))

    if has_subscription:
        builder.row(
            InlineKeyboardButton(text=t(locale, "menu.my_keys"), callback_data="my_vpn"),
            InlineKeyboardButton(text=t(locale, "menu.account"), callback_data="account"),
        )

    builder.row(
        InlineKeyboardButton(text=t(locale, "menu.reviews"), callback_data="reviews"),
        InlineKeyboardButton(text=t(locale, "menu.about"), callback_data="about"),
    )
    builder.row(
        InlineKeyboardButton(text=t(locale, "menu.support"), url=config.SUPPORT_URL),
        InlineKeyboardButton(text=t(locale, "menu.info"), callback_data="info"),
    )
    builder.row(
        InlineKeyboardButton(text="🌍 " + t(locale, "app.language"), callback_data="choose_language"),
    )
    return builder.as_markup()


def welcome_text_new(locale: str) -> str:
    return t(locale, "welcome.new", brand=config.BRAND_NAME)


def welcome_text_returning(name: str, *, has_subscription: bool, locale: str) -> str:
    if has_subscription:
        return t(locale, "welcome.returning_sub", name=name)
    return t(locale, "welcome.returning", name=name)


def send_welcome_for_user(
    first_name: str | None,
    *,
    locale: str,
    has_subscription: bool,
    is_new_user: bool = False,
    web_registered: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    if is_new_user:
        welcome = welcome_text_new(locale) + t(locale, "welcome.new_trial")
    else:
        name = first_name or t(locale, "welcome.friend")
        welcome = welcome_text_returning(name, has_subscription=has_subscription, locale=locale)
    kb = main_keyboard(
        has_subscription=has_subscription,
        web_registered=web_registered,
        locale=locale,
    )
    return welcome, kb
