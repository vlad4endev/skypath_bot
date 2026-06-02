"""
Обработчик /start — приветствие, регистрация, главное меню
"""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.filters import CommandObject

from bot.config import Config
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo

router = Router()
logger = logging.getLogger(__name__)
config = Config()


def main_keyboard(has_subscription: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if has_subscription:
        builder.row(
            InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="account"),
            InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_vpn"),
        )
        builder.row(
            InlineKeyboardButton(text="💳 Продлить / Купить", callback_data="plans"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔑 Получить VPN", callback_data="plans"),
        )

    builder.row(
        InlineKeyboardButton(text="💬 Отзывы", callback_data="reviews"),
        InlineKeyboardButton(text="😎 О нас", callback_data="about"),
    )
    builder.row(
        InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL),
        InlineKeyboardButton(text="📄 Инфо", callback_data="info"),
    )
    builder.row(
        InlineKeyboardButton(
            text="🌐 Личный кабинет",
            web_app=WebAppInfo(url=config.MINI_APP_URL),
        )
    )
    return builder.as_markup()


WELCOME_TEXT = """
👋 Добро пожаловать в <b>SkyPath VPN</b>!

🛡 Твой личный помощник для безопасного и свободного интернета.

<b>Что ты получаешь:</b>
• 🔒 Надёжная защита данных в любой сети
• ⚡️ Безлимитная скорость без ограничений  
• 📺 YouTube в 4K, стриминг без буферизации
• 📱 До 10 устройств одновременно
• 🌍 Серверы: Россия, США, Германия, Нидерланды, Казахстан
• 💰 Честная цена — от 250 руб/месяц

📅 Статус подписки и ключи — в личном кабинете
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

    # Приветствие
    if is_new:
        welcome = WELCOME_TEXT + "\n\n🎁 <b>Для тебя — 3 дня бесплатно!</b> Нажми «Получить VPN»"
    else:
        name = user.first_name or "друг"
        welcome = f"👋 С возвращением, <b>{name}</b>!\n" + WELCOME_TEXT

    kb = main_keyboard(has_subscription=active_sub is not None)

    # Пробуем отправить с фото, если нет — текст
    try:
        await message.answer_photo(
            photo="https://disk.yandex.ru/i/bdf9VfFqRYeOEw",
            caption=welcome,
            reply_markup=kb,
        )
    except Exception:
        await message.answer(welcome, reply_markup=kb)


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
    text = """
😎 <b>О нас — SkyPath VPN</b>

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
• Автопродление через бота

<b>Контакты:</b>
• Поддержка: @SkyPathsupport
• Канал: @SkyPathVPN
"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "info")
async def cb_info(call: CallbackQuery):
    text = """
📄 <b>Информация о SkyPath VPN</b>

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
💳 Банковская карта (YooKassa)
₿ Крипто (USDT, BTC, ETH)
"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📲 Купить", callback_data="plans"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main"),
    )

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
    builder.row(
        InlineKeyboardButton(text="📲 Попробовать", callback_data="plans"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main"),
    )

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()
