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
from bot.keyboards.webapp import (
    cabinet_payment_return_url,
    is_cabinet_available,
    is_miniapp_available,
    miniapp_payment_return_url,
)
from bot.services.payment import (
    PlategaClient,
    PlategaWebhookEvent,
    parse_platega_webhook,
)
from bot.services.discount_service import calculate_discount, DiscountResult
from database.engine import async_session
from database.models import PlanType, PaymentStatus, SubscriptionStatus
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
    original_amount: float
    discount_total: float
    plan: str
    months: int
    promo_code: str | None = None
    promotion_id: int | None = None
    discount_label: str | None = None


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
    for_cabinet: bool = False,
) -> CreateOrderResult:
    """Создать подписку (ожидает оплаты) и платёж в БД + Platega."""
    plan = PLANS.get(plan_key)
    if not plan:
        raise ValueError("unknown_plan")

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        pay_repo = PaymentRepo(session)

        db_user, is_new_user = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        from bot.i18n import get_api_locale

        locale = get_api_locale(db_user)
        discount: DiscountResult = await calculate_discount(
            session,
            telegram_id=telegram_id,
            user_id=db_user.id,
            plan_key=plan_key,
            months=months,
            promo_code=promo_code,
            is_new_user=is_new_user,
            locale=locale,
        )
        if not discount.ok:
            raise ValueError(discount.error or "invalid_discount")
        if discount.final_price != price:
            logger.warning(
                "Price corrected user=%s plan=%s %s mo client=%s server=%s",
                telegram_id,
                plan_key,
                months,
                price,
                discount.final_price,
            )
        price = discount.final_price
        promo_code = discount.promo_code
        promotion_id = discount.promotion_id

    description = f"{config.BRAND_NAME} — {plan['name']} на {months} мес."
    if discount.discount_label:
        description += f" ({discount.discount_label})"

    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        pay_repo = PaymentRepo(session)

        db_user = await user_repo.get_by_telegram_id(telegram_id)
        if not db_user:
            raise ValueError("user_not_found")

        active = await sub_repo.get_active(telegram_id)
        if (
            active
            and active.plan != PlanType.FREE
            and active.vpn_sub_id
            and active.status == SubscriptionStatus.ACTIVE
        ):
            sub = active
            pending = await sub_repo.get_pending(telegram_id)
            if pending and pending.id != active.id:
                await sub_repo.expire(pending)
        else:
            grace_sub = await sub_repo.get_expired_grace_restorable(telegram_id)
            if grace_sub and plan_key != "FREE":
                sub = grace_sub
                sub.plan = PlanType[plan_key]
                sub.limit_ip = plan["limit_ip"]
                if promo_code:
                    sub.promo_code = promo_code
                if discount.discount_total and discount.base_price:
                    sub.discount_pct = int(round(discount.discount_total / discount.base_price * 100))
                await session.commit()
                pending = await sub_repo.get_pending(telegram_id)
                if pending and pending.id != grace_sub.id:
                    await sub_repo.expire(pending)
            else:
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
        if for_cabinet and is_cabinet_available():
            return_url = cabinet_payment_return_url(order_id, "success")
            failed_url = cabinet_payment_return_url(order_id, "failed")
        elif for_miniapp and is_miniapp_available():
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
            promotion_id=promotion_id,
            original_amount=float(discount.base_price),
            discount_amount=float(discount.discount_total),
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
        original_amount=float(discount.base_price),
        discount_total=float(discount.discount_total),
        plan=plan_key,
        months=months,
        promo_code=promo_code,
        promotion_id=promotion_id,
        discount_label=discount.discount_label,
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

        if payment.promo_code:
            promo_repo = PromoRepo(session)
            if not await promo_repo.payment_has_usage(payment.id):
                promo = await promo_repo.get_by_code(payment.promo_code)
                if promo:
                    await promo_repo.use(
                        promo,
                        user_id=payment.user_id,
                        telegram_id=payment.telegram_id or telegram_id,
                        payment_id=payment.id,
                    )

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
