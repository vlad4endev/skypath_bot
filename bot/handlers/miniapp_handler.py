"""
Mini App API — REST endpoints для Telegram Mini App
"""
import logging
from aiohttp import web
from aiogram import Router

from bot.config import Config, PLANS, MONTHS_LABELS
from bot.i18n import SUPPORTED_LOCALES, get_api_locale, get_user_locale, normalize_locale, t
from bot.i18n.api_messages import api_msg
from bot.i18n.plans import i18n_bundle, months_labels, plan_display_name, serialize_plans
from bot.services.discount_service import calculate_discount, preview_discounts_for_plan
from bot.services.miniapp_purchase import process_miniapp_purchase, _is_new_vpn_user
from bot.services.payment_processor import process_manual_check
from bot.services.subscription_url import resolve_subscription_url
from bot.services.user_auth import (
    hash_user_password,
    normalize_email,
    validate_email,
    validate_password,
    validate_password_message,
)
from bot.services.vpn_provision import ensure_subscription_link
from bot.services.xui_client import XUIClient
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo
from database.models import SubscriptionStatus, PlanType, PaymentStatus

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
RENEWAL_WINDOW_DAYS = 14


def _resolve_request_locale(request: web.Request, user=None) -> str:
    query_lang = request.query.get("lang") or request.query.get("locale")
    if user:
        return get_user_locale(user, query_lang)
    if query_lang:
        return normalize_locale(query_lang)
    return "ru"


def _serialize_plans(locale: str = "ru") -> dict:
    return serialize_plans(locale)


def _plan_display_name(plan: PlanType | None, locale: str = "ru") -> str:
    if not plan:
        return "—"
    return plan_display_name(plan.value, locale)


def _is_subscription_live(sub) -> bool:
    return sub is not None and sub.is_active


def _subscription_can_renew(sub) -> bool:
    """Тарифы для продления: подписка истекла, пробная или осталось ≤14 дней."""
    if sub is None:
        return False
    if not _is_subscription_live(sub):
        return True
    if sub.plan == PlanType.FREE or sub.status == SubscriptionStatus.FREE_TRIAL:
        return True
    return sub.days_left <= RENEWAL_WINDOW_DAYS


def _plans_available_for_user(sub, *, has_subscription: bool) -> bool:
    if not has_subscription:
        return True
    return _subscription_can_renew(sub)


async def get_config(request: web.Request) -> web.Response:
    locale = _resolve_request_locale(request)
    return web.json_response({
        "brand_name": config.BRAND_NAME,
        "support_url": config.SUPPORT_URL,
        "bot_username": config.BOT_USERNAME,
        "cabinet_url": config.CABINET_URL,
        "months_labels": months_labels(locale),
        "locale": locale,
        "i18n": i18n_bundle(locale),
    })


async def get_i18n(request: web.Request) -> web.Response:
    locale = normalize_locale(request.match_info.get("locale", "ru"))
    return web.json_response(i18n_bundle(locale))


async def set_locale(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        locale = normalize_locale(data.get("locale", ""))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_request"}, status=400)

    if locale not in SUPPORTED_LOCALES:
        return web.json_response({"error": "unsupported_locale"}, status=400)
    if telegram_id <= 0:
        return web.json_response({"error": "invalid telegram_id"}, status=400)

    async with async_session() as session:
        user_repo = UserRepo(session)
        user, _ = await user_repo.get_or_create(telegram_id=telegram_id)
        await user_repo.set_preferred_locale(user, locale)

    return web.json_response({
        "ok": True,
        "locale": locale,
        "i18n": i18n_bundle(locale),
    })


async def get_plans(request: web.Request) -> web.Response:
    locale = _resolve_request_locale(request)
    return web.json_response({
        "plans": _serialize_plans(locale),
        "months_labels": months_labels(locale),
        "locale": locale,
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


def _serialize_subscription(
    sub,
    *,
    traffic: dict | None = None,
    plan_info: dict | None = None,
    locale: str = "ru",
) -> dict:
    is_live = _is_subscription_live(sub)
    subscription_url = resolve_subscription_url(sub, config)
    return {
        "id": sub.id,
        "plan": sub.plan.value if sub.plan else None,
        "plan_name": _plan_display_name(sub.plan, locale),
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

    async with async_session() as session:
        user_repo = UserRepo(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
    locale = _resolve_request_locale(request, user)

    traffic = None
    if sub.vpn_email:
        traffic = await xui.get_client_traffic(sub.vpn_email)

    plan_key = sub.plan.value if sub.plan else None
    plan_info = _serialize_plans(locale).get(plan_key) if plan_key else None

    return web.json_response(_serialize_subscription(sub, traffic=traffic, plan_info=plan_info, locale=locale))


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
        if not sub:
            sub = await sub_repo.get_expired_grace_restorable(telegram_id)
        referrals = await user_repo.count_referrals(telegram_id)

    has_subscription = sub is not None and _is_subscription_live(sub)
    can_renew = _subscription_can_renew(sub)
    show_plans = _plans_available_for_user(sub, has_subscription=has_subscription)
    is_new_vpn_user = _is_new_vpn_user(all_subs)

    locale = _resolve_request_locale(request, user)

    traffic = None
    plan_info = None
    subscription_data = None

    if sub:
        if sub.vpn_email:
            traffic = await xui.get_client_traffic(sub.vpn_email)
        plan_key = sub.plan.value if sub.plan else None
        plan_info = _serialize_plans(locale).get(plan_key) if plan_key else None
        subscription_data = _serialize_subscription(
            sub, traffic=traffic, plan_info=plan_info, locale=locale,
        )

    return web.json_response({
        "brand_name": config.BRAND_NAME,
        "support_url": config.SUPPORT_URL,
        "cabinet_url": config.CABINET_URL,
        "locale": locale,
        "preferred_locale": user.preferred_locale if user else locale,
        "rtl": locale == "ar",
        "i18n": i18n_bundle(locale),
        "user": {
            "telegram_id": telegram_id,
            "full_name": user.full_name if user else None,
            "username": user.username if user else None,
            "member_since": user.created_at.isoformat() if user else None,
            "referrals_count": referrals,
            "web_email": user.web_email if user and user.web_registered else None,
        } if user else None,
        "has_subscription": has_subscription,
        "can_renew": can_renew,
        "is_new_user": is_new_user,
        "is_new_vpn_user": is_new_vpn_user,
        "needs_registration": bool(user and not user.web_registered),
        "web_registered": bool(user and user.web_registered),
        "subscription": subscription_data,
        "plans": _serialize_plans(locale) if show_plans else None,
    })


async def create_payment(request: web.Request) -> web.Response:
    """Создать платёж или пробный период из Mini App"""
    telegram_id = 0
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        if not telegram_id:
            return web.json_response({"error": "telegram_id required"}, status=400)

        plan = data.get("plan", "BASIC")
        months = int(data.get("months", 1))
        price = int(data.get("price", 250))
        promo_code = (data.get("promo_code") or "").strip().upper() or None

        bot = request.app.get("bot")
        result = await process_miniapp_purchase(
            telegram_id=telegram_id,
            plan=plan,
            months=months,
            price=price,
            promo_code=promo_code,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            bot=bot,
        )

        if result.get("error"):
            status = 409 if result["error"] == "trial_used" else 400
            return web.json_response(result, status=status)

        return web.json_response(result)

    except ValueError as e:
        async with async_session() as session:
            user = await UserRepo(session).get_by_telegram_id(telegram_id)
        locale = get_api_locale(user)
        err_key = str(e)
        return web.json_response(
            {
                "error": "invalid_discount",
                "message": api_msg(locale, err_key),
            },
            status=400,
        )
    except Exception as e:
        logger.error("Create payment error: %s", e)
        async with async_session() as session:
            user = await UserRepo(session).get_by_telegram_id(telegram_id)
        locale = get_api_locale(user)
        return web.json_response(
            {"error": "payment_failed", "message": api_msg(locale, "payment_failed")},
            status=500,
        )


async def preview_discount(request: web.Request) -> web.Response:
    """Предпросмотр цен со скидками для тарифа."""
    try:
        telegram_id = int(request.match_info["telegram_id"])
        plan = request.query.get("plan", "BASIC")
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_request"}, status=400)

    async with async_session() as session:
        user_repo = UserRepo(session)
        db_user, is_new_user = await user_repo.get_or_create(telegram_id=telegram_id)
        locale = get_api_locale(db_user)
        data = await preview_discounts_for_plan(
            session,
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan_key=plan,
            is_new_user=is_new_user,
            locale=locale,
        )
    return web.json_response(data)


async def validate_promo(request: web.Request) -> web.Response:
    """Проверить промокод для тарифа и срока."""
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        plan = data.get("plan", "BASIC")
        months = int(data.get("months", 1))
        promo_code = (data.get("promo_code") or "").strip().upper()
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_request"}, status=400)

    if not telegram_id or not promo_code:
        return web.json_response({"error": "telegram_id and promo_code required"}, status=400)

    async with async_session() as session:
        user_repo = UserRepo(session)
        db_user, is_new_user = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
        )
        locale = get_api_locale(db_user)
        discount = await calculate_discount(
            session,
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan_key=plan,
            months=months,
            promo_code=promo_code,
            is_new_user=is_new_user,
            locale=locale,
        )

    if not discount.ok:
        err_key = discount.error or "promo_invalid"
        return web.json_response(
            {
                "valid": False,
                "error": err_key,
                "message": api_msg(locale, err_key),
            },
            status=400,
        )

    return web.json_response({
        "valid": True,
        "base_price": discount.base_price,
        "final_price": discount.final_price,
        "discount_total": discount.discount_total,
        "promo_code": discount.promo_code,
        "promotion_name": discount.promotion_name,
        "discount_label": discount.discount_label,
    })


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
            locale = get_api_locale(user)

        if not sub or not _is_subscription_live(sub):
            return web.json_response(
                {
                    "error": "no_subscription",
                    "message": api_msg(locale, "no_subscription"),
                },
                status=404,
            )

        existing_url = resolve_subscription_url(sub, config)
        if existing_url:
            return web.json_response({
                "subscription_url": existing_url,
                "vpn_key": existing_url,
                "message": api_msg(locale, "link_ready"),
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
                {
                    "error": "provision_failed",
                    "message": api_msg(locale, "provision_failed"),
                },
                status=500,
            )

        return web.json_response({
            "subscription_url": subscription_url,
            "vpn_key": subscription_url,
            "message": api_msg(locale, "vpn_key_created"),
        })
    except Exception as e:
        logger.error("Provision VPN error: %s", e)
        return web.json_response(
            {
                "error": "provision_failed",
                "message": api_msg("ru", "provision_failed"),
            },
            status=500,
        )


async def register_web_account(request: web.Request) -> web.Response:
    """Первичная регистрация email + пароль для будущего входа в веб-версию."""
    locale = "ru"
    try:
        data = await request.json()
        telegram_id = int(data.get("telegram_id", 0))
        email = (data.get("email") or "").strip()
        password = data.get("password") or ""
        password_confirm = data.get("password_confirm") or password

        if telegram_id <= 0:
            return web.json_response(
                {"error": "invalid_request", "message": api_msg(locale, "invalid_request")},
                status=400,
            )
        if not validate_email(email):
            return web.json_response(
                {"error": "invalid_email", "message": api_msg(locale, "invalid_email")},
                status=400,
            )

        pwd_error = validate_password(password)
        if pwd_error:
            return web.json_response(
                {
                    "error": "weak_password",
                    "message": validate_password_message(pwd_error, locale),
                },
                status=400,
            )
        if password != password_confirm:
            return web.json_response(
                {
                    "error": "password_mismatch",
                    "message": api_msg(locale, "password_mismatch"),
                },
                status=400,
            )

        async with async_session() as session:
            user_repo = UserRepo(session)
            user, _ = await user_repo.get_or_create(
                telegram_id=telegram_id,
                username=data.get("username") or None,
                first_name=data.get("first_name") or None,
                last_name=data.get("last_name") or None,
            )
            locale = get_api_locale(user)

            if user.is_banned:
                return web.json_response(
                    {"error": "banned", "message": api_msg(locale, "banned")},
                    status=403,
                )

            existing_email = await user_repo.get_by_web_email(normalize_email(email))
            if existing_email and existing_email.id != user.id:
                return web.json_response(
                    {"error": "email_taken", "message": api_msg(locale, "email_taken")},
                    status=409,
                )

            if user.web_registered:
                return web.json_response(
                    {
                        "error": "already_registered",
                        "message": api_msg(locale, "already_registered"),
                        "web_email": user.web_email,
                    },
                    status=409,
                )

            password_hash = hash_user_password(password, config.WEB_PASSWORD_PEPPER)
            user = await user_repo.register_web_credentials(
                user,
                email=email,
                password_hash=password_hash,
            )

        return web.json_response({
            "ok": True,
            "web_email": user.web_email,
            "message": api_msg(locale, "registration_complete"),
        })
    except ValueError as e:
        if str(e) == "email_taken":
            return web.json_response(
                {"error": "email_taken", "message": api_msg(locale, "email_taken")},
                status=409,
            )
        if str(e) == "already_registered":
            return web.json_response(
                {"error": "already_registered", "message": api_msg(locale, "already_registered")},
                status=409,
            )
        return web.json_response(
            {"error": str(e), "message": api_msg(locale, "generic_error")},
            status=400,
        )
    except Exception as e:
        logger.error("Register web account error: %s", e)
        return web.json_response(
            {"error": "registration_failed", "message": api_msg(locale, "registration_failed")},
            status=500,
        )


async def get_payment_status(request: web.Request) -> web.Response:
    """Статус заказа для Mini App после возврата с Platega."""
    order_id = request.match_info.get("order_id", "").strip()
    try:
        telegram_id = int(request.query.get("telegram_id", 0))
    except (TypeError, ValueError):
        telegram_id = 0

    if not order_id or telegram_id <= 0:
        return web.json_response({"error": "invalid_request"}, status=400)

    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        sub_repo = SubscriptionRepo(session)
        payment = await pay_repo.get_by_order_id(order_id)

        if not payment or payment.telegram_id != telegram_id:
            return web.json_response({"error": "not_found"}, status=404)

        if payment.status == PaymentStatus.PENDING:
            bot = request.app.get("bot")
            if bot:
                await process_manual_check(bot, order_id, telegram_id)
                payment = await pay_repo.get_by_order_id(order_id)

        subscription_url = None
        if payment.subscription_id:
            sub = await sub_repo.get_by_id(payment.subscription_id)
            if sub:
                subscription_url = resolve_subscription_url(sub, config)

        return web.json_response({
            "order_id": payment.order_id,
            "status": payment.status.value,
            "subscription_url": subscription_url,
            "fulfilled": payment.fulfilled_at is not None,
        })
