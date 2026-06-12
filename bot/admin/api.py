"""REST API handlers for web admin panel."""
from __future__ import annotations

import logging
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Awaitable

from aiohttp import web

from bot.admin.auth import AdminAuth, verify_password
from bot.admin.repository import AdminRepo
from bot.admin.telegram_profile import download_profile_photo, fetch_telegram_profile
from bot.config import Config, PLANS, MONTHS_LABELS
from database.engine import async_session
from database.models import (
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
    User,
    Subscription,
    Payment,
    PromoCode,
)
from database.repository import UserRepo

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/admin/api/auth/login", "/admin/api/health"}


def _dt(val: datetime | None) -> str | None:
    return val.isoformat() if val else None


def _user_json(u: User, subscription: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "username": u.username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "full_name": u.full_name,
        "language_code": u.language_code,
        "is_banned": u.is_banned,
        "referrer_id": u.referrer_id,
        "created_at": _dt(u.created_at),
        "last_seen": _dt(u.last_seen),
    }
    if subscription is not None:
        data["subscription"] = subscription
    return data


def _sub_json(s: Subscription) -> dict[str, Any]:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "telegram_id": s.telegram_id,
        "plan": s.plan.value,
        "status": s.status.value,
        "vpn_uuid": s.vpn_uuid,
        "vpn_email": s.vpn_email,
        "vpn_sub_id": s.vpn_sub_id,
        "vpn_key": s.vpn_key,
        "inbound_id": s.inbound_id,
        "started_at": _dt(s.started_at),
        "expires_at": _dt(s.expires_at),
        "months_paid": s.months_paid,
        "promo_code": s.promo_code,
        "discount_pct": s.discount_pct,
        "limit_ip": s.limit_ip,
        "traffic_gb": s.traffic_gb,
        "days_left": s.days_left,
        "is_active": s.is_active,
        "is_expired": (
            s.status == SubscriptionStatus.EXPIRED
            or s.status == SubscriptionStatus.BLOCKED
            or (s.expires_at is not None and s.expires_at < datetime.utcnow())
        ),
        "vpn_disabled_at": _dt(s.vpn_disabled_at),
        "created_at": _dt(s.created_at),
        "updated_at": _dt(s.updated_at),
    }


def _payment_json(p: Payment) -> dict[str, Any]:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "subscription_id": p.subscription_id,
        "telegram_id": p.telegram_id,
        "provider": p.provider,
        "order_id": p.order_id,
        "yookassa_id": p.yookassa_id,
        "payment_url": p.payment_url,
        "description": p.description,
        "amount": p.amount,
        "paid_amount": p.paid_amount,
        "currency": p.currency,
        "status": p.status.value,
        "provider_status": p.provider_status,
        "plan": p.plan,
        "months": p.months,
        "promo_code": p.promo_code,
        "created_at": _dt(p.created_at),
        "paid_at": _dt(p.paid_at),
        "webhook_received_at": _dt(p.webhook_received_at),
        "fulfilled_at": _dt(p.fulfilled_at),
        "is_fulfilled": p.fulfilled_at is not None,
    }


def _promo_json(p: PromoCode) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "discount_pct": p.discount_pct,
        "discount_amount": p.discount_amount,
        "max_uses": p.max_uses,
        "uses_count": p.uses_count,
        "is_active": p.is_active,
        "is_valid": p.is_valid,
        "expires_at": _dt(p.expires_at),
        "created_at": _dt(p.created_at),
    }


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        return {}


def admin_middleware(auth: AdminAuth):
    @web.middleware
    async def middleware(request: web.Request, handler):
        path = request.path
        if not path.startswith("/admin/api"):
            return await handler(request)
        if path in PUBLIC_PATHS:
            return await handler(request)
        token = auth.extract_token(request)
        if not await auth.validate_session(token):
            return _error("Unauthorized", 401)
        request["admin_token"] = token
        return await handler(request)

    return middleware


def setup_admin_routes(app: web.Application, config: Config) -> AdminAuth:
    auth = AdminAuth(config)
    app.middlewares.insert(0, admin_middleware(auth))

    # ── Auth ───────────────────────────────────────────────────

    async def login(request: web.Request) -> web.Response:
        if not config.ADMIN_PASSWORD:
            return _error("Admin panel not configured (ADMIN_PASSWORD missing)", 503)
        body = await _body(request)
        password = body.get("password", "")
        if not verify_password(password, config):
            return _error("Invalid password", 401)
        token = await auth.create_session()
        resp = _json({"ok": True, "token": token})
        resp.set_cookie(
            "admin_token", token, httponly=True, samesite="Strict",
            max_age=60 * 60 * 24, path="/",
        )
        return resp

    async def logout(request: web.Request) -> web.Response:
        await auth.revoke_session(request.get("admin_token"))
        resp = _json({"ok": True})
        resp.del_cookie("admin_token", path="/")
        return resp

    async def me(request: web.Request) -> web.Response:
        return _json({"ok": True, "brand": config.BRAND_NAME})

    async def health(request: web.Request) -> web.Response:
        return _json({"status": "ok"})

    # ── Stats ──────────────────────────────────────────────────

    async def stats_dashboard(request: web.Request) -> web.Response:
        async with async_session() as session:
            repo = AdminRepo(session)
            data = await repo.get_dashboard_stats()
        return _json(data)

    async def stats_revenue(request: web.Request) -> web.Response:
        days = int(request.query.get("days", "30"))
        async with async_session() as session:
            repo = AdminRepo(session)
            data = await repo.get_revenue_chart(days)
        return _json(data)

    async def stats_users(request: web.Request) -> web.Response:
        days = int(request.query.get("days", "30"))
        async with async_session() as session:
            repo = AdminRepo(session)
            data = await repo.get_users_chart(days)
        return _json(data)

    async def stats_plans(request: web.Request) -> web.Response:
        async with async_session() as session:
            repo = AdminRepo(session)
            data = await repo.get_plan_distribution()
        return _json(data)

    # ── Users ──────────────────────────────────────────────────

    async def users_list(request: web.Request) -> web.Response:
        page = int(request.query.get("page", "1"))
        per_page = int(request.query.get("per_page", "20"))
        search = request.query.get("search", "")
        banned = request.query.get("banned")
        async with async_session() as session:
            repo = AdminRepo(session)
            result = await repo.list_users(
                page=page, per_page=per_page, search=search, banned=banned,
            )
        return _json({
            "items": [
                _user_json(row["user"], row["subscription"])
                for row in result["items"]
            ],
            "total": result["total"],
            "page": result["page"],
            "per_page": result["per_page"],
        })

    async def users_detail(request: web.Request) -> web.Response:
        user_id = int(request.match_info["user_id"])
        bot = request.app.get("bot")
        async with async_session() as session:
            repo = AdminRepo(session)
            user = await repo.get_user_detail(user_id)
            if not user:
                return _error("User not found", 404)
            primary = repo.subscription_summary(
                repo._pick_primary_subscription(list(user.subscriptions))
            )
            stats = await repo.get_user_stats(user)
            subs_sorted = sorted(
                user.subscriptions,
                key=lambda s: s.created_at,
                reverse=True,
            )
            payments_sorted = sorted(
                user.payments,
                key=lambda p: p.created_at,
                reverse=True,
            )
            data = _user_json(user, primary)
            data["stats"] = stats
            data["subscriptions"] = [_sub_json(s) for s in subs_sorted]
            data["payments"] = [_payment_json(p) for p in payments_sorted[:30]]
            data["telegram_profile"] = (
                await fetch_telegram_profile(bot, user.telegram_id)
                if bot else {"available": False, "error": "bot_unavailable"}
            )
            if data["telegram_profile"].get("has_photo"):
                data["telegram_profile"]["photo_url"] = (
                    f"/admin/api/users/{user_id}/photo"
                )
        return _json(data)

    async def users_photo(request: web.Request) -> web.Response:
        user_id = int(request.match_info["user_id"])
        bot = request.app.get("bot")
        if not bot:
            return _error("Bot not available", 503)
        async with async_session() as session:
            repo = AdminRepo(session)
            user = await repo.get_user_detail(user_id)
        if not user:
            return _error("User not found", 404)
        downloaded = await download_profile_photo(bot, user.telegram_id)
        if not downloaded:
            return _error("Photo not found", 404)
        data, content_type = downloaded
        return web.Response(body=data, content_type=content_type, headers={
            "Cache-Control": "private, max-age=3600",
        })

    async def users_update(request: web.Request) -> web.Response:
        user_id = int(request.match_info["user_id"])
        body = await _body(request)
        async with async_session() as session:
            repo = AdminRepo(session)
            if "is_banned" in body:
                user = await repo.set_user_banned(user_id, bool(body["is_banned"]))
            else:
                user = await repo.get_user_detail(user_id)
        if not user:
            return _error("User not found", 404)
        return _json(_user_json(user))

    async def users_delete(request: web.Request) -> web.Response:
        user_id = int(request.match_info["user_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_user(user_id)
        if not ok:
            return _error("User not found", 404)
        return _json({"ok": True})

    # ── Subscriptions ──────────────────────────────────────────

    async def subs_list(request: web.Request) -> web.Response:
        page = int(request.query.get("page", "1"))
        per_page = int(request.query.get("per_page", "20"))
        status = request.query.get("status") or None
        plan = request.query.get("plan") or None
        search = request.query.get("search", "")
        async with async_session() as session:
            repo = AdminRepo(session)
            result = await repo.list_subscriptions(
                page=page, per_page=per_page,
                status=status, plan=plan, search=search,
            )
        return _json({
            "items": [_sub_json(s) for s in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "per_page": result["per_page"],
        })

    async def subs_detail(request: web.Request) -> web.Response:
        sub_id = int(request.match_info["sub_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            sub = await repo.get_subscription(sub_id)
        if not sub:
            return _error("Subscription not found", 404)
        return _json(_sub_json(sub))

    async def subs_create(request: web.Request) -> web.Response:
        body = await _body(request)
        telegram_id = body.get("telegram_id")
        plan = body.get("plan", "BASIC")
        days = int(body.get("days", 30))
        status = body.get("status", SubscriptionStatus.ACTIVE.value)
        limit_ip = int(body.get("limit_ip", 3))

        if not telegram_id:
            return _error("telegram_id required")

        async with async_session() as session:
            user_repo = UserRepo(session)
            admin_repo = AdminRepo(session)
            user = await user_repo.get_by_telegram_id(int(telegram_id))
            if not user:
                user, _ = await user_repo.get_or_create(telegram_id=int(telegram_id))
            sub = await admin_repo.create_subscription(
                user_id=user.id,
                telegram_id=int(telegram_id),
                plan=plan,
                status=status,
                days=days,
                limit_ip=limit_ip,
                vpn_key=body.get("vpn_key"),
            )
        return _json(_sub_json(sub), 201)

    async def subs_update(request: web.Request) -> web.Response:
        sub_id = int(request.match_info["sub_id"])
        body = await _body(request)
        expires_at = None
        if body.get("expires_at"):
            expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", ""))

        async with async_session() as session:
            repo = AdminRepo(session)
            sub = await repo.update_subscription(
                sub_id,
                status=body.get("status"),
                plan=body.get("plan"),
                expires_at=expires_at,
                extend_days=body.get("extend_days"),
                extend_months=body.get("extend_months"),
                limit_ip=body.get("limit_ip"),
                vpn_key=body.get("vpn_key"),
            )
        if not sub:
            return _error("Subscription not found", 404)
        return _json(_sub_json(sub))

    async def subs_delete(request: web.Request) -> web.Response:
        sub_id = int(request.match_info["sub_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_subscription(sub_id)
        if not ok:
            return _error("Subscription not found", 404)
        return _json({"ok": True})

    # ── 3X-UI sync ─────────────────────────────────────────────

    async def xui_status(request: web.Request) -> web.Response:
        from bot.services.xui_sync import xui as xui_client

        try:
            status = await xui_client.get_server_status()
            inbounds = await xui_client.list_inbounds()
            clients = await xui_client.list_all_clients()
        except Exception as e:
            logger.error("xui_status failed: %s", e)
            return _json({"ok": False, "error": str(e)}, status=502)

        return _json({
            "ok": True,
            "panel": {
                "host": config.XUI_HOST,
                "sub_base_url": config.XUI_SUB_BASE_URL or config.xui_sub_url("…"),
            },
            "server": status,
            "inbounds_count": len(inbounds),
            "clients_count": len(clients),
        })

    async def xui_sync(request: web.Request) -> web.Response:
        """Массовая синхронизация пользователей с 3X-UI."""
        from bot.services.xui_sync import bulk_sync_from_xui

        body = await _body(request)
        dry_run = bool(body.get("dry_run"))
        delete_missing = body.get("delete_missing", True)
        user_ids = body.get("user_ids")
        if user_ids is not None:
            user_ids = [int(x) for x in user_ids]

        try:
            async with async_session() as session:
                repo = AdminRepo(session)
                result = await bulk_sync_from_xui(
                    repo,
                    dry_run=dry_run,
                    delete_missing=bool(delete_missing),
                    user_ids=user_ids,
                )
        except Exception as e:
            logger.exception("xui_sync failed")
            return _json({"ok": False, "error": str(e)}, status=502)

        return _json(result.to_dict())

    async def user_sync_xui(request: web.Request) -> web.Response:
        """Синхронизация одного пользователя с 3X-UI."""
        from bot.services.xui_sync import bulk_sync_from_xui

        user_id = int(request.match_info["user_id"])
        body = await _body(request)
        dry_run = bool(body.get("dry_run"))
        delete_missing = body.get("delete_missing", True)

        try:
            async with async_session() as session:
                repo = AdminRepo(session)
                result = await bulk_sync_from_xui(
                    repo,
                    dry_run=dry_run,
                    delete_missing=bool(delete_missing),
                    user_ids=[user_id],
                )
        except Exception as e:
            logger.exception("user_sync_xui failed for %s", user_id)
            return _json({"ok": False, "error": str(e)}, status=502)

        return _json(result.to_dict())

    # ── Payments ───────────────────────────────────────────────

    async def payments_list(request: web.Request) -> web.Response:
        page = int(request.query.get("page", "1"))
        per_page = int(request.query.get("per_page", "20"))
        status = request.query.get("status") or None
        search = request.query.get("search", "")
        unfulfilled = request.query.get("unfulfilled") == "true"
        async with async_session() as session:
            repo = AdminRepo(session)
            result = await repo.list_payments(
                page=page, per_page=per_page,
                status=status, search=search,
                unfulfilled_only=unfulfilled,
            )
        return _json({
            "items": [_payment_json(p) for p in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "per_page": result["per_page"],
        })

    async def payments_detail(request: web.Request) -> web.Response:
        payment_id = int(request.match_info["payment_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            payment = await repo.get_payment(payment_id)
        if not payment:
            return _error("Payment not found", 404)
        return _json(_payment_json(payment))

    async def payments_update(request: web.Request) -> web.Response:
        payment_id = int(request.match_info["payment_id"])
        body = await _body(request)
        async with async_session() as session:
            repo = AdminRepo(session)
            if body.get("status"):
                payment = await repo.update_payment_status(payment_id, body["status"])
            elif body.get("fulfill"):
                payment = await repo.mark_payment_fulfilled(payment_id)
            else:
                payment = await repo.get_payment(payment_id)
        if not payment:
            return _error("Payment not found", 404)
        return _json(_payment_json(payment))

    async def payments_fulfill(request: web.Request) -> web.Response:
        """Trigger VPN fulfillment for succeeded but unfulfilled payment."""
        payment_id = int(request.match_info["payment_id"])
        bot = request.app.get("bot")
        if not bot:
            return _error("Bot not available", 503)

        async with async_session() as session:
            repo = AdminRepo(session)
            payment = await repo.get_payment(payment_id)
            if not payment:
                return _error("Payment not found", 404)
            if payment.status != PaymentStatus.SUCCEEDED:
                await repo.update_payment_status(payment_id, PaymentStatus.SUCCEEDED.value)
            user_repo = UserRepo(session)
            user = await user_repo.get_by_id(payment.user_id)

        from bot.services.payment_processor import fulfill_paid_payment

        ref = payment.order_id or payment.yookassa_id or str(payment.id)
        telegram_id = payment.telegram_id or (user.telegram_id if user else None)
        if not telegram_id:
            return _error("telegram_id missing", 400)

        ok = await fulfill_paid_payment(bot, ref, int(telegram_id))
        async with async_session() as session:
            repo = AdminRepo(session)
            payment = await repo.get_payment(payment_id)
        return _json({"ok": ok, "payment": _payment_json(payment) if payment else None})

    async def payments_delete(request: web.Request) -> web.Response:
        payment_id = int(request.match_info["payment_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_payment(payment_id)
        if not ok:
            return _error("Payment not found", 404)
        return _json({"ok": True})

    # ── Promos ─────────────────────────────────────────────────

    async def promos_list(request: web.Request) -> web.Response:
        async with async_session() as session:
            repo = AdminRepo(session)
            promos = await repo.list_promos()
        return _json([_promo_json(p) for p in promos])

    async def promos_create(request: web.Request) -> web.Response:
        body = await _body(request)
        code = body.get("code", "").strip()
        if not code:
            return _error("code required")
        expires_at = None
        if body.get("expires_at"):
            expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", ""))
        async with async_session() as session:
            repo = AdminRepo(session)
            promo = await repo.create_promo(
                code=code,
                discount_pct=int(body.get("discount_pct", 0)),
                discount_amount=int(body.get("discount_amount", 0)),
                max_uses=int(body.get("max_uses", 1)),
                expires_at=expires_at,
            )
        return _json(_promo_json(promo), 201)

    async def promos_update(request: web.Request) -> web.Response:
        promo_id = int(request.match_info["promo_id"])
        body = await _body(request)
        expires_at = body.get("expires_at")
        if expires_at:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", ""))
        async with async_session() as session:
            repo = AdminRepo(session)
            promo = await repo.update_promo(
                promo_id,
                discount_pct=body.get("discount_pct"),
                discount_amount=body.get("discount_amount"),
                max_uses=body.get("max_uses"),
                is_active=body.get("is_active"),
                expires_at=expires_at if body.get("expires_at") else None,
            )
        if not promo:
            return _error("Promo not found", 404)
        return _json(_promo_json(promo))

    async def promos_delete(request: web.Request) -> web.Response:
        promo_id = int(request.match_info["promo_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_promo(promo_id)
        if not ok:
            return _error("Promo not found", 404)
        return _json({"ok": True})

    # ── Config reference ───────────────────────────────────────

    async def config_plans(request: web.Request) -> web.Response:
        return _json({
            "plans": PLANS,
            "months_labels": MONTHS_LABELS,
            "subscription_statuses": [s.value for s in SubscriptionStatus],
            "payment_statuses": [s.value for s in PaymentStatus],
            "plan_types": [p.value for p in PlanType],
        })

    # ── Register routes ────────────────────────────────────────

    routes = [
        web.post("/admin/api/auth/login", login),
        web.post("/admin/api/auth/logout", logout),
        web.get("/admin/api/auth/me", me),
        web.get("/admin/api/health", health),
        web.get("/admin/api/stats", stats_dashboard),
        web.get("/admin/api/stats/revenue", stats_revenue),
        web.get("/admin/api/stats/users", stats_users),
        web.get("/admin/api/stats/plans", stats_plans),
        web.get("/admin/api/config", config_plans),
        web.get("/admin/api/users", users_list),
        web.get("/admin/api/users/{user_id}", users_detail),
        web.get("/admin/api/users/{user_id}/photo", users_photo),
        web.patch("/admin/api/users/{user_id}", users_update),
        web.delete("/admin/api/users/{user_id}", users_delete),
        web.post("/admin/api/users/{user_id}/sync-xui", user_sync_xui),
        web.get("/admin/api/xui/status", xui_status),
        web.post("/admin/api/xui/sync", xui_sync),
        web.get("/admin/api/subscriptions", subs_list),
        web.get("/admin/api/subscriptions/{sub_id}", subs_detail),
        web.post("/admin/api/subscriptions", subs_create),
        web.patch("/admin/api/subscriptions/{sub_id}", subs_update),
        web.delete("/admin/api/subscriptions/{sub_id}", subs_delete),
        web.get("/admin/api/payments", payments_list),
        web.get("/admin/api/payments/{payment_id}", payments_detail),
        web.patch("/admin/api/payments/{payment_id}", payments_update),
        web.post("/admin/api/payments/{payment_id}/fulfill", payments_fulfill),
        web.delete("/admin/api/payments/{payment_id}", payments_delete),
        web.get("/admin/api/promos", promos_list),
        web.post("/admin/api/promos", promos_create),
        web.patch("/admin/api/promos/{promo_id}", promos_update),
        web.delete("/admin/api/promos/{promo_id}", promos_delete),
    ]
    app.router.add_routes(routes)

    # Static admin UI
    admin_dir = Path(__file__).resolve().parent.parent.parent / "admin"
    admin_index = admin_dir / "index.html"

    if admin_index.is_file():

        async def _redirect_admin(_request: web.Request) -> web.Response:
            raise web.HTTPFound("/admin/")

        async def _serve_admin(_request: web.Request) -> web.Response:
            return web.FileResponse(admin_index)

        app.router.add_get("/admin", _redirect_admin)
        app.router.add_get("/admin/", _serve_admin)
        app.router.add_static("/admin/static", admin_dir / "static", show_index=False)
        logger.info("Admin panel: %s", admin_index)
    else:
        logger.warning("Admin panel index not found at %s", admin_index)

    return auth
