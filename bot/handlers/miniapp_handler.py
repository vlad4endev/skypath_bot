"""
Mini App API — REST endpoints для Telegram Mini App
"""
import logging
from aiohttp import web
from aiogram import Router

from bot.config import Config
from bot.services.miniapp_purchase import process_miniapp_purchase
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo

router = Router()
logger = logging.getLogger(__name__)
config = Config()


async def get_config(_request: web.Request) -> web.Response:
    return web.json_response({
        "brand_name": config.BRAND_NAME,
        "support_url": config.SUPPORT_URL,
        "bot_username": config.BOT_USERNAME,
    })


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
    """Создать платёж или пробный период из Mini App"""
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        if not telegram_id:
            return web.json_response({"error": "telegram_id required"}, status=400)

        plan = data.get("plan", "BASIC")
        months = int(data.get("months", 1))
        price = int(data.get("price", 250))

        result = await process_miniapp_purchase(
            telegram_id=telegram_id,
            plan=plan,
            months=months,
            price=price,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )

        if result.get("error"):
            status = 409 if result["error"] == "trial_used" else 400
            return web.json_response(result, status=status)

        return web.json_response(result)

    except Exception as e:
        logger.error("Create payment error: %s", e)
        return web.json_response({"error": str(e)}, status=500)
