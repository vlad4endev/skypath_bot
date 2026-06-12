"""
Покупка из Telegram Mini App — общая логика для REST API и web_app_data.
"""
import logging
from typing import Any

from bot.config import Config, PLANS
from bot.services.payment_processor import create_paid_order
from bot.services.subscription_url import resolve_subscription_url
from bot.services.vpn_provision import ensure_subscription_link, provision_vpn_for_subscription
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo
from database.models import PlanType, SubscriptionStatus

logger = logging.getLogger(__name__)
config = Config()


def _is_new_vpn_user(existing_subs: list) -> bool:
    """Пользователь ещё не получал VPN (нет подписок с клиентом в панели)."""
    if not existing_subs:
        return True
    return not any(s.vpn_sub_id or s.vpn_uuid for s in existing_subs)


async def process_miniapp_purchase(
    telegram_id: int,
    plan: str,
    months: int,
    price: int,
    *,
    promo_code: str | None = None,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    bot: Any | None = None,
) -> dict[str, Any]:
    """Создать заказ из Mini App. Возвращает dict для JSON-ответа."""
    plan_cfg = PLANS.get(plan)
    if not plan_cfg:
        return {"error": "unknown_plan", "message": "Тариф не найден"}

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        db_user, is_new_user = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        existing_subs = await sub_repo.get_all_for_user(telegram_id)
        is_new_vpn_user = _is_new_vpn_user(existing_subs)

    if plan == "FREE" or price == 0:
        return await _issue_free_trial(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            bot=bot,
            is_new_user=is_new_user,
            is_new_vpn_user=is_new_vpn_user,
        )

    try:
        order = await create_paid_order(
            telegram_id=telegram_id,
            plan_key=plan,
            months=months,
            price=price,
            username=username,
            first_name=first_name,
            last_name=last_name,
            promo_code=promo_code,
            for_miniapp=True,
        )
    except ValueError as e:
        return {"error": "invalid_discount", "message": str(e)}
    except Exception as e:
        logger.error("Mini App create order failed: %s", e)
        return {"error": "payment_failed", "message": "Не удалось создать платёж"}

    return {
        "payment_url": order.payment_url,
        "payment_id": order.payment_id,
        "order_id": order.order_id,
        "amount": order.amount,
        "original_amount": order.original_amount,
        "discount_total": order.discount_total,
        "discount_label": order.discount_label,
        "promo_code": order.promo_code,
        "subscription_id": order.subscription_id,
        "is_new_user": is_new_user,
        "is_new_vpn_user": is_new_vpn_user,
        "provisioned": False,
    }


async def _issue_free_trial(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    bot: Any | None = None,
    is_new_user: bool = False,
    is_new_vpn_user: bool = True,
) -> dict[str, Any]:
    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        db_user, _ = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        existing = await sub_repo.get_all_for_user(telegram_id)
        if any(s.plan == PlanType.FREE for s in existing):
            return {
                "error": "trial_used",
                "message": "Пробный период уже был использован",
            }

        active = await sub_repo.get_active(telegram_id)
        if active:
            link = resolve_subscription_url(active, config)
            if link:
                return {
                    "free_trial": False,
                    "provisioned": True,
                    "subscription_url": link,
                    "vpn_key": link,
                    "expires_at": active.expires_at.isoformat() if active.expires_at else None,
                    "is_new_user": is_new_user,
                    "is_new_vpn_user": False,
                    "message": "Подписка уже активна",
                }

        sub = await sub_repo.create_pending(
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan=PlanType.FREE,
            limit_ip=PLANS["FREE"]["limit_ip"],
        )
        sub_id = sub.id

    try:
        result = await provision_vpn_for_subscription(
            telegram_id=telegram_id,
            first_name=first_name or "User",
            last_name=last_name or "",
            sub_id_db=sub_id,
            months=0,
            days=PLANS["FREE"]["days"],
        )
    except Exception as e:
        logger.exception("Free trial provision failed for %s: %s", telegram_id, e)
        return {"error": "provision_failed", "message": "Не удалось создать VPN-ключ"}

    if bot is not None:
        await _notify_trial_activated(bot, telegram_id, result.subscription_url)

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id)

    if not sub or sub.status not in (
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.FREE_TRIAL,
    ):
        return {"error": "provision_failed", "message": "Не удалось активировать подписку"}

    return {
        "free_trial": True,
        "provisioned": True,
        "vpn_key": result.subscription_url,
        "subscription_url": result.subscription_url,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "is_new_user": is_new_user,
        "is_new_vpn_user": is_new_vpn_user,
        "message": "Пробный период активирован — ссылка готова",
    }


async def _notify_trial_activated(bot: Any, telegram_id: int, subscription_url: str) -> None:
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        from bot.keyboards.webapp import cabinet_button, is_miniapp_available

        text = (
            "🎉 <b>Пробный VPN готов!</b>\n\n"
            "🔗 <b>Ссылка подписки:</b>\n"
            f"<code>{subscription_url}</code>\n\n"
            "Скопируй и добавь в Happ или v2rayNG."
        )
        builder = InlineKeyboardBuilder()
        if is_miniapp_available():
            builder.row(cabinet_button("👤 Личный кабинет"))
        builder.row(InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"))
        await bot.send_message(telegram_id, text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.warning("Trial notify failed for %s: %s", telegram_id, e)


class _NoopBot:
    """Заглушка для REST API без дублирования сообщения в чат."""

    def __init__(self, telegram_id: int) -> None:
        self._telegram_id = telegram_id

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        logger.debug("Skip bot message for %s (mini-app REST)", chat_id)
