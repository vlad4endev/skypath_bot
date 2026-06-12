"""
Сервис массовых рассылок — сегменты, отправка, планирование.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import async_session
from database.models import (
    Broadcast,
    BroadcastStatus,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
)
from database.repository import ACTIVE_SUBSCRIPTION_STATUSES, UserRepo

logger = logging.getLogger(__name__)

BROADCAST_TARGETS: dict[str, str] = {
    "all": "Все пользователи",
    "active": "Активные подписчики",
    "leads": "Потенциальные клиенты",
    "expired": "Истёкшие подписки",
    "new_7d": "Новые за 7 дней",
    "never_paid": "Без оплат",
}

SEND_DELAY_SEC = 0.05


def is_valid_target(target: str) -> bool:
    return target in BROADCAST_TARGETS


async def count_recipients(session: AsyncSession, target: str) -> int:
    ids = await resolve_recipient_ids(session, target)
    return len(ids)


async def resolve_recipient_ids(session: AsyncSession, target: str) -> list[int]:
    if not is_valid_target(target):
        raise ValueError(f"Unknown broadcast target: {target}")

    if target == "all":
        result = await session.execute(
            select(User.telegram_id).where(User.is_banned == False)  # noqa: E712
        )
        return [r[0] for r in result.all()]

    if target == "active":
        result = await session.execute(
            select(distinct(Subscription.telegram_id))
            .join(User, User.telegram_id == Subscription.telegram_id)
            .where(
                and_(
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    User.is_banned == False,  # noqa: E712
                )
            )
        )
        return [r[0] for r in result.all()]

    if target == "leads":
        user_repo = UserRepo(session)
        banned = await session.execute(
            select(User.telegram_id).where(User.is_banned == True)  # noqa: E712
        )
        banned_ids = {r[0] for r in banned.all()}
        return [tid for tid in await user_repo.get_marketing_lead_ids() if tid not in banned_ids]

    if target == "expired":
        active_ids = await session.execute(
            select(distinct(Subscription.telegram_id)).where(
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES)
            )
        )
        active_set = {r[0] for r in active_ids.all()}
        result = await session.execute(
            select(distinct(Subscription.telegram_id))
            .join(User, User.telegram_id == Subscription.telegram_id)
            .where(
                and_(
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    User.is_banned == False,  # noqa: E712
                )
            )
        )
        return [r[0] for r in result.all() if r[0] not in active_set]

    if target == "new_7d":
        since = datetime.utcnow() - timedelta(days=7)
        result = await session.execute(
            select(User.telegram_id).where(
                and_(User.created_at >= since, User.is_banned == False)  # noqa: E712
            )
        )
        return [r[0] for r in result.all()]

    if target == "never_paid":
        paid_subq = (
            select(Payment.user_id)
            .where(Payment.status == PaymentStatus.SUCCEEDED)
            .distinct()
        )
        result = await session.execute(
            select(User.telegram_id).where(
                and_(
                    User.is_banned == False,  # noqa: E712
                    User.id.not_in(paid_subq),
                )
            )
        )
        return [r[0] for r in result.all()]

    return []


async def execute_broadcast(broadcast_id: int, bot: Bot) -> Broadcast | None:
    """Отправить рассылку. Идемпотентно — повторный вызов для sent/cancelled игнорируется."""
    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if not broadcast:
            logger.warning("Broadcast %s not found", broadcast_id)
            return None

        if broadcast.status in (BroadcastStatus.SENT, BroadcastStatus.CANCELLED):
            return broadcast

        if broadcast.status == BroadcastStatus.SENDING and broadcast.completed_at:
            return broadcast

        if broadcast.status == BroadcastStatus.SCHEDULED:
            broadcast.status = BroadcastStatus.SENDING
            broadcast.started_at = datetime.utcnow()
            await session.commit()
        elif broadcast.status == BroadcastStatus.SENDING and not broadcast.started_at:
            broadcast.started_at = datetime.utcnow()
            await session.commit()

        await session.refresh(broadcast)

        target = broadcast.target
        text = broadcast.text

    try:
        async with async_session() as session:
            recipient_ids = await resolve_recipient_ids(session, target)
    except Exception as e:
        logger.exception("Broadcast %s: failed to resolve recipients", broadcast_id)
        await _mark_failed(broadcast_id, str(e))
        return None

    sent = 0
    failed = 0
    for telegram_id in recipient_ids:
        try:
            await bot.send_message(telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug("Broadcast %s: send failed for %s: %s", broadcast_id, telegram_id, e)
        await asyncio.sleep(SEND_DELAY_SEC)

    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if not broadcast:
            return None

        broadcast.sent_count = sent
        broadcast.failed_count = failed
        broadcast.sent = True
        broadcast.completed_at = datetime.utcnow()
        if sent == 0 and failed > 0:
            broadcast.status = BroadcastStatus.FAILED
            broadcast.error_message = "Ни одно сообщение не доставлено"
        else:
            broadcast.status = BroadcastStatus.SENT
        await session.commit()
        await session.refresh(broadcast)

    logger.info(
        "Broadcast %s done: sent=%s failed=%s target=%s",
        broadcast_id, sent, failed, target,
    )
    return broadcast


async def _mark_failed(broadcast_id: int, message: str) -> None:
    async with async_session() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if not broadcast:
            return
        broadcast.status = BroadcastStatus.FAILED
        broadcast.error_message = message[:500]
        broadcast.completed_at = datetime.utcnow()
        broadcast.sent = True
        await session.commit()


async def process_due_broadcasts(bot: Bot) -> int:
    """Обработать все запланированные рассылки, время которых наступило."""
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(Broadcast.id).where(
                and_(
                    Broadcast.status == BroadcastStatus.SCHEDULED,
                    Broadcast.send_at <= now,
                )
            ).order_by(Broadcast.send_at.asc())
        )
        ids = [r[0] for r in result.all()]

    for broadcast_id in ids:
        await execute_broadcast(broadcast_id, bot)

    return len(ids)
