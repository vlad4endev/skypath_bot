"""
Создание VPN-клиента в 3X-UI и активация подписки в БД.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.config import Config, PLANS
from bot.services.subscription_url import resolve_subscription_url
from bot.services.xui_client import XUIClient
from database.engine import async_session
from database.models import PlanType
from database.repository import SubscriptionRepo

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


@dataclass(frozen=True)
class ProvisionResult:
    subscription_url: str
    vpn_email: str
    vpn_sub_id: str
    inbound_id: int


async def provision_vpn_for_subscription(
    *,
    telegram_id: int,
    first_name: str,
    last_name: str,
    sub_id_db: int,
    months: int = 0,
    days: int = 0,
) -> ProvisionResult:
    """Создать клиента в 3X-UI и активировать подписку. Возвращает ссылку подписки."""
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id_db)
        if not sub:
            raise ValueError(f"Subscription {sub_id_db} not found")

        plan_key = sub.plan.value if sub.plan else "BASIC"
        plan_config = PLANS.get(plan_key, PLANS["BASIC"])

    is_trial = days > 0 or sub.plan == PlanType.FREE
    if is_trial:
        free_cfg = PLANS["FREE"]
        limit_ip = free_cfg["limit_ip"]
        traffic_gb = free_cfg["traffic_gb"]
        trial_days = days or free_cfg["days"]
        xui_months = 0
    else:
        limit_ip = plan_config.get("limit_ip", 3)
        traffic_gb = plan_config.get("traffic_gb", 0)
        trial_days = 0
        xui_months = max(months, 1)

    inbound_id = list(config.XUI_INBOUND_IDS.values())[0]

    vpn_data = await xui.add_client(
        inbound_id=inbound_id,
        first_name=first_name,
        last_name=last_name,
        telegram_id=telegram_id,
        months=xui_months,
        limit_ip=limit_ip,
        traffic_gb=traffic_gb if is_trial else 0,
        days=trial_days,
    )

    subscription_url = config.xui_sub_url(vpn_data["sub_id"])

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id_db)
        if not sub:
            raise ValueError(f"Subscription {sub_id_db} not found after XUI create")

        await sub_repo.activate(
            sub=sub,
            months=months if months > 0 else 1,
            vpn_uuid=vpn_data["uuid"],
            vpn_email=vpn_data["email"],
            vpn_sub_id=vpn_data["sub_id"],
            vpn_key=subscription_url,
            inbound_id=inbound_id,
            days=trial_days,
            traffic_gb=traffic_gb if is_trial else 0,
        )

    logger.info("VPN provisioned for %s: %s", telegram_id, vpn_data["email"])
    return ProvisionResult(
        subscription_url=subscription_url,
        vpn_email=vpn_data["email"],
        vpn_sub_id=vpn_data["sub_id"],
        inbound_id=inbound_id,
    )


async def ensure_subscription_link(
    *,
    telegram_id: int,
    first_name: str,
    last_name: str,
    sub_id_db: int,
    months: int = 0,
    days: int = 0,
) -> str | None:
    """Вернуть ссылку подписки; при необходимости создать клиента в 3X-UI."""
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id_db)

    existing = resolve_subscription_url(sub, config)
    if existing:
        return existing

    result = await provision_vpn_for_subscription(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        sub_id_db=sub_id_db,
        months=months,
        days=days,
    )
    return result.subscription_url
