"""Language selection — first start and settings."""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.handlers.welcome import send_welcome_for_user
from bot.i18n import LOCALE_LABELS, SUPPORTED_LOCALES, get_user_locale, normalize_locale, t
from database.engine import async_session
from database.repository import SubscriptionRepo, UserRepo

router = Router()
logger = logging.getLogger(__name__)
config = Config()


async def _edit_or_send_welcome(call: CallbackQuery, welcome: str, kb) -> None:
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=welcome, reply_markup=kb)
        else:
            await call.message.edit_text(text=welcome, reply_markup=kb)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return
        logger.warning("edit welcome failed for %s: %s", call.from_user.id, e)
        await call.message.answer(welcome, reply_markup=kb)


def language_keyboard(current: str | None = None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for code in SUPPORTED_LOCALES:
        label = LOCALE_LABELS[code]
        if current == code:
            label = f"✓ {label}"
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"set_locale:{code}"),
        )
    builder.row(
        InlineKeyboardButton(
            text=t(current or "ru", "menu.back"),
            callback_data="main",
        ),
    )
    return builder


async def prompt_language_choice(message, locale: str = "ru") -> None:
    text = (
        f"{t(locale, 'lang.choose_title')}\n\n"
        f"{t(locale, 'lang.choose_desc')}"
    )
    await message.answer(text, reply_markup=language_keyboard().as_markup())


@router.callback_query(F.data.startswith("set_locale:"))
async def cb_set_locale(call: CallbackQuery):
    code = normalize_locale(call.data.split(":", 1)[1])
    if code not in SUPPORTED_LOCALES:
        await call.answer("Invalid locale", show_alert=True)
        return

    try:
        async with async_session() as session:
            user_repo = UserRepo(session)
            sub_repo = SubscriptionRepo(session)
            user = await user_repo.get_by_telegram_id(call.from_user.id)
            if not user:
                await call.answer(t("ru", "account.not_found"), show_alert=True)
                return

            current = user.preferred_locale
            if current == code:
                await call.answer(t(code, "lang.saved", label=LOCALE_LABELS[code]))
                return

            await user_repo.set_preferred_locale(user, code)
            active_sub = await sub_repo.get_active(call.from_user.id)
            all_subs = await sub_repo.get_all_for_user(call.from_user.id)

        has_subscription = active_sub is not None
        is_new = len(all_subs) == 0
        label = LOCALE_LABELS[code]
        await call.answer(t(code, "lang.saved", label=label))

        welcome, kb = send_welcome_for_user(
            call.from_user.first_name,
            locale=code,
            has_subscription=has_subscription,
            is_new_user=is_new,
        )
        await _edit_or_send_welcome(call, welcome, kb)
    except Exception as e:
        logger.exception("set_locale failed for %s: %s", call.from_user.id, e)
        await call.answer(t("ru", "errors.generic"), show_alert=True)


@router.callback_query(F.data == "choose_language")
async def cb_choose_language(call: CallbackQuery, db_user=None):
    locale = get_user_locale(db_user, call.from_user.language_code)
    text = (
        f"{t(locale, 'lang.settings_title')}\n\n"
        f"{t(locale, 'lang.settings_desc')}"
    )

    async with async_session() as session:
        user_repo = UserRepo(session)
        user = await user_repo.get_by_telegram_id(call.from_user.id)
        current = user.preferred_locale if user else locale

    kb = language_keyboard(current).as_markup()
    if call.message.photo:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    else:
        await call.message.edit_text(text=text, reply_markup=kb)
    await call.answer()
