"""
Покупка из Telegram Mini App — общая логика для REST API и web_app_data.
"""
import logging
from typing import Any

from bot.config import Config, PLANS
from bot.services.payment import PlategaClient
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo
from database.models import PlanType, SubscriptionStatus

logger = logging.getLogger(__name__)


async def process_miniapp_purchase(
    telegram_id: int,
    plan: str,
    months: int,
    price: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    bot: Any | None = None,
) -> dict[str, Any]:
    """Создать заказ из Mini App. Возвращает dict для JSON-ответа."""
    cfg = Config()
    plan_cfg = PLANS.get(plan)
    if not plan_cfg:
        return {"error": "unknown_plan", "message": "Тариф не найден"}

    if plan == "FREE" or price == 0:
        return await _issue_free_trial(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            bot=bot,
        )

    platega = PlategaClient(cfg)
    limit_ip = plan_cfg.get("limit_ip", 3)

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        pay_repo = PaymentRepo(session)

        user, _ = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        sub = await sub_repo.create_pending(
            telegram_id=telegram_id,
            user_id=user.id,
            plan=PlanType[plan],
            limit_ip=limit_ip,
        )

        payment_data = await platega.create_payment(
            amount=price,
            description=f"{cfg.BRAND_NAME} — {plan} / {months} мес.",
            metadata={
                "telegram_id": str(telegram_id),
                "plan": plan,
                "months": str(months),
                "subscription_id": str(sub.id),
            },
        )

        await pay_repo.create(
            user_id=user.id,
            subscription_id=sub.id,
            amount=price,
            plan=plan,
            months=months,
            yookassa_id=payment_data["payment_id"],
            order_id=payment_data["order_id"],
            payment_url=payment_data["payment_url"],
        )

    return {
        "payment_url": payment_data["payment_url"],
        "payment_id": payment_data["payment_id"],
    }


async def _issue_free_trial(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    bot: Any | None = None,
) -> dict[str, Any]:
    from bot.handlers.payment_handler import _create_vpn_and_notify

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

        sub = await sub_repo.create_pending(
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan=PlanType.FREE,
            limit_ip=PLANS["FREE"]["limit_ip"],
        )
        sub_id = sub.id

    notify_bot = bot if bot is not None else _NoopBot(telegram_id)
    await _create_vpn_and_notify(
        bot=notify_bot,
        telegram_id=telegram_id,
        first_name=first_name or "User",
        last_name=last_name or "",
        sub_id_db=sub_id,
        months=0,
        days=PLANS["FREE"]["days"],
        plan_name=PLANS["FREE"]["name"],
        amount=0,
    )

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id)

    if not sub or sub.status != SubscriptionStatus.ACTIVE or not sub.vpn_key:
        return {"error": "provision_failed", "message": "Не удалось выдать пробный ключ"}

    return {
        "free_trial": True,
        "vpn_key": sub.vpn_key,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "message": "Пробный период активирован",
    }


class _NoopBot:
    """Заглушка: VPN уже создан, сообщение в чат отправит web_app_data-обработчик."""

    def __init__(self, telegram_id: int) -> None:
        self._telegram_id = telegram_id

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        logger.debug("Skip duplicate free-trial message for %s", chat_id)
