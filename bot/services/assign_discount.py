"""
Персональная скидка пользователю: промокод + уведомление в Telegram.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.keyboards.webapp import cabinet_button, is_miniapp_available
from database.engine import async_session
from database.models import PromoCode, User
from database.repository import PromoRepo, UserRepo

logger = logging.getLogger(__name__)
config = Config()


def generate_personal_code(telegram_id: int, prefix: str = "VIP") -> str:
    suffix = secrets.token_hex(2).upper()
    base = f"{prefix}{str(telegram_id)[-5:]}{suffix}"
    return base[:32].upper()


def format_discount_label(promo: PromoCode) -> str:
    if promo.discount_pct and promo.discount_amount:
        return f"{promo.discount_pct}% + {promo.discount_amount}₽"
    if promo.discount_pct:
        return f"{promo.discount_pct}%"
    if promo.discount_amount:
        return f"{promo.discount_amount}₽"
    return "скидка"


def build_discount_message(
    promo: PromoCode,
    *,
    custom_message: str | None = None,
    source_name: str | None = None,
) -> str:
    title = source_name or promo.name or "Персональная скидка"
    lines = [
        "🎁 <b>Вам назначена персональная скидка!</b>",
        "",
        f"📌 <b>{title}</b>",
    ]
    if custom_message:
        lines.extend(["", custom_message])
    elif promo.description:
        lines.extend(["", promo.description])

    lines.extend([
        "",
        f"🏷 Промокод: <code>{promo.code}</code>",
        f"💰 Скидка: <b>{format_discount_label(promo)}</b>",
    ])

    if promo.plans:
        lines.append(f"📦 Тарифы: {', '.join(str(p) for p in promo.plans)}")
    if promo.months:
        lines.append(f"⏱ Сроки: {', '.join(str(m) for m in promo.months)} мес.")
    if promo.expires_at:
        lines.append(f"📅 Действует до: <b>{promo.expires_at.strftime('%d.%m.%Y')}</b>")

    lines.extend([
        "",
        "При оплате введите промокод или нажмите «Выбрать тариф».",
    ])
    return "\n".join(lines)


async def send_discount_notification(
    bot: Bot,
    telegram_id: int,
    promo: PromoCode,
    *,
    custom_message: str | None = None,
    source_name: str | None = None,
) -> bool:
    text = build_discount_message(
        promo,
        custom_message=custom_message,
        source_name=source_name,
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📦 Выбрать тариф", callback_data="plans"))
    if is_miniapp_available():
        builder.row(cabinet_button("👤 Личный кабинет"))
    try:
        await bot.send_message(telegram_id, text, reply_markup=builder.as_markup())
        return True
    except Exception as e:
        logger.warning("Failed to send discount notification to %s: %s", telegram_id, e)
        return False


async def assign_personal_discount(
    *,
    bot: Bot | None,
    user: User,
    discount_pct: int = 0,
    discount_amount: int = 0,
    plans: list | None = None,
    months: list | None = None,
    min_amount: int = 0,
    expires_at: datetime | None = None,
    code: str | None = None,
    name: str | None = None,
    description: str | None = None,
    custom_message: str | None = None,
    source_name: str | None = None,
    send_notification: bool = True,
) -> dict[str, Any]:
    """Создать персональный промокод и опционально отправить сообщение."""
    if not discount_pct and not discount_amount:
        raise ValueError("Укажите скидку в процентах или в рублях")

    promo_code = (code or generate_personal_code(user.telegram_id)).upper().strip()
    if len(promo_code) > 32:
        raise ValueError("Код промокода слишком длинный")

    async with async_session() as session:
        promo_repo = PromoRepo(session)
        existing = await promo_repo.get_by_code(promo_code)
        if existing:
            raise ValueError("Такой промокод уже существует")

        promo = await promo_repo.create_personal(
            code=promo_code,
            telegram_id=user.telegram_id,
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            plans=plans,
            months=months,
            min_amount=min_amount,
            expires_at=expires_at,
            name=name or source_name or "Персональная скидка",
            description=description,
        )

    notified = False
    if send_notification and bot is not None:
        notified = await send_discount_notification(
            bot,
            user.telegram_id,
            promo,
            custom_message=custom_message,
            source_name=source_name or name,
        )

    return {
        "promo_id": promo.id,
        "code": promo.code,
        "telegram_id": user.telegram_id,
        "notified": notified,
        "discount_label": format_discount_label(promo),
    }


async def resolve_user(*, user_id: int | None = None, telegram_id: int | None = None) -> User:
    async with async_session() as session:
        user_repo = UserRepo(session)
        if user_id:
            user = await user_repo.get_by_id(user_id)
            if user:
                return user
        if telegram_id:
            user, _ = await user_repo.get_or_create(telegram_id=telegram_id)
            return user
    raise ValueError("Пользователь не найден")
