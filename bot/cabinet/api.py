"""REST API for web cabinet (authenticated by email + password)."""
from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Awaitable

from aiohttp import web

from bot.cabinet.auth import CabinetAuth
from bot.config import Config, PLANS, MONTHS_LABELS
from bot.handlers import miniapp_handler
from bot.services.discount_service import calculate_discount, preview_discounts_for_plan
from bot.services.miniapp_purchase import process_miniapp_purchase, _is_new_vpn_user
from bot.services.payment_processor import process_manual_check
from bot.services.subscription_url import resolve_subscription_url
from bot.services.user_auth import (
    normalize_email,
    validate_email,
    verify_user_password,
)
from bot.services.vpn_provision import ensure_subscription_link
from database.engine import async_session
from database.models import PlanType, PaymentStatus, SubscriptionStatus, User
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {
    "/cabinet/api/auth/login",
    "/cabinet/api/config",
    "/cabinet/api/health",
}


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _error(message: str, status: int = 400, *, code: str | None = None) -> web.Response:
    body: dict[str, Any] = {"error": code or "error", "message": message}
    return web.json_response(body, status=status)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        return {}


async def _get_authenticated_user(request: web.Request) -> User | None:
    session = request.get("cabinet_session")
    if not session:
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    async with async_session() as db:
        return await UserRepo(db).get_by_id(user_id)


def cabinet_middleware(auth: CabinetAuth):
    @web.middleware
    async def middleware(request: web.Request, handler):
        path = request.path
        if not path.startswith("/cabinet/api"):
            return await handler(request)
        if path in PUBLIC_PATHS:
            return await handler(request)
        token = auth.extract_token(request)
        session = await auth.get_session(token)
        if not session:
            return _error("Требуется авторизация", 401, code="unauthorized")
        request["cabinet_token"] = token
        request["cabinet_session"] = session
        return await handler(request)

    return middleware


def require_user(handler: Callable[..., Awaitable[web.Response]]):
    @wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        user = await _get_authenticated_user(request)
        if not user:
            return _error("Пользователь не найден", 401, code="unauthorized")
        if user.is_banned:
            return _error("Аккаунт заблокирован", 403, code="banned")
        request["cabinet_user"] = user
        return await handler(request)

    return wrapper


def setup_cabinet_routes(app: web.Application, config: Config) -> CabinetAuth:
    auth = CabinetAuth(config)
    app.middlewares.insert(0, cabinet_middleware(auth))

    async def login(request: web.Request) -> web.Response:
        body = await _body(request)
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""

        if not validate_email(email):
            return _error("Введите корректный email", 400, code="invalid_email")
        if not password:
            return _error("Введите пароль", 400, code="missing_password")

        normalized = normalize_email(email)
        async with async_session() as session:
            user_repo = UserRepo(session)
            user = await user_repo.get_by_web_email(normalized)

        if not user or not user.web_registered or not user.password_hash:
            return _error("Неверный email или пароль", 401, code="invalid_credentials")
        if user.is_banned:
            return _error("Аккаунт заблокирован", 403, code="banned")
        if not verify_user_password(password, user.password_hash, config.WEB_PASSWORD_PEPPER):
            return _error("Неверный email или пароль", 401, code="invalid_credentials")

        token = await auth.create_session(
            user_id=user.id,
            telegram_id=user.telegram_id,
            email=user.web_email or normalized,
        )
        resp = _json({
            "ok": True,
            "token": token,
            "user": {
                "full_name": user.full_name,
                "email": user.web_email,
                "telegram_id": user.telegram_id,
            },
        })
        resp.set_cookie(
            "cabinet_token",
            token,
            httponly=True,
            samesite="Lax",
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    async def logout(request: web.Request) -> web.Response:
        await auth.revoke_session(request.get("cabinet_token"))
        resp = _json({"ok": True})
        resp.del_cookie("cabinet_token", path="/")
        return resp

    @require_user
    async def me(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        return _json({
            "ok": True,
            "brand": config.BRAND_NAME,
            "user": {
                "full_name": user.full_name,
                "email": user.web_email,
                "username": user.username,
                "telegram_id": user.telegram_id,
                "member_since": user.created_at.isoformat() if user.created_at else None,
            },
        })

    async def health(_request: web.Request) -> web.Response:
        return _json({"status": "ok"})

    async def get_config(_request: web.Request) -> web.Response:
        return _json({
            "brand_name": config.BRAND_NAME,
            "support_url": config.SUPPORT_URL,
            "bot_username": config.BOT_USERNAME,
            "months_labels": MONTHS_LABELS,
        })

    @require_user
    async def get_plans(_request: web.Request) -> web.Response:
        return _json({
            "plans": miniapp_handler._serialize_plans(),
            "months_labels": MONTHS_LABELS,
        })

    @require_user
    async def get_dashboard(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        telegram_id = user.telegram_id

        async with async_session() as session:
            user_repo = UserRepo(session)
            sub_repo = SubscriptionRepo(session)
            all_subs = await sub_repo.get_all_for_user(telegram_id)
            sub = await sub_repo.get_active(telegram_id)
            referrals = await user_repo.count_referrals(telegram_id)

        has_subscription = sub is not None and miniapp_handler._is_subscription_live(sub)
        is_new_vpn_user = _is_new_vpn_user(all_subs)

        traffic = None
        plan_info = None
        subscription_data = None

        if sub:
            if sub.vpn_email:
                traffic = await miniapp_handler.xui.get_client_traffic(sub.vpn_email)
            plan_key = sub.plan.value if sub.plan else None
            plan_info = miniapp_handler._serialize_plans().get(plan_key) if plan_key else None
            subscription_data = miniapp_handler._serialize_subscription(
                sub, traffic=traffic, plan_info=plan_info
            )

        return _json({
            "brand_name": config.BRAND_NAME,
            "support_url": config.SUPPORT_URL,
            "user": {
                "telegram_id": telegram_id,
                "full_name": user.full_name,
                "username": user.username,
                "email": user.web_email,
                "member_since": user.created_at.isoformat() if user.created_at else None,
                "referrals_count": referrals,
            },
            "has_subscription": has_subscription,
            "is_new_vpn_user": is_new_vpn_user,
            "web_registered": user.web_registered,
            "subscription": subscription_data,
            "plans": miniapp_handler._serialize_plans() if not has_subscription else None,
        })

    @require_user
    async def create_payment(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        try:
            data = await request.json()
            plan = data.get("plan", "BASIC")
            months = int(data.get("months", 1))
            price = int(data.get("price", 250))
            promo_code = (data.get("promo_code") or "").strip().upper() or None

            bot = request.app.get("bot")
            result = await process_miniapp_purchase(
                telegram_id=user.telegram_id,
                plan=plan,
                months=months,
                price=price,
                promo_code=promo_code,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                bot=bot,
            )

            if result.get("error"):
                status = 409 if result["error"] == "trial_used" else 400
                return web.json_response(result, status=status)

            return web.json_response(result)
        except ValueError as e:
            return _error(str(e), 400, code="invalid_discount")
        except Exception as e:
            logger.error("Cabinet payment error: %s", e)
            return _error("Не удалось создать платёж", 500)

    @require_user
    async def preview_discount(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        try:
            plan = request.query.get("plan", "BASIC")
        except Exception:
            return _error("Некорректный запрос", 400)

        async with async_session() as session:
            user_repo = UserRepo(session)
            db_user, is_new_user = await user_repo.get_or_create(telegram_id=user.telegram_id)
            data = await preview_discounts_for_plan(
                session,
                telegram_id=user.telegram_id,
                user_id=db_user.id,
                plan_key=plan,
                is_new_user=is_new_user,
            )
        return _json(data)

    @require_user
    async def validate_promo(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        try:
            data = await request.json()
            plan = data.get("plan", "BASIC")
            months = int(data.get("months", 1))
            promo_code = (data.get("promo_code") or "").strip().upper()
        except (TypeError, ValueError):
            return _error("Некорректный запрос", 400)

        if not promo_code:
            return _error("Введите промокод", 400)

        async with async_session() as session:
            user_repo = UserRepo(session)
            db_user, is_new_user = await user_repo.get_or_create(telegram_id=user.telegram_id)
            discount = await calculate_discount(
                session,
                telegram_id=user.telegram_id,
                user_id=db_user.id,
                plan_key=plan,
                months=months,
                promo_code=promo_code,
                is_new_user=is_new_user,
            )

        if not discount.ok:
            return _json(
                {"valid": False, "error": discount.error or "Промокод недействителен"},
                status=400,
            )

        return _json({
            "valid": True,
            "base_price": discount.base_price,
            "final_price": discount.final_price,
            "discount_total": discount.discount_total,
            "promo_code": discount.promo_code,
            "promotion_name": discount.promotion_name,
            "discount_label": discount.discount_label,
        })

    @require_user
    async def provision_vpn(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        try:
            async with async_session() as session:
                sub_repo = SubscriptionRepo(session)
                sub = await sub_repo.get_active(user.telegram_id)

            if not sub or not miniapp_handler._is_subscription_live(sub):
                return _error("Нет активной подписки", 404, code="no_subscription")

            existing_url = resolve_subscription_url(sub, config)
            if existing_url:
                return _json({
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
                telegram_id=user.telegram_id,
                first_name=user.first_name or "User",
                last_name=user.last_name or "",
                sub_id_db=sub.id,
                months=0 if is_trial else months,
                days=trial_days if is_trial else 0,
            )
            if not subscription_url:
                return _error("Не удалось создать VPN-ключ", 500, code="provision_failed")

            return _json({
                "subscription_url": subscription_url,
                "vpn_key": subscription_url,
                "message": "VPN-ключ создан",
            })
        except Exception as e:
            logger.error("Cabinet provision error: %s", e)
            return _error("Не удалось создать VPN-ключ", 500)

    @require_user
    async def get_payment_status(request: web.Request) -> web.Response:
        user: User = request["cabinet_user"]
        order_id = request.match_info.get("order_id", "").strip()
        if not order_id:
            return _error("Некорректный запрос", 400)

        async with async_session() as session:
            pay_repo = PaymentRepo(session)
            sub_repo = SubscriptionRepo(session)
            payment = await pay_repo.get_by_order_id(order_id)

            if not payment or payment.telegram_id != user.telegram_id:
                return _error("Заказ не найден", 404, code="not_found")

            if payment.status == PaymentStatus.PENDING:
                bot = request.app.get("bot")
                if bot:
                    await process_manual_check(bot, order_id, user.telegram_id)
                    payment = await pay_repo.get_by_order_id(order_id)

            subscription_url = None
            if payment.subscription_id:
                sub = await sub_repo.get_by_id(payment.subscription_id)
                if sub:
                    subscription_url = resolve_subscription_url(sub, config)

            return _json({
                "order_id": payment.order_id,
                "status": payment.status.value,
                "subscription_url": subscription_url,
                "fulfilled": payment.fulfilled_at is not None,
            })

    app.router.add_post("/cabinet/api/auth/login", login)
    app.router.add_post("/cabinet/api/auth/logout", logout)
    app.router.add_get("/cabinet/api/auth/me", me)
    app.router.add_get("/cabinet/api/health", health)
    app.router.add_get("/cabinet/api/config", get_config)
    app.router.add_get("/cabinet/api/plans", get_plans)
    app.router.add_get("/cabinet/api/dashboard", get_dashboard)
    app.router.add_post("/cabinet/api/pay", create_payment)
    app.router.add_get("/cabinet/api/discount/preview", preview_discount)
    app.router.add_post("/cabinet/api/promo/validate", validate_promo)
    app.router.add_post("/cabinet/api/provision", provision_vpn)
    app.router.add_get("/cabinet/api/payment/{order_id}/status", get_payment_status)

    cabinet_dist = Path(__file__).resolve().parent.parent.parent / "cabinet" / "dist"
    cabinet_index = cabinet_dist / "index.html"

    if cabinet_index.is_file():
        async def _redirect_cabinet(_request: web.Request) -> web.Response:
            raise web.HTTPFound("/cabinet/")

        async def _serve_cabinet_spa(_request: web.Request) -> web.Response:
            return web.FileResponse(cabinet_index)

        app.router.add_get("/cabinet", _redirect_cabinet)
        app.router.add_get("/cabinet/", _serve_cabinet_spa)
        for sub_path in ("home", "keys", "plans", "support", "login"):
            app.router.add_get(f"/cabinet/{sub_path}", _serve_cabinet_spa)
            app.router.add_get(f"/cabinet/{sub_path}/", _serve_cabinet_spa)

        for static_name in ("favicon.svg", "apple-touch-icon.png", "site.webmanifest"):
            static_path = cabinet_dist / static_name
            if static_path.is_file():

                async def _serve_cabinet_static(
                    _request: web.Request, path: Path = static_path
                ) -> web.Response:
                    return web.FileResponse(path)

                app.router.add_get(f"/cabinet/{static_name}", _serve_cabinet_static)

        assets_dir = cabinet_dist / "assets"
        if assets_dir.is_dir():
            app.router.add_static("/cabinet/assets", assets_dir, show_index=False)

        logger.info("Web cabinet (React): %s", cabinet_index)
    else:
        logger.warning(
            "Web cabinet build not found at %s — run: cd cabinet && npm run build",
            cabinet_index,
        )

    return auth
