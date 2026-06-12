"""
Аккаунт пользователя — статус, VPN ключи, устройства
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo
from database.models import SubscriptionStatus
from bot.handlers.referral_handler import referral_link

router = Router()
logger = logging.getLogger(__name__)
config = Config()


def status_emoji(status: SubscriptionStatus) -> str:
    return {
        SubscriptionStatus.ACTIVE: "🟢",
        SubscriptionStatus.PENDING: "🟡",
        SubscriptionStatus.EXPIRED: "🔴",
        SubscriptionStatus.BLOCKED: "⛔️",
        SubscriptionStatus.FREE_TRIAL: "🎁",
    }.get(status, "⚪️")


@router.callback_query(F.data == "account")
async def cb_account(call: CallbackQuery):
    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        user = await user_repo.get_by_telegram_id(call.from_user.id)
        subs = await sub_repo.get_all_for_user(call.from_user.id)
        active_sub = next((s for s in subs if s.status == SubscriptionStatus.ACTIVE), None)
        referrals_count = await user_repo.count_referrals(call.from_user.id) if user else 0

    if not user:
        await call.answer("Аккаунт не найден", show_alert=True)
        return

    member_since = user.created_at.strftime("%d.%m.%Y")
    name = user.full_name

    if active_sub:
        days = active_sub.days_left
        expires_str = active_sub.expires_at.strftime("%d.%m.%Y") if active_sub.expires_at else "—"
        plan_name = active_sub.plan.value if active_sub.plan else "—"
        status_str = f"{status_emoji(active_sub.status)} {active_sub.status.value}"

        days_text = f"⏳ Осталось: <b>{days} дней</b>" if days > 0 else "⚠️ <b>Подписка истекает сегодня!</b>"

        text = f"""
👤 <b>Мой аккаунт</b>

👋 {name}
🆔 ID: <code>{call.from_user.id}</code>
📅 Участник с: {member_since}

━━━━━━━━━━━━━━━━━
<b>Активная подписка:</b>
📦 Тариф: <b>{plan_name}</b>
{status_str}
📆 До: <b>{expires_str}</b>
{days_text}
📱 Устройств: <b>{active_sub.limit_ip}</b>
👥 Приглашено друзей: <b>{referrals_count}</b>
━━━━━━━━━━━━━━━━━
"""
    else:
        text = f"""
👤 <b>Мой аккаунт</b>

👋 {name}
🆔 ID: <code>{call.from_user.id}</code>
📅 Участник с: {member_since}

━━━━━━━━━━━━━━━━━
❌ Активная подписка отсутствует
👥 Приглашено друзей: <b>{referrals_count}</b>
━━━━━━━━━━━━━━━━━
"""

    ref_url = referral_link(call.from_user.id)
    builder = InlineKeyboardBuilder()
    if active_sub:
        builder.row(
            InlineKeyboardButton(text="🔑 Мои VPN ключи", callback_data="my_vpn"),
            InlineKeyboardButton(text="🔄 Продлить", callback_data="plans"),
        )
    else:
        builder.row(InlineKeyboardButton(text="🛒 Купить подписку", callback_data="plans"))

    builder.row(
        InlineKeyboardButton(
            text="🎁 Поделиться — +7 дней за друга",
            switch_inline_query=f"Попробуй {config.BRAND_NAME} — 3 дня бесплатно! {ref_url}",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ Главная", callback_data="main"))

    await call.message.edit_caption(
        caption=text, reply_markup=builder.as_markup()
    ) if call.message.photo else await call.message.edit_text(
        text=text, reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "my_vpn")
async def cb_my_vpn(call: CallbackQuery):
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        subs = await sub_repo.get_all_for_user(call.from_user.id)

    active_subs = [s for s in subs if s.status == SubscriptionStatus.ACTIVE]

    if not active_subs:
        text = "❌ У тебя нет активных VPN подписок.\n\nНажми «Купить» чтобы начать!"
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🛒 Купить", callback_data="plans"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="account"),
        )
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
            if call.message.photo else \
            await call.message.edit_text(text=text, reply_markup=builder.as_markup())
        await call.answer()
        return

    text = "🔑 <b>Твои VPN ключи</b>\n\n"
    builder = InlineKeyboardBuilder()

    for i, sub in enumerate(active_subs, 1):
        expires = sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "?"
        plan_name = sub.plan.value if sub.plan else "VPN"
        days = sub.days_left

        text += f"<b>{i}. {plan_name}</b>\n"
        text += f"   ⏳ До: {expires} (осталось {days} дн.)\n"
        text += f"   📱 Устройств: {sub.limit_ip}\n\n"

        if sub.vpn_key:
            builder.row(
                InlineKeyboardButton(
                    text=f"📋 Ключ #{i} — {plan_name}",
                    callback_data=f"get_key:{sub.id}",
                )
            )
        if sub.vpn_sub_id:
            sub_url = config.xui_sub_url(sub.vpn_sub_id)
            builder.row(
                InlineKeyboardButton(
                    text=f"🔗 Ссылка подписки #{i}",
                    callback_data=f"get_sub_url:{sub.id}",
                )
            )

    text += "💡 <i>Ключ можно добавить в любое VPN приложение.\n"
    text += "Рекомендуем: v2rayNG, Nekoray, V2Box, Happ, ShadowRocket</i>"

    builder.row(
        InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="account"),
    )

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("get_key:"))
async def cb_get_key(call: CallbackQuery):
    sub_id = int(call.data.split(":")[1])

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id)

    if not sub or sub.telegram_id != call.from_user.id:
        await call.answer("Ключ не найден", show_alert=True)
        return

    if not sub.vpn_key:
        await call.answer("Ключ ещё не создан. Обратись в поддержку.", show_alert=True)
        return

    expires = sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "?"

    text = f"""
🔑 <b>Твой VPN ключ</b>

<code>{sub.vpn_key}</code>

📆 Действует до: <b>{expires}</b>
📱 Устройств: <b>{sub.limit_ip}</b>

<b>Как использовать:</b>
1. Скопируй ключ (нажми на текст)
2. Открой приложение (v2rayNG / Happ / V2Box)
3. Добавь конфигурацию → вставь ключ
4. Нажми подключить ✅
"""

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="my_vpn"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("get_sub_url:"))
async def cb_get_sub_url(call: CallbackQuery):
    sub_id = int(call.data.split(":")[1])

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id)

    if not sub or sub.telegram_id != call.from_user.id:
        await call.answer("Подписка не найдена", show_alert=True)
        return

    if not sub.vpn_sub_id:
        await call.answer("Ссылка подписки недоступна", show_alert=True)
        return

    sub_url = config.xui_sub_url(sub.vpn_sub_id)

    text = f"""
🔗 <b>Ссылка подписки</b>

<code>{sub_url}</code>

Добавь эту ссылку в приложение для автоматического обновления конфигурации.

<b>Поддерживается в:</b>
• v2rayNG (Android)
• Nekoray (ПК)
• Happ (iOS/Mac)
• V2Box (iOS)
"""

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="my_vpn"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "instructions")
async def cb_instructions(call: CallbackQuery):
    text = """
📖 <b>Инструкции по настройке</b>

<b>📱 Android — v2rayNG</b>
1. Установи <a href="https://play.google.com/store/apps/details?id=com.v2ray.ang">v2rayNG</a>
2. Нажми + → Вставить из буфера обмена
3. Включи VPN ✅

<b>🍎 iPhone / iPad — Happ</b>
1. Установи <a href="https://apps.apple.com/app/happ-proxy-utility/id6504287215">Happ</a>
2. + → Вставить ссылку конфига
3. Подключиться ✅

<b>💻 Windows — Nekoray</b>
1. Скачай <a href="https://github.com/MatsuriDayo/nekoray/releases">Nekoray</a>
2. Сервер → Добавить → Вставить конфиг
3. Включить ✅

<b>🍎 macOS — V2Box</b>
1. Установи <a href="https://apps.apple.com/app/v2box-v2ray-client/id6446814690">V2Box</a>
2. Конфигурация → Добавить → Вставить ✅

💡 <i>Проблемы? Напиши в @SkyPathsupport</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="my_vpn"),
    )

    await call.message.edit_caption(
        caption=text, reply_markup=builder.as_markup(), disable_web_page_preview=True
    ) if call.message.photo else await call.message.edit_text(
        text=text, reply_markup=builder.as_markup(), disable_web_page_preview=True
    )
    await call.answer()
