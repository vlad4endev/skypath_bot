"""
Обработчик /start — приветствие, регистрация, главное меню
"""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.filters import CommandObject

from bot.config import Config
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


def main_keyboard(has_subscription: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_miniapp_available():
        label = "👤 Личный кабинет" if has_subscription else "🚀 Получить VPN"
        builder.row(cabinet_button(label))
    else:
        builder.row(
            InlineKeyboardButton(text="🔑 Получить VPN", callback_data="plans"),
        )

    if has_subscription:
        builder.row(
            InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_vpn"),
            InlineKeyboardButton(text="👤 Аккаунт", callback_data="account"),
        )

    builder.row(
        InlineKeyboardButton(text="💬 Отзывы", callback_data="reviews"),
        InlineKeyboardButton(text="😎 О нас", callback_data="about"),
    )
    builder.row(
        InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL),
        InlineKeyboardButton(text="📄 Инфо", callback_data="info"),
    )
    return builder.as_markup()


async def _send_welcome(
    message: Message,
    text: str,
    kb: InlineKeyboardMarkup,
    *,
    has_subscription: bool = False,
) -> None:
    """Отправка приветствия: сначала текст (надёжно), фото — опционально."""
    try:
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.warning("Welcome with keyboard failed: %s", e)
        try:
            await message.answer(
                text,
                reply_markup=main_keyboard(has_subscription=has_subscription),
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


WELCOME_TEXT = f"""
👋 Добро пожаловать в <b>{config.BRAND_NAME}</b>!

🛡 Твой личный помощник для безопасного и свободного интернета.

<b>Что ты получаешь:</b>
• 🔒 Надёжная защита данных в любой сети
• ⚡️ Безлимитная скорость без ограничений  
• 📺 YouTube в 4K, стриминг без буферизации
• 📱 До 10 устройств одновременно
• 🌍 Серверы: Россия, США, Германия, Нидерланды, Казахстан
• 💰 Честная цена — от 250 руб/месяц

📱 Тарифы, оплата и личный кабинет — в приложении
"""


def _parse_referrer_id(args: str | None) -> int | None:
    """/start ref_123456789 или /start 123456789"""
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
async def cmd_start(message: Message, command: CommandObject):
    user = message.from_user
    referrer_id = _parse_referrer_id(command.args)

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        db_user, is_new = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )

        if referrer_id and referrer_id != user.id:
            await user_repo.set_referrer_if_empty(db_user, referrer_id)

        active_sub = await sub_repo.get_active(user.id)

    if is_new:
        welcome = WELCOME_TEXT + "\n\n🎁 <b>Для тебя — 3 дня бесплатно!</b> Открой приложение 👇"
    else:
        name = user.first_name or "друг"
        welcome = f"👋 С возвращением, <b>{name}</b>!\n" + WELCOME_TEXT

    kb = main_keyboard(has_subscription=active_sub is not None)

    await _send_welcome(
        message,
        welcome,
        kb,
        has_subscription=active_sub is not None,
    )


@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery):
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        active_sub = await sub_repo.get_active(call.from_user.id)

    kb = main_keyboard(has_subscription=active_sub is not None)
    await call.message.edit_caption(
        caption=WELCOME_TEXT,
        reply_markup=kb,
    ) if call.message.photo else await call.message.edit_text(
        text=WELCOME_TEXT,
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery):
    text = f"""
😎 <b>О нас — {config.BRAND_NAME}</b>

Мы строим сервис, которому можно доверять.

<b>Наши серверы:</b>
🇷🇺 Москва — высокая скорость
🇺🇸 Нью-Йорк — YouTube, стриминг
🇩🇪 Франкфурт — EU контент  
🇳🇱 Амстердам — приватность
🇰🇿 Алматы — Центральная Азия

<b>Технологии:</b>
• VLESS + XTLS-Reality (необнаруживаем)
• 3X-UI панель, обновления каждый день

<b>Контакты:</b>
• Поддержка: @SkyPathsupport
• Канал: @SkyPathVPN
"""
    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        builder.row(cabinet_button())
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "info")
async def cb_info(call: CallbackQuery):
    text = f"""
📄 <b>Информация о {config.BRAND_NAME}</b>

<b>Тарифы:</b>
🆓 Пробный — 3 дня бесплатно, 1 устройство
💎 Базовый — от 250 руб/мес, 3 устройства
🚀 Мульти — от 350 руб/мес, 5 устройств
👑 Супер — от 450 руб/мес, 10 устройств

<b>Все тарифы включают:</b>
✅ Безлимитный трафик
✅ Все сервера
✅ Поддержка 24/7
✅ Инструкции для всех платформ

<b>Платёж:</b>
💳 Банковская карта (Platega)
₿ Крипто (USDT, BTC, ETH)
"""
    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        builder.row(cabinet_button("📲 Открыть приложение"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "reviews")
async def cb_reviews(call: CallbackQuery):
    text = """
💬 <b>Отзывы пользователей</b>

⭐️⭐️⭐️⭐️⭐️ <b>Максим К.</b>
«Пользуюсь 8 месяцев. YouTube летает, Netflix работает. Отличный сервис!»

⭐️⭐️⭐️⭐️⭐️ <b>Анна М.</b>
«Настроила за 5 минут по инструкции. Всё работает на iPhone и MacBook»

⭐️⭐️⭐️⭐️⭐️ <b>Дмитрий П.</b>
«Скорость не падает даже в 4К. Рекомендую всем!»

⭐️⭐️⭐️⭐️⭐️ <b>Ольга Н.</b>
«Поддержка ответила за 10 минут. Помогли настроить. Спасибо!»

<i>Более 2000 довольных клиентов 🚀</i>
"""
    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        builder.row(cabinet_button("📲 Попробовать"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()
