"""
Обработчик /start — приветствие, регистрация, главное меню
"""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.handlers.locale_handler import prompt_language_choice
from bot.handlers.welcome import main_keyboard, send_welcome_for_user
from bot.i18n import get_user_locale, t
from bot.keyboards.webapp import cabinet_button, is_miniapp_available
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo

router = Router()
logger = logging.getLogger(__name__)
config = Config()

_PLACEHOLDER_HOSTS = ("your-domain.com", "example.com", "localhost")


def _is_valid_https_url(url: str | None) -> bool:
    if not url or not url.startswith("https://"):
        return False
    host = url.split("/")[2].split(":")[0].lower()
    return host not in _PLACEHOLDER_HOSTS


async def _send_welcome(
    message: Message,
    text: str,
    kb: InlineKeyboardMarkup,
    *,
    has_subscription: bool = False,
    locale: str = "ru",
) -> None:
    try:
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.warning("Welcome with keyboard failed: %s", e)
        try:
            await message.answer(
                text,
                reply_markup=main_keyboard(has_subscription=has_subscription, locale=locale),
            )
        except Exception as e2:
            logger.error("Welcome fallback failed: %s", e2)
            await message.answer(text)

    photo_url = config.WELCOME_PHOTO_URL.strip()
    if photo_url and _is_valid_https_url(photo_url):
        try:
            await message.answer_photo(photo=photo_url)
        except Exception as e:
            logger.warning("Welcome photo failed: %s", e)


def _parse_referrer_id(args: str | None) -> int | None:
    if not args:
        return None
    raw = args.strip()
    if raw.startswith("ref_"):
        raw = raw[4:]
    try:
        return int(raw)
    except ValueError:
        return None


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    is_new_user: bool = False,
    db_user=None,
):
    user = message.from_user
    referrer_id = _parse_referrer_id(command.args)

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        db_user, _ = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )

        if referrer_id and referrer_id != user.id:
            await user_repo.set_referrer_if_empty(db_user, referrer_id)

        active_sub = await sub_repo.get_active(user.id)

    has_subscription = active_sub is not None

    if is_new_user and not db_user.preferred_locale:
        await prompt_language_choice(message)
        return

    if not db_user.preferred_locale:
        async with async_session() as session:
            user_repo = UserRepo(session)
            fresh = await user_repo.get_by_telegram_id(user.id)
            if fresh:
                await user_repo.ensure_locale_from_telegram(fresh)
                db_user = fresh

    locale = get_user_locale(db_user, user.language_code)
    welcome, kb = send_welcome_for_user(
        user.first_name,
        locale=locale,
        has_subscription=has_subscription,
        is_new_user=is_new_user,
    )

    await _send_welcome(
        message,
        welcome,
        kb,
        has_subscription=has_subscription,
        locale=locale,
    )


@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, db_user=None):
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        active_sub = await sub_repo.get_active(call.from_user.id)

    has_subscription = active_sub is not None
    locale = get_user_locale(db_user, call.from_user.language_code)
    welcome, kb = send_welcome_for_user(
        call.from_user.first_name,
        locale=locale,
        has_subscription=has_subscription,
    )
    if call.message.photo:
        await call.message.edit_caption(caption=welcome, reply_markup=kb)
    else:
        await call.message.edit_text(text=welcome, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery, db_user=None):
    locale = get_user_locale(db_user, call.from_user.language_code)
    text = t(locale, "about.text", brand=config.BRAND_NAME)
    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        builder.row(cabinet_button(locale=locale))
    builder.row(InlineKeyboardButton(text=t(locale, "menu.back"), callback_data="main"))

    if call.message.photo:
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup())
    else:
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "info")
async def cb_info(call: CallbackQuery, db_user=None):
    locale = get_user_locale(db_user, call.from_user.language_code)
    text = t(locale, "info.text", brand=config.BRAND_NAME)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t(locale, "menu.terms"), url=config.TERMS_URL),
    )
    builder.row(
        InlineKeyboardButton(text=t(locale, "menu.privacy"), url=config.PRIVACY_URL),
    )
    if is_miniapp_available():
        builder.row(cabinet_button(t(locale, "menu.open_app"), locale=locale))
    builder.row(InlineKeyboardButton(text=t(locale, "menu.back"), callback_data="main"))

    if call.message.photo:
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup())
    else:
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "reviews")
async def cb_reviews(call: CallbackQuery, db_user=None):
    locale = get_user_locale(db_user, call.from_user.language_code)
    text = t(locale, "reviews.text")
    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        builder.row(cabinet_button(t(locale, "menu.try_app"), locale=locale))
    builder.row(InlineKeyboardButton(text=t(locale, "menu.back"), callback_data="main"))

    if call.message.photo:
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup())
    else:
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()
