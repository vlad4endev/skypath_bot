"""
Mini App API — REST endpoints для Telegram Mini App
"""
import logging
from aiohttp import web
from aiogram import Router

from bot.config import Config, PLANS, MONTHS_LABELS
from bot.services.miniapp_purchase import process_miniapp_purchase, _is_new_vpn_user
from bot.services.subscription_url import resolve_subscription_url
from bot.services.vpn_provision import ensure_subscription_link
from bot.services.xui_client import XUIClient
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo
from database.models import SubscriptionStatus, PlanType

router = Router()
logger = logging.getLogger(__name__)
config = Config()

xui = XUIClient(
    host=config.XUI_HOST,
    url_prefix=config.XUI_URL_PREFIX,
    username=config.XUI_USERNAME,
    password=config.XUI_PASSWORD,
    api_token=config.XUI_API_TOKEN,
    sub_path=config.XUI_SUB_PATH,
    sub_base_url=config.XUI_SUB_BASE_URL,
)

ACTIVE_STATUSES = {SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL}

PLAN_FEATURES = {
    "FREE": ["3 дня бесплатно", "1 устройство", "5 ГБ трафика", "Все серверы"],
    "BASIC": ["3 устройства", "Безлимитный трафик", "5 локаций", "Поддержка 24/7"],
    "MULTI": ["5 устройств", "Безлимитный трафик", "Все серверы", "Приоритетная скорость"],
    "SUPER": ["10 устройств", "Безлимитный трафик", "Все серверы", "Максимальный приоритет"],
}


def _serialize_plans() -> dict:
    result = {}
    for key, plan in PLANS.items():
        entry = {
            "key": key,
            "name": plan["name"],
            "description": plan.get("description", ""),
            "limit_ip": plan.get("limit_ip", 1),
            "traffic_gb": plan.get("traffic_gb", 0),
            "features": PLAN_FEATURES.get(key, []),
            "recommended": key == "MULTI",
        }
        if key == "FREE":
            entry["price"] = 0
            entry["days"] = plan.get("days", 3)
        else:
            entry["prices"] = plan.get("prices", {})
        result[key] = entry
    return result


def _plan_display_name(plan: PlanType | None) -> str:
    if not plan:
        return "—"
    cfg = PLANS.get(plan.value, {})
    return cfg.get("name", plan.value)


def _is_subscription_live(sub) -> bool:
    return sub is not None and sub.is_active


async def get_config(_request: web.Request) -> web.Response:
    return web.json_response({
        "brand_name": config.BRAND_NAME,
        "support_url": config.SUPPORT_URL,
        "bot_username": config.BOT_USERNAME,
        "months_labels": MONTHS_LABELS,
    })


async def get_plans(_request: web.Request) -> web.Response:
    return web.json_response({
        "plans": _serialize_plans(),
        "months_labels": MONTHS_LABELS,
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


def _serialize_subscription(sub, *, traffic: dict | None = None, plan_info: dict | None = None) -> dict:
    is_live = _is_subscription_live(sub)
    subscription_url = resolve_subscription_url(sub, config)
    return {
        "id": sub.id,
        "plan": sub.plan.value if sub.plan else None,
        "plan_name": _plan_display_name(sub.plan),
        "status": sub.status.value if sub.status else None,
        "is_active": is_live,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "started_at": sub.started_at.isoformat() if sub.started_at else None,
        "days_left": sub.days_left,
        "limit_ip": sub.limit_ip,
        "months_paid": sub.months_paid,
        "traffic_gb": sub.traffic_gb,
        "vpn_key": subscription_url,
        "subscription_url": subscription_url,
        "vpn_sub_id": sub.vpn_sub_id,
        "has_vpn_client": bool(sub.vpn_sub_id or sub.vpn_uuid or sub.vpn_email),
        "traffic": traffic,
        "plan_info": plan_info,
    }


async def get_subscription(request: web.Request) -> web.Response:
    telegram_id = int(request.match_info["telegram_id"])

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_active(telegram_id)

    if not sub:
        return web.json_response({"status": None, "is_active": False})

    traffic = None
    if sub.vpn_email:
        traffic = await xui.get_client_traffic(sub.vpn_email)

    plan_key = sub.plan.value if sub.plan else None
    plan_info = _serialize_plans().get(plan_key) if plan_key else None

    return web.json_response(_serialize_subscription(sub, traffic=traffic, plan_info=plan_info))


async def get_dashboard(request: web.Request) -> web.Response:
    """Личный кабинет Mini App: пользователь и активная подписка."""
    telegram_id = int(request.match_info["telegram_id"])
    if telegram_id <= 0:
        return web.json_response({"error": "invalid telegram_id"}, status=400)

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        user, is_new_user = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=request.query.get("username") or None,
            first_name=request.query.get("first_name") or None,
            last_name=request.query.get("last_name") or None,
        )
        all_subs = await sub_repo.get_all_for_user(telegram_id)
        sub = await sub_repo.get_active(telegram_id)
        referrals = await user_repo.count_referrals(telegram_id)

    has_subscription = sub is not None and _is_subscription_live(sub)
    is_new_vpn_user = _is_new_vpn_user(all_subs)

    traffic = None
    plan_info = None
    subscription_data = None

    if sub:
        if sub.vpn_email:
            traffic = await xui.get_client_traffic(sub.vpn_email)
        plan_key = sub.plan.value if sub.plan else None
        plan_info = _serialize_plans().get(plan_key) if plan_key else None
        subscription_data = _serialize_subscription(
            sub, traffic=traffic, plan_info=plan_info
        )

    return web.json_response({
        "brand_name": config.BRAND_NAME,
        "support_url": config.SUPPORT_URL,
        "user": {
            "telegram_id": telegram_id,
            "full_name": user.full_name if user else None,
            "username": user.username if user else None,
            "member_since": user.created_at.isoformat() if user else None,
            "referrals_count": referrals,
        } if user else None,
        "has_subscription": has_subscription,
        "is_new_user": is_new_user,
        "is_new_vpn_user": is_new_vpn_user,
        "subscription": subscription_data,
        "plans": _serialize_plans() if not has_subscription else None,
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

        bot = request.app.get("bot")
        result = await process_miniapp_purchase(
            telegram_id=telegram_id,
            plan=plan,
            months=months,
            price=price,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            bot=bot,
        )

        if result.get("error"):
            status = 409 if result["error"] == "trial_used" else 400
            return web.json_response(result, status=status)

        return web.json_response(result)

    except Exception as e:
        logger.error("Create payment error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def provision_vpn(request: web.Request) -> web.Response:
    """Создать VPN-клиент или вернуть subscription link для активной подписки без ключа."""
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        if telegram_id <= 0:
            return web.json_response({"error": "telegram_id required"}, status=400)

        async with async_session() as session:
            user_repo = UserRepo(session)
            sub_repo = SubscriptionRepo(session)
            user, _ = await user_repo.get_or_create(
                telegram_id=telegram_id,
                username=data.get("username") or None,
                first_name=data.get("first_name") or None,
                last_name=data.get("last_name") or None,
            )
            sub = await sub_repo.get_active(telegram_id)

        if not sub or not _is_subscription_live(sub):
            return web.json_response(
                {"error": "no_subscription", "message": "Нет активной подписки"},
                status=404,
            )

        existing_url = resolve_subscription_url(sub, config)
        if existing_url:
            return web.json_response({
                "subscription_url": existing_url,
                "vpn_key": existing_url,
                "message": "Ссылка подписки готова",
            })

        plan_key = sub.plan.value if sub.plan else "BASIC"
        plan_cfg = PLANS.get(plan_key, PLANS["BASIC"])
        is_trial = sub.plan == PlanType.FREE or sub.status == SubscriptionStatus.FREE_TRIAL
        trial_days = plan_cfg.get("days", 3) if is_trial else 0
        months = sub.months_paid or 1

        subscription_url = await ensure_subscription_link(
            telegram_id=telegram_id,
            first_name=user.first_name or data.get("first_name") or "User",
            last_name=user.last_name or data.get("last_name") or "",
            sub_id_db=sub.id,
            months=0 if is_trial else months,
            days=trial_days if is_trial else 0,
        )
        if not subscription_url:
            return web.json_response(
                {"error": "provision_failed", "message": "Не удалось создать VPN-ключ"},
                status=500,
            )

        return web.json_response({
            "subscription_url": subscription_url,
            "vpn_key": subscription_url,
            "message": "VPN-ключ создан",
        })
    except Exception as e:
        logger.error("Provision VPN error: %s", e)
        return web.json_response({"error": "provision_failed", "message": str(e)}, status=500)
