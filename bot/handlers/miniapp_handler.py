"""
Mini App API — REST endpoints для Telegram Mini App
"""
import logging
from aiohttp import web
from aiogram import Router

from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo
from database.models import SubscriptionStatus

router = Router()
logger = logging.getLogger(__name__)


async def get_user_info(request: web.Request) -> web.Response:
    telegram_id = int(request.match_info["telegram_id"])

    async with async_session() as session:
        user_repo = UserRepo(session)
        user = await user_repo.get_by_telegram_id(telegram_id)

    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    return web.json_response({
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
    })


async def get_subscription(request: web.Request) -> web.Response:
    telegram_id = int(request.match_info["telegram_id"])

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_active(telegram_id)

    if not sub:
        return web.json_response({"status": None})

    return web.json_response({
        "id": sub.id,
        "plan": sub.plan.value if sub.plan else None,
        "status": sub.status.value if sub.status else None,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "days_left": sub.days_left,
        "limit_ip": sub.limit_ip,
        "months_paid": sub.months_paid,
        "vpn_key": sub.vpn_key,
        "vpn_sub_id": sub.vpn_sub_id,
    })


async def create_payment(request: web.Request) -> web.Response:
    """Создать платёж из Mini App"""
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        plan = data.get("plan", "BASIC")
        months = int(data.get("months", 1))
        price = int(data.get("price", 250))

        from bot.config import Config, PLANS
        from bot.services.payment import YooKassaClient
        from database.repository import UserRepo, SubscriptionRepo, PaymentRepo
        from database.models import PlanType

        cfg = Config()
        yookassa = YooKassaClient(cfg)
        plan_cfg = PLANS.get(plan, PLANS["BASIC"])
        limit_ip = plan_cfg.get("limit_ip", 3)

        async with async_session() as session:
            user_repo = UserRepo(session)
            sub_repo = SubscriptionRepo(session)
            pay_repo = PaymentRepo(session)

            user, _ = await user_repo.get_or_create(telegram_id=telegram_id)
            sub = await sub_repo.create_pending(
                telegram_id=telegram_id,
                user_id=user.id,
                plan=PlanType[plan],
                limit_ip=limit_ip,
            )

            payment_data = await yookassa.create_payment(
                amount=price,
                description=f"SkyPath VPN — {plan} / {months} мес.",
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

        return web.json_response({
            "payment_url": payment_data["payment_url"],
            "payment_id": payment_data["payment_id"],
        })

    except Exception as e:
        logger.error(f"Create payment error: {e}")
        return web.json_response({"error": str(e)}, status=500)
