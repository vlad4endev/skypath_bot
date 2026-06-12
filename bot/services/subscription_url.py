"""Subscription URL для Happ / v2rayNG (HTTP sub-link, не vless://)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Config
    from database.models import Subscription


def is_http_subscription_url(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def build_subscription_url(config: "Config", sub_id: str) -> str:
    return config.xui_sub_url(sub_id)


def resolve_subscription_url(sub: "Subscription | None", config: "Config") -> str | None:
    """Ссылка подписки для Mini App / Happ. Приоритет — vpn_sub_id + настройки панели."""
    if sub is None:
        return None

    if sub.vpn_sub_id:
        return build_subscription_url(config, sub.vpn_sub_id)

    if is_http_subscription_url(sub.vpn_key):
        return sub.vpn_key.strip()

    return None
