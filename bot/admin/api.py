"""REST API handlers for web admin panel."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Callable, Awaitable

from aiohttp import web

from bot.admin.auth import AdminAuth, verify_password
from bot.admin.repository import AdminRepo
from bot.admin.telegram_profile import download_profile_photo, fetch_telegram_profile
from bot.config import Config, PLANS, MONTHS_LABELS
from bot.services.broadcast_service import (
    BROADCAST_TARGETS,
    count_recipients,
    execute_broadcast,
    is_valid_target,
)
from database.engine import async_session
from database.models import (
    BroadcastStatus,
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
    User,
    Subscription,
    Payment,
    PromoCode,
    Promotion,
    Broadcast,
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
        "promotion_id": p.promotion_id,
        "original_amount": p.original_amount,
        "discount_amount": p.discount_amount,
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
        "name": p.name,
        "description": p.description,
        "discount_pct": p.discount_pct,
        "discount_amount": p.discount_amount,
        "plans": p.plans,
        "months": p.months,
        "min_amount": p.min_amount,
        "max_uses": p.max_uses,
        "uses_count": p.uses_count,
        "one_per_user": p.one_per_user,
        "assigned_telegram_id": p.assigned_telegram_id,
        "is_active": p.is_active,
        "is_valid": p.is_valid,
        "expires_at": _dt(p.expires_at),
        "created_at": _dt(p.created_at),
    }


def _broadcast_json(b: Broadcast) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "text": b.text,
        "target": b.target,
        "target_label": BROADCAST_TARGETS.get(b.target, b.target),
        "status": b.status.value,
        "send_at": _dt(b.send_at),
        "sent": b.sent,
        "sent_count": b.sent_count,
        "failed_count": b.failed_count,
        "target_count": b.target_count,
        "started_at": _dt(b.started_at),
        "completed_at": _dt(b.completed_at),
        "error_message": b.error_message,
        "created_at": _dt(b.created_at),
    }


def _promotion_json(p: Promotion) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "discount_pct": p.discount_pct,
        "discount_amount": p.discount_amount,
        "plans": p.plans,
        "months": p.months,
        "min_amount": p.min_amount,
        "new_users_only": p.new_users_only,
        "starts_at": _dt(p.starts_at),
        "ends_at": _dt(p.ends_at),
        "is_active": p.is_active,
        "is_valid": p.is_valid,
        "priority": p.priority,
        "stackable_with_promo": p.stackable_with_promo,
        "created_at": _dt(p.created_at),
    }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", ""))


def _parse_dt_msk(value: Any) -> datetime | None:
    """datetime-local из админки трактуем как Europe/Moscow → UTC в БД."""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", ""))
    if dt.tzinfo is not None:
        return dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    msk = ZoneInfo("Europe/Moscow")
    return dt.replace(tzinfo=msk).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _parse_str_list(value: Any) -> list | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
        return items or None
    return None


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

    async def users_assign_discount(request: web.Request) -> web.Response:
        user_id = int(request.match_info["user_id"])
        body = await _body(request)
        bot = request.app.get("bot")

        async with async_session() as session:
            repo = AdminRepo(session)
            user = await repo.get_user_detail(user_id)
            if not user:
                return _error("User not found", 404)

            discount_pct = int(body.get("discount_pct", 0))
            discount_amount = int(body.get("discount_amount", 0))
            plans = _parse_str_list(body.get("plans"))
            months = _parse_str_list(body.get("months"))
            min_amount = int(body.get("min_amount", 0))
            expires_at = _parse_dt(body.get("expires_at"))
            source_name = body.get("source_name")
            custom_message = body.get("message") or body.get("custom_message")
            code = (body.get("code") or "").strip().upper() or None
            send_notification = body.get("send_notification", True)

            promo_id = body.get("promo_id")
            promotion_id = body.get("promotion_id")
            if promo_id:
                promo = await repo.get_promo(int(promo_id))
                if not promo:
                    return _error("Promo not found", 404)
                discount_pct = promo.discount_pct
                discount_amount = promo.discount_amount
                plans = promo.plans
                months = promo.months
                min_amount = promo.min_amount
                expires_at = expires_at or promo.expires_at
                source_name = source_name or promo.name or promo.code
            elif promotion_id:
                promotion = await repo.get_promotion(int(promotion_id))
                if not promotion:
                    return _error("Promotion not found", 404)
                discount_pct = promotion.discount_pct
                discount_amount = promotion.discount_amount
                plans = promotion.plans
                months = promotion.months
                min_amount = promotion.min_amount
                expires_at = expires_at or promotion.ends_at
                source_name = source_name or promotion.name

        from bot.services.assign_discount import assign_personal_discount

        try:
            result = await assign_personal_discount(
                bot=bot,
                user=user,
                discount_pct=discount_pct,
                discount_amount=discount_amount,
                plans=plans,
                months=months,
                min_amount=min_amount,
                expires_at=expires_at,
                code=code,
                name=body.get("name"),
                description=body.get("description"),
                custom_message=custom_message,
                source_name=source_name,
                send_notification=bool(send_notification),
            )
        except ValueError as e:
            return _error(str(e), 400)

        if send_notification and bot and not result["notified"]:
            return _json({
                **result,
                "warning": "Промокод создан, но сообщение в Telegram не доставлено",
            })

        return _json(result)

    async def discounts_assign_by_telegram(request: web.Request) -> web.Response:
        """Назначить скидку по telegram_id (из карточки акции/промокода)."""
        body = await _body(request)
        try:
            telegram_id = int(body.get("telegram_id", 0))
        except (TypeError, ValueError):
            telegram_id = 0
        if not telegram_id:
            return _error("telegram_id required")

        from bot.services.assign_discount import assign_personal_discount, resolve_user

        try:
            user = await resolve_user(telegram_id=telegram_id)
        except ValueError as e:
            return _error(str(e), 404)

        bot = request.app.get("bot")
        async with async_session() as session:
            repo = AdminRepo(session)

            discount_pct = int(body.get("discount_pct", 0))
            discount_amount = int(body.get("discount_amount", 0))
            plans = _parse_str_list(body.get("plans"))
            months = _parse_str_list(body.get("months"))
            min_amount = int(body.get("min_amount", 0))
            expires_at = _parse_dt(body.get("expires_at"))
            source_name = body.get("source_name")
            custom_message = body.get("message") or body.get("custom_message")
            code = (body.get("code") or "").strip().upper() or None
            send_notification = body.get("send_notification", True)

            promo_id = body.get("promo_id")
            promotion_id = body.get("promotion_id")
            if promo_id:
                promo = await repo.get_promo(int(promo_id))
                if not promo:
                    return _error("Promo not found", 404)
                discount_pct = promo.discount_pct
                discount_amount = promo.discount_amount
                plans = promo.plans
                months = promo.months
                min_amount = promo.min_amount
                expires_at = expires_at or promo.expires_at
                source_name = source_name or promo.name or promo.code
            elif promotion_id:
                promotion = await repo.get_promotion(int(promotion_id))
                if not promotion:
                    return _error("Promotion not found", 404)
                discount_pct = promotion.discount_pct
                discount_amount = promotion.discount_amount
                plans = promotion.plans
                months = promotion.months
                min_amount = promotion.min_amount
                expires_at = expires_at or promotion.ends_at
                source_name = source_name or promotion.name

        try:
            result = await assign_personal_discount(
                bot=bot,
                user=user,
                discount_pct=discount_pct,
                discount_amount=discount_amount,
                plans=plans,
                months=months,
                min_amount=min_amount,
                expires_at=expires_at,
                code=code,
                name=body.get("name"),
                description=body.get("description"),
                custom_message=custom_message,
                source_name=source_name,
                send_notification=bool(send_notification),
            )
        except ValueError as e:
            return _error(str(e), 400)

        return _json(result)

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

        from bot.services.xui_sync import push_subscription_to_xui

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
                disable_vpn=bool(body.get("disable")),
            )
            if not sub:
                return _error("Subscription not found", 404)
            xui_result = await push_subscription_to_xui(sub)

        data = _sub_json(sub)
        data["xui_sync"] = xui_result.to_dict()
        return _json(data)

    async def subs_delete(request: web.Request) -> web.Response:
        sub_id = int(request.match_info["sub_id"])
        from bot.services.xui_sync import delete_subscription_from_xui

        async with async_session() as session:
            repo = AdminRepo(session)
            sub = await repo.get_subscription(sub_id)
            if not sub:
                return _error("Subscription not found", 404)
            xui_result = await delete_subscription_from_xui(sub)
            ok = await repo.delete_subscription(sub_id)

        return _json({"ok": ok, "xui_sync": xui_result.to_dict()})

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

    async def xui_import(request: web.Request) -> web.Response:
        """Импорт клиентов из 3X-UI, которых нет в админке."""
        from bot.services.xui_sync import bulk_import_from_xui

        body = await _body(request)
        dry_run = bool(body.get("dry_run"))

        try:
            async with async_session() as session:
                repo = AdminRepo(session)
                result = await bulk_import_from_xui(repo, dry_run=dry_run)
        except Exception as e:
            logger.exception("xui_import failed")
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
        async with async_session() as session:
            repo = AdminRepo(session)
            promo = await repo.create_promo(
                code=code,
                name=body.get("name"),
                description=body.get("description"),
                discount_pct=int(body.get("discount_pct", 0)),
                discount_amount=int(body.get("discount_amount", 0)),
                plans=_parse_str_list(body.get("plans")),
                months=_parse_str_list(body.get("months")),
                min_amount=int(body.get("min_amount", 0)),
                max_uses=int(body.get("max_uses", 1)),
                one_per_user=bool(body.get("one_per_user", True)),
                is_active=bool(body.get("is_active", True)),
                expires_at=_parse_dt(body.get("expires_at")),
            )
        return _json(_promo_json(promo), 201)

    async def promos_update(request: web.Request) -> web.Response:
        promo_id = int(request.match_info["promo_id"])
        body = await _body(request)
        fields: dict[str, Any] = {}
        for key in (
            "name", "description", "discount_pct", "discount_amount",
            "min_amount", "max_uses", "one_per_user", "is_active",
        ):
            if key in body:
                fields[key] = body[key]
        if "plans" in body:
            fields["plans"] = _parse_str_list(body.get("plans"))
        if "months" in body:
            fields["months"] = _parse_str_list(body.get("months"))
        if "expires_at" in body:
            fields["expires_at"] = _parse_dt(body.get("expires_at"))
        async with async_session() as session:
            repo = AdminRepo(session)
            promo = await repo.update_promo(promo_id, **fields)
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

    # ── Promotions (акции) ─────────────────────────────────────

    async def promotions_list(request: web.Request) -> web.Response:
        async with async_session() as session:
            repo = AdminRepo(session)
            items = await repo.list_promotions()
        return _json([_promotion_json(p) for p in items])

    async def promotions_create(request: web.Request) -> web.Response:
        body = await _body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return _error("name required")
        async with async_session() as session:
            repo = AdminRepo(session)
            promotion = await repo.create_promotion(
                name=name,
                description=body.get("description"),
                discount_pct=int(body.get("discount_pct", 0)),
                discount_amount=int(body.get("discount_amount", 0)),
                plans=_parse_str_list(body.get("plans")),
                months=_parse_str_list(body.get("months")),
                min_amount=int(body.get("min_amount", 0)),
                new_users_only=bool(body.get("new_users_only", False)),
                starts_at=_parse_dt(body.get("starts_at")),
                ends_at=_parse_dt(body.get("ends_at")),
                is_active=bool(body.get("is_active", True)),
                priority=int(body.get("priority", 0)),
                stackable_with_promo=bool(body.get("stackable_with_promo", False)),
            )
        return _json(_promotion_json(promotion), 201)

    async def promotions_update(request: web.Request) -> web.Response:
        promotion_id = int(request.match_info["promotion_id"])
        body = await _body(request)
        fields: dict[str, Any] = {}
        for key in (
            "name", "description", "discount_pct", "discount_amount",
            "min_amount", "new_users_only", "is_active", "priority",
            "stackable_with_promo",
        ):
            if key in body:
                fields[key] = body[key]
        if "plans" in body:
            fields["plans"] = _parse_str_list(body.get("plans"))
        if "months" in body:
            fields["months"] = _parse_str_list(body.get("months"))
        if "starts_at" in body:
            fields["starts_at"] = _parse_dt(body.get("starts_at"))
        if "ends_at" in body:
            fields["ends_at"] = _parse_dt(body.get("ends_at"))
        async with async_session() as session:
            repo = AdminRepo(session)
            promotion = await repo.update_promotion(promotion_id, **fields)
        if not promotion:
            return _error("Promotion not found", 404)
        return _json(_promotion_json(promotion))

    async def promotions_delete(request: web.Request) -> web.Response:
        promotion_id = int(request.match_info["promotion_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_promotion(promotion_id)
        if not ok:
            return _error("Promotion not found", 404)
        return _json({"ok": True})

    # ── Broadcasts (рассылки) ──────────────────────────────────

    async def broadcasts_targets(request: web.Request) -> web.Response:
        return _json([
            {"id": key, "label": label}
            for key, label in BROADCAST_TARGETS.items()
        ])

    async def broadcasts_estimate(request: web.Request) -> web.Response:
        target = request.query.get("target", "all")
        if not is_valid_target(target):
            return _error("Invalid target")
        async with async_session() as session:
            count = await count_recipients(session, target)
        return _json({"target": target, "count": count})

    async def broadcasts_list(request: web.Request) -> web.Response:
        status = request.query.get("status") or None
        async with async_session() as session:
            repo = AdminRepo(session)
            items = await repo.list_broadcasts(status=status)
        return _json([_broadcast_json(b) for b in items])

    async def broadcasts_create(request: web.Request) -> web.Response:
        body = await _body(request)
        text = (body.get("text") or "").strip()
        if not text:
            return _error("text required")
        target = (body.get("target") or "all").strip()
        if not is_valid_target(target):
            return _error("Invalid target")
        send_mode = (body.get("send_mode") or "now").strip()
        name = (body.get("name") or "").strip() or None

        immediate = send_mode != "scheduled"
        send_at: datetime
        if immediate:
            send_at = datetime.utcnow()
            status = BroadcastStatus.SENDING
        else:
            parsed = _parse_dt_msk(body.get("send_at"))
            if not parsed:
                return _error("send_at required for scheduled broadcast")
            if parsed <= datetime.utcnow():
                return _error("send_at must be in the future (MSK)")
            send_at = parsed
            status = BroadcastStatus.SCHEDULED

        async with async_session() as session:
            target_count = await count_recipients(session, target)
            repo = AdminRepo(session)
            broadcast = await repo.create_broadcast(
                name=name,
                text=text,
                target=target,
                status=status,
                send_at=send_at,
                target_count=target_count,
                started_at=datetime.utcnow() if immediate else None,
            )

        if immediate:
            bot = request.app["bot"]
            asyncio.create_task(
                execute_broadcast(broadcast.id, bot),
                name=f"broadcast-{broadcast.id}",
            )

        return _json(_broadcast_json(broadcast), 201)

    async def broadcasts_send_now(request: web.Request) -> web.Response:
        broadcast_id = int(request.match_info["broadcast_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            broadcast = await repo.get_broadcast(broadcast_id)
        if not broadcast:
            return _error("Broadcast not found", 404)
        if broadcast.status not in (BroadcastStatus.SCHEDULED,):
            return _error("Only scheduled broadcasts can be sent now", 400)

        bot = request.app["bot"]
        asyncio.create_task(
            execute_broadcast(broadcast_id, bot),
            name=f"broadcast-{broadcast_id}",
        )
        return _json({"ok": True, "message": "Рассылка запущена"})

    async def broadcasts_cancel(request: web.Request) -> web.Response:
        broadcast_id = int(request.match_info["broadcast_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            existing = await repo.get_broadcast(broadcast_id)
            if not existing:
                return _error("Broadcast not found", 404)
            if existing.status != BroadcastStatus.SCHEDULED:
                return _error("Only scheduled broadcasts can be cancelled", 400)
            broadcast = await repo.cancel_broadcast(broadcast_id)
        return _json(_broadcast_json(broadcast))

    async def broadcasts_delete(request: web.Request) -> web.Response:
        broadcast_id = int(request.match_info["broadcast_id"])
        async with async_session() as session:
            repo = AdminRepo(session)
            ok = await repo.delete_broadcast(broadcast_id)
        if not ok:
            return _error("Broadcast not found or cannot be deleted", 404)
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
        web.post("/admin/api/users/{user_id}/assign-discount", users_assign_discount),
        web.post("/admin/api/discounts/assign", discounts_assign_by_telegram),
        web.post("/admin/api/users/{user_id}/sync-xui", user_sync_xui),
        web.get("/admin/api/xui/status", xui_status),
        web.post("/admin/api/xui/sync", xui_sync),
        web.post("/admin/api/xui/import", xui_import),
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
        web.get("/admin/api/promotions", promotions_list),
        web.post("/admin/api/promotions", promotions_create),
        web.patch("/admin/api/promotions/{promotion_id}", promotions_update),
        web.delete("/admin/api/promotions/{promotion_id}", promotions_delete),
        web.get("/admin/api/broadcasts", broadcasts_list),
        web.get("/admin/api/broadcasts/targets", broadcasts_targets),
        web.get("/admin/api/broadcasts/estimate", broadcasts_estimate),
        web.post("/admin/api/broadcasts", broadcasts_create),
        web.post("/admin/api/broadcasts/{broadcast_id}/send", broadcasts_send_now),
        web.post("/admin/api/broadcasts/{broadcast_id}/cancel", broadcasts_cancel),
        web.delete("/admin/api/broadcasts/{broadcast_id}", broadcasts_delete),
    ]
    app.router.add_routes(routes)

    # Static admin UI (React build in admin/dist)
    admin_dir = Path(__file__).resolve().parent.parent.parent / "admin"
    admin_dist = admin_dir / "dist"
    admin_index = admin_dist / "index.html"

    if admin_index.is_file():
        assets_dir = admin_dist / "assets"
        if assets_dir.is_dir():
            app.router.add_static("/admin/assets", assets_dir, show_index=False)

        async def _redirect_admin(_request: web.Request) -> web.Response:
            raise web.HTTPFound("/admin/")

        async def _serve_admin_spa(_request: web.Request) -> web.Response:
            return web.FileResponse(admin_index)

        app.router.add_get("/admin", _redirect_admin)
        app.router.add_get("/admin/", _serve_admin_spa)
        for sub_path in ("users", "payments", "promos", "promotions", "broadcasts"):
            app.router.add_get(f"/admin/{sub_path}", _serve_admin_spa)
            app.router.add_get(f"/admin/{sub_path}/", _serve_admin_spa)
        logger.info("Admin panel (React): %s", admin_index)
    else:
        logger.warning("Admin panel build not found at %s — run: cd admin && npm run build", admin_index)

    return auth
