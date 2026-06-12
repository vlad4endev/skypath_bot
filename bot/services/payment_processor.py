"""
Единая логика заказов и приёма оплат из Platega.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from aiogram import Bot

from bot.config import Config, PLANS
from bot.keyboards.webapp import is_miniapp_available, miniapp_payment_return_url
from bot.services.payment import (
    PlategaClient,
    PlategaWebhookEvent,
    parse_platega_webhook,
)
from database.engine import async_session
from database.models import PlanType, PaymentStatus
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo, PromoRepo

logger = logging.getLogger(__name__)
config = Config()
platega = PlategaClient(config)


@dataclass
class CreateOrderResult:
    order_id: str
    payment_id: str
    payment_url: str
    subscription_id: int
    payment_db_id: int
    amount: float
    plan: str
    months: int


async def create_paid_order(
    *,
    telegram_id: int,
    plan_key: str,
    months: int,
    price: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    promo_code: str | None = None,
    for_miniapp: bool = False,
) -> CreateOrderResult:
    """Создать подписку (ожидает оплаты) и платёж в БД + Platega."""
    plan = PLANS.get(plan_key)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_key}")

    description = f"{config.BRAND_NAME} — {plan['name']} на {months} мес."

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        pay_repo = PaymentRepo(session)
        promo_repo = PromoRepo(session)

        db_user, _ = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        if promo_code:
            promo = await promo_repo.get_by_code(promo_code)
            if promo and promo.is_valid:
                await promo_repo.use(promo)

        sub = await sub_repo.create_pending(
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan=PlanType[plan_key],
            limit_ip=plan["limit_ip"],
            promo_code=promo_code,
        )

        order_id = str(uuid.uuid4())
        return_url = None
        failed_url = None
        if for_miniapp and is_miniapp_available():
            return_url = miniapp_payment_return_url(order_id, "success")
            failed_url = miniapp_payment_return_url(order_id, "failed")

        payment_data = await platega.create_payment(
            amount=price,
            description=description,
            metadata={
                "telegram_id": str(telegram_id),
                "plan": plan_key,
                "months": str(months),
                "subscription_id": str(sub.id),
                "promo_code": promo_code or "",
            },
            order_id=order_id,
            return_url=return_url,
            failed_url=failed_url,
        )

        payment = await pay_repo.create(
            user_id=db_user.id,
            telegram_id=telegram_id,
            subscription_id=sub.id,
            amount=price,
            plan=plan_key,
            months=months,
            provider_transaction_id=payment_data["payment_id"],
            order_id=payment_data["order_id"],
            payment_url=payment_data["payment_url"],
            description=description,
            promo_code=promo_code,
        )

    logger.info(
        "Order created payment_id=%s order=%s user=%s plan=%s %s mo %s RUB",
        payment.id,
        payment.order_id,
        telegram_id,
        plan_key,
        months,
        price,
    )
    return CreateOrderResult(
        order_id=payment_data["order_id"],
        payment_id=payment_data["payment_id"],
        payment_url=payment_data["payment_url"],
        subscription_id=sub.id,
        payment_db_id=payment.id,
        amount=float(price),
        plan=plan_key,
        months=months,
    )


async def find_payment_for_event(event: PlategaWebhookEvent):
    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        if event.order_id:
            payment = await pay_repo.get_by_order_id(event.order_id)
            if payment:
                return payment
        if event.transaction_id:
            payment = await pay_repo.get_by_payment_ref(event.transaction_id)
            if payment:
                return payment
    return None


async def record_provider_event(payment_id: int, event: PlategaWebhookEvent) -> None:
    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        payment = await pay_repo.get_by_id(payment_id)
        if payment:
            await pay_repo.record_webhook(
                payment,
                provider_status=event.provider_status,
                paid_amount=event.amount or None,
                transaction_id=event.transaction_id,
            )


async def process_webhook(body: dict[str, Any], bot: Bot) -> dict[str, Any]:
    """Обработать webhook Platega: обновить платёж и выдать VPN при оплате."""
    event = parse_platega_webhook(body)
    if not event:
        logger.info("Platega webhook: unparseable body")
        return {"ok": True, "skipped": "unparseable"}

    if event.transaction_id and not event.subscription_id:
        tx_data = await platega.fetch_transaction(event.transaction_id)
        if tx_data:
            enriched = parse_platega_webhook(tx_data)
            if enriched:
                event = enriched

    logger.info(
        "Platega webhook type=%s order=%s tx=%s status=%s amount=%s",
        event.event_type,
        event.order_id,
        event.transaction_id,
        event.provider_status,
        event.amount,
    )

    payment = await find_payment_for_event(event)
    if not payment:
        logger.warning("Platega webhook: payment not found order=%s tx=%s", event.order_id, event.transaction_id)
        return {"ok": True, "skipped": "payment_not_found"}

    await record_provider_event(payment.id, event)

    if event.event_type == "cancelled":
        async with async_session() as session:
            pay_repo = PaymentRepo(session)
            p = await pay_repo.get_by_id(payment.id)
            if p and p.status == PaymentStatus.PENDING:
                await pay_repo.mark_cancelled(p, provider_status=event.provider_status)
        return {"ok": True, "status": "cancelled"}

    if event.event_type != "paid":
        return {"ok": True, "skipped": event.event_type}

    async with async_session() as session:
        user_repo = UserRepo(session)
        user = await user_repo.get_by_id(payment.user_id)
        telegram_id = (
            event.telegram_id
            or payment.telegram_id
            or (user.telegram_id if user else None)
        )

    if not telegram_id:
        logger.warning("Platega webhook: telegram_id missing for payment %s", payment.id)
        return {"ok": True, "skipped": "no_telegram_id"}

    fulfilled = await fulfill_paid_payment(
        bot=bot,
        payment_ref=payment.order_id or event.order_id or event.transaction_id or "",
        telegram_id=int(telegram_id),
        provider_event=event,
    )
    return {"ok": True, "fulfilled": fulfilled}


async def process_manual_check(bot: Bot, payment_ref: str, telegram_id: int) -> str:
    """Проверка «Я оплатил» — статус: succeeded | pending | cancelled | not_found."""
    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        payment = await pay_repo.get_by_payment_ref(payment_ref)

    if not payment:
        return "not_found"

    if payment.status == PaymentStatus.SUCCEEDED:
        if not payment.fulfilled_at:
            await fulfill_paid_payment(
                bot=bot,
                payment_ref=payment.order_id or payment_ref,
                telegram_id=telegram_id,
            )
        return "succeeded"

    if payment.status == PaymentStatus.CANCELLED:
        return "cancelled"

    tx_id = payment.yookassa_id or payment_ref
    status = await platega.check_payment_status(tx_id)

    if status == "succeeded":
        tx_data = await platega.fetch_transaction(tx_id)
        event: PlategaWebhookEvent | None = None
        if tx_data:
            event = parse_platega_webhook(tx_data)
        if event:
            await record_provider_event(payment.id, event)
        await fulfill_paid_payment(
            bot=bot,
            payment_ref=payment.order_id or payment_ref,
            telegram_id=telegram_id,
            provider_event=event,
        )
        return "succeeded"

    if status == "cancelled":
        async with async_session() as session:
            pay_repo = PaymentRepo(session)
            p = await pay_repo.get_by_id(payment.id)
            if p:
                await pay_repo.mark_cancelled(p, provider_status=status)
        return "cancelled"

    return "pending"


async def fulfill_paid_payment(
    bot: Bot,
    payment_ref: str,
    telegram_id: int,
    provider_event: PlategaWebhookEvent | None = None,
) -> bool:
    """Подтвердить оплату в БД и выдать VPN (идемпотентно)."""
    from bot.handlers.payment_handler import _process_successful_payment

    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        payment = await pay_repo.claim_success(
            payment_ref,
            provider_status=provider_event.provider_status if provider_event else None,
            paid_amount=provider_event.amount if provider_event and provider_event.amount else None,
            transaction_id=provider_event.transaction_id if provider_event else None,
        )
        if not payment:
            existing = await pay_repo.get_by_payment_ref(payment_ref)
            if existing and existing.status == PaymentStatus.SUCCEEDED and not existing.fulfilled_at:
                payment = existing
            else:
                logger.info("Payment %s already processed or not found", payment_ref)
                return False

        if provider_event and payment.amount and provider_event.amount:
            if int(provider_event.amount) != int(payment.amount):
                logger.warning(
                    "Amount mismatch payment=%s expected=%s got=%s order=%s",
                    payment.id,
                    payment.amount,
                    provider_event.amount,
                    payment.order_id,
                )

        plan = provider_event.plan if provider_event and provider_event.plan else payment.plan
        months = provider_event.months if provider_event else payment.months
        amount = provider_event.amount if provider_event and provider_event.amount else payment.amount
        subscription_id = (
            provider_event.subscription_id if provider_event and provider_event.subscription_id
            else payment.subscription_id
        )

    await _process_successful_payment(
        bot=bot,
        payment_id=payment.order_id or payment_ref,
        telegram_id=telegram_id,
        plan=plan or "BASIC",
        months=months or 1,
        amount=amount or 0,
        subscription_id=subscription_id or 0,
        payment_db_id=payment.id,
    )
    return True
