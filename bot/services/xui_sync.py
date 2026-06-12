"""Синхронизация подписок БД ↔ 3X-UI (админ-панель)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bot.config import Config
from bot.services.subscription_url import build_subscription_url
from bot.services.xui_client import XUIClient
from bot.admin.repository import AdminRepo
from database.models import PlanType, Subscription, SubscriptionStatus, User

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


@dataclass
class SyncItemResult:
    user_id: int
    telegram_id: int
    action: str  # updated | deleted | skipped | error
    message: str = ""
    subscription_id: int | None = None


@dataclass
class BulkSyncResult:
    processed: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = False
    items: list[SyncItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.errors == 0,
            "processed": self.processed,
            "updated": self.updated,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "items": [
                {
                    "user_id": i.user_id,
                    "telegram_id": i.telegram_id,
                    "subscription_id": i.subscription_id,
                    "action": i.action,
                    "message": i.message,
                }
                for i in self.items
            ],
        }


def subscription_expects_xui_client(sub: Subscription | None) -> bool:
    """Подписка должна иметь клиента в 3X-UI."""
    if sub is None:
        return False
    if sub.vpn_email or sub.vpn_sub_id or sub.vpn_uuid:
        return True
    return sub.status in (
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.FREE_TRIAL,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.BLOCKED,
    )


def _expiry_from_panel(client: dict[str, Any]) -> datetime | None:
    raw = client.get("expiryTime") or 0
    try:
        expiry_ms = int(raw)
    except (TypeError, ValueError):
        return None
    if expiry_ms <= 0:
        return None
    return datetime.utcfromtimestamp(expiry_ms / 1000)


def _traffic_gb_from_panel(client: dict[str, Any]) -> int:
    try:
        total_bytes = int(client.get("totalGB") or 0)
    except (TypeError, ValueError):
        return 0
    if total_bytes <= 0:
        return 0
    return int(round(total_bytes / (1024**3)))


def _derive_status(sub: Subscription, client: dict[str, Any], expires_at: datetime | None) -> SubscriptionStatus:
    now = datetime.utcnow()
    if not bool(client.get("enable", True)):
        return SubscriptionStatus.EXPIRED
    if expires_at and expires_at < now:
        return SubscriptionStatus.EXPIRED
    if sub.plan == PlanType.FREE:
        return SubscriptionStatus.FREE_TRIAL
    return SubscriptionStatus.ACTIVE


def panel_client_fields(client: dict[str, Any], sub: Subscription) -> dict[str, Any]:
    expires_at = _expiry_from_panel(client)
    sub_id = str(client.get("subId") or sub.vpn_sub_id or "").strip()
    return {
        "vpn_uuid": str(client.get("id") or sub.vpn_uuid or "").strip() or None,
        "vpn_email": str(client.get("email") or sub.vpn_email or "").strip() or None,
        "vpn_sub_id": sub_id or None,
        "vpn_key": build_subscription_url(config, sub_id) if sub_id else sub.vpn_key,
        "inbound_id": int(client.get("_inbound_id") or sub.inbound_id or 0) or sub.inbound_id,
        "expires_at": expires_at,
        "limit_ip": int(client.get("limitIp") or sub.limit_ip or 1),
        "traffic_gb": _traffic_gb_from_panel(client),
        "status": _derive_status(sub, client, expires_at),
    }


async def sync_user_subscription(
    repo: AdminRepo,
    user: User,
    sub: Subscription | None,
    index: dict[str, dict[str, dict[str, Any]]],
    *,
    dry_run: bool,
    delete_missing: bool,
) -> SyncItemResult:
    base = SyncItemResult(
        user_id=user.id,
        telegram_id=user.telegram_id,
        subscription_id=sub.id if sub else None,
    )

    if sub is None or not subscription_expects_xui_client(sub):
        base.action = "skipped"
        base.message = "нет подписки с VPN"
        return base

    try:
        client = await xui.find_panel_client(
            index,
            email=sub.vpn_email,
            sub_id=sub.vpn_sub_id,
            telegram_id=user.telegram_id,
            client_uuid=sub.vpn_uuid,
        )
    except Exception as e:
        logger.exception("3X-UI lookup failed for user %s", user.telegram_id)
        base.action = "error"
        base.message = str(e)
        return base

    if client is None:
        if not delete_missing:
            base.action = "skipped"
            base.message = "клиент не найден в 3X-UI (удаление отключено)"
            return base
        if dry_run:
            base.action = "deleted"
            base.message = "будет удалён (нет в 3X-UI)"
            return base
        ok = await repo.delete_user(user.id)
        base.action = "deleted" if ok else "error"
        base.message = "удалён из БД (нет в 3X-UI)" if ok else "не удалось удалить"
        return base

    fields = panel_client_fields(client, sub)
    if dry_run:
        base.action = "updated"
        expires = fields["expires_at"]
        base.message = (
            f"будет обновлён: {fields['status'].value}, "
            f"до {expires.strftime('%d.%m.%Y') if expires else '—'}"
        )
        return base

    await repo.apply_panel_client_to_subscription(sub.id, **fields)
    base.action = "updated"
    expires = fields["expires_at"]
    base.message = (
        f"обновлён: {fields['status'].value}, "
        f"до {expires.strftime('%d.%m.%Y') if expires else '—'}"
    )
    return base


async def bulk_sync_from_xui(
    repo: AdminRepo,
    *,
    dry_run: bool = False,
    delete_missing: bool = True,
    user_ids: list[int] | None = None,
) -> BulkSyncResult:
    result = BulkSyncResult(dry_run=dry_run)
    index = await xui.build_client_index()
    pairs = await repo.list_users_for_xui_sync(user_ids=user_ids)

    for user, sub in pairs:
        result.processed += 1
        item = await sync_user_subscription(
            repo,
            user,
            sub,
            index,
            dry_run=dry_run,
            delete_missing=delete_missing,
        )
        result.items.append(item)

        if item.action == "updated":
            result.updated += 1
        elif item.action == "deleted":
            result.deleted += 1
        elif item.action == "skipped":
            result.skipped += 1
        elif item.action == "error":
            result.errors += 1

    return result


ACTIVE_XUI_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL)


@dataclass
class PushResult:
    ok: bool
    skipped: bool = False
    message: str = ""
    enabled: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "message": self.message,
            "enabled": self.enabled,
        }


def subscription_should_be_enabled(sub: Subscription) -> bool:
    if sub.status not in ACTIVE_XUI_STATUSES:
        return False
    if sub.expires_at and sub.expires_at < datetime.utcnow():
        return False
    return True


async def push_subscription_to_xui(sub: Subscription) -> PushResult:
    """Применить подписку из БД к клиенту в 3X-UI (срок, enable, лимиты)."""
    if not all([sub.vpn_uuid, sub.vpn_email, sub.vpn_sub_id, sub.inbound_id]):
        return PushResult(
            ok=True,
            skipped=True,
            message="VPN-клиент не создан — синхронизация с 3X-UI не требуется",
        )

    enable = subscription_should_be_enabled(sub)
    expiry_unix: int | None = None
    if sub.expires_at:
        expiry_unix = xui._expiry_unix_from_datetime(sub.expires_at)
    elif enable:
        expiry_unix = xui._expiry_unix(1)

    try:
        await xui.update_client(
            inbound_id=sub.inbound_id,
            client_uuid=sub.vpn_uuid,
            email=sub.vpn_email,
            sub_id=sub.vpn_sub_id,
            telegram_id=sub.telegram_id,
            limit_ip=sub.limit_ip,
            expiry_unix=expiry_unix,
            enable=enable,
            traffic_gb=sub.traffic_gb or 0,
        )
        exp = sub.expires_at.strftime("%d.%m.%Y %H:%M") if sub.expires_at else "—"
        state = "включён" if enable else "отключён"
        return PushResult(
            ok=True,
            message=f"3X-UI: клиент {state}, срок до {exp}",
            enabled=enable,
        )
    except Exception as e:
        logger.exception("push_subscription_to_xui failed sub=%s", sub.id)
        return PushResult(ok=False, message=f"3X-UI: {e}")


async def delete_subscription_from_xui(sub: Subscription) -> PushResult:
    if not sub.vpn_uuid or not sub.inbound_id:
        return PushResult(ok=True, skipped=True, message="Нет клиента в 3X-UI")
    try:
        await xui.delete_client(
            sub.inbound_id,
            sub.vpn_uuid,
            sub.vpn_email or "",
        )
        return PushResult(ok=True, message="Клиент удалён из 3X-UI")
    except Exception as e:
        logger.exception("delete_subscription_from_xui failed sub=%s", sub.id)
        return PushResult(ok=False, message=f"3X-UI: {e}")
