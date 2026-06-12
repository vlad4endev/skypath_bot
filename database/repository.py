"""
Репозиторий — все операции с БД (PostgreSQL вместо NocoDB)
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Subscription, Payment, PromoCode, PromoCodeUsage, Promotion, SubscriptionStatus, PaymentStatus, PlanType

ACTIVE_SUBSCRIPTION_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL)


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, telegram_id: int, **kwargs) -> tuple[User, bool]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            # Обновляем last_seen и данные
            for k, v in kwargs.items():
                if v is not None:
                    setattr(user, k, v)
            user.last_seen = datetime.utcnow()
            await self.session.commit()
            return user, False

        user = User(telegram_id=telegram_id, **kwargs)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_referrer_if_empty(self, user: User, referrer_telegram_id: int) -> bool:
        """Записать referrer_id один раз (self-referral и повтор не перезаписывают)."""
        if user.referrer_id or user.telegram_id == referrer_telegram_id:
            return False
        referrer = await self.get_by_telegram_id(referrer_telegram_id)
        if not referrer:
            return False
        user.referrer_id = referrer_telegram_id
        await self.session.commit()
        return True

    async def count_referrals(self, referrer_telegram_id: int) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.referrer_id == referrer_telegram_id)
        )
        return result.scalar() or 0

    async def get_all_ids(self) -> list[int]:
        result = await self.session.execute(select(User.telegram_id))
        return [r[0] for r in result.all()]

    async def get_marketing_lead_ids(self) -> list[int]:
        result = await self.session.execute(
            select(User.telegram_id).where(User.is_marketing_lead == True)  # noqa: E712
        )
        return [r[0] for r in result.all()]

    async def set_marketing_lead(self, user_id: int, *, value: bool = True) -> None:
        user = await self.get_by_id(user_id)
        if user and user.is_marketing_lead != value:
            user.is_marketing_lead = value
            await self.session.commit()


class SubscriptionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self, telegram_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.telegram_id == telegram_id,
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                )
            ).order_by(Subscription.expires_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_all_for_user(self, telegram_id: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.telegram_id == telegram_id
            ).order_by(Subscription.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, sub_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        return result.scalar_one_or_none()

    async def get_pending(self, telegram_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.telegram_id == telegram_id,
                    Subscription.status == SubscriptionStatus.PENDING,
                )
            ).order_by(Subscription.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_pending(
        self,
        telegram_id: int,
        user_id: int,
        plan: PlanType,
        limit_ip: int = 3,
        promo_code: str | None = None,
    ) -> Subscription:
        sub = Subscription(
            telegram_id=telegram_id,
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.PENDING,
            limit_ip=limit_ip,
            promo_code=promo_code,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def activate(
        self, sub: Subscription, months: int,
        vpn_uuid: str, vpn_email: str,
        vpn_sub_id: str, vpn_key: str,
        inbound_id: int,
        days: int = 0,
        traffic_gb: int = 0,
    ) -> Subscription:
        sub.started_at = datetime.utcnow()
        if days > 0:
            sub.status = SubscriptionStatus.FREE_TRIAL
            sub.expires_at = datetime.utcnow() + timedelta(days=days)
            sub.months_paid = 0
            sub.traffic_gb = traffic_gb
        else:
            sub.status = SubscriptionStatus.ACTIVE
            sub.expires_at = datetime.utcnow() + timedelta(days=30 * months)
            sub.months_paid = months
        sub.vpn_uuid = vpn_uuid
        sub.vpn_email = vpn_email
        sub.vpn_sub_id = vpn_sub_id
        sub.vpn_key = vpn_key
        sub.inbound_id = inbound_id
        sub.vpn_disabled_at = None
        sub.grace_reminders_sent = 0
        sub.vpn_purged_at = None
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        user_repo = UserRepo(self.session)
        await user_repo.set_marketing_lead(sub.user_id, value=False)
        return sub

    async def extend_days(self, sub: Subscription, days: int) -> Subscription:
        base = max(sub.expires_at, datetime.utcnow()) if sub.expires_at else datetime.utcnow()
        sub.expires_at = base + timedelta(days=days)
        sub.status = SubscriptionStatus.ACTIVE
        sub.notified_1day = False
        sub.notified_expired = False
        sub.grace_reminders_sent = 0
        sub.vpn_purged_at = None
        sub.vpn_disabled_at = None
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        user_repo = UserRepo(self.session)
        await user_repo.set_marketing_lead(sub.user_id, value=False)
        return sub

    async def extend(
        self,
        sub: Subscription,
        months: int,
        *,
        plan: PlanType | None = None,
        limit_ip: int | None = None,
    ) -> Subscription:
        base = max(sub.expires_at, datetime.utcnow()) if sub.expires_at else datetime.utcnow()
        sub.expires_at = base + timedelta(days=30 * months)
        sub.months_paid = (sub.months_paid or 0) + months
        sub.status = SubscriptionStatus.ACTIVE
        if plan is not None:
            sub.plan = plan
        if limit_ip is not None:
            sub.limit_ip = limit_ip
        sub.notified_1day = False
        sub.notified_expired = False
        sub.grace_reminders_sent = 0
        sub.vpn_purged_at = None
        sub.vpn_disabled_at = None
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        user_repo = UserRepo(self.session)
        await user_repo.set_marketing_lead(sub.user_id, value=False)
        return sub

    async def expire(self, sub: Subscription) -> Subscription:
        sub.status = SubscriptionStatus.EXPIRED
        sub.grace_reminders_sent = 0
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        return sub

    async def mark_vpn_disabled(self, sub: Subscription) -> Subscription:
        sub.vpn_disabled_at = datetime.utcnow()
        sub.grace_reminders_sent = 0
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def increment_grace_reminder(self, sub: Subscription) -> Subscription:
        sub.grace_reminders_sent = (sub.grace_reminders_sent or 0) + 1
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def mark_vpn_purged(self, sub: Subscription) -> Subscription:
        sub.vpn_purged_at = datetime.utcnow()
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def clear_vpn_client(self, sub: Subscription) -> Subscription:
        sub.vpn_uuid = None
        sub.vpn_email = None
        sub.vpn_sub_id = None
        sub.vpn_key = None
        sub.inbound_id = None
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get_expired_grace_restorable(self, telegram_id: int) -> Optional[Subscription]:
        """EXPIRED подписка с ключом на сервере — можно продлить без перевыпуска."""
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.telegram_id == telegram_id,
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    Subscription.vpn_uuid.isnot(None),
                    Subscription.vpn_purged_at.is_(None),
                )
            ).order_by(Subscription.expires_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_expired_pending_grace_actions(self) -> list[Subscription]:
        """Истёкшие подписки с ключом на сервере — напоминания или удаление."""
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    Subscription.vpn_disabled_at.isnot(None),
                    Subscription.vpn_uuid.isnot(None),
                    Subscription.vpn_purged_at.is_(None),
                )
            )
        )
        return result.scalars().all()

    async def get_expiring_tomorrow(self) -> list[Subscription]:
        """Истекают завтра — для напоминания"""
        tomorrow_start = datetime.utcnow() + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(hours=24)
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    Subscription.expires_at >= tomorrow_start,
                    Subscription.expires_at < tomorrow_end,
                    Subscription.notified_1day == False,
                )
            )
        )
        return result.scalars().all()

    async def get_expiring_today(self) -> list[Subscription]:
        """Истекают сегодня — последнее напоминание"""
        today_start = datetime.utcnow()
        today_end = today_start + timedelta(hours=24)
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    Subscription.expires_at >= today_start,
                    Subscription.expires_at < today_end,
                    Subscription.notified_expired == False,
                )
            )
        )
        return result.scalars().all()

    async def get_all_active(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES)
            )
        )
        return result.scalars().all()


class PaymentRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _payment_ref_filter(self, payment_ref: str):
        return or_(
            Payment.yookassa_id == payment_ref,
            Payment.order_id == payment_ref,
        )

    async def create(
        self,
        user_id: int,
        subscription_id: int,
        amount: float,
        plan: str,
        months: int,
        provider_transaction_id: str,
        order_id: str,
        payment_url: str,
        *,
        telegram_id: int | None = None,
        description: str | None = None,
        promo_code: str | None = None,
        promotion_id: int | None = None,
        original_amount: float | None = None,
        discount_amount: float | None = None,
        provider: str = "platega",
    ) -> Payment:
        pay = Payment(
            user_id=user_id,
            telegram_id=telegram_id,
            subscription_id=subscription_id,
            amount=amount,
            plan=plan,
            months=months,
            yookassa_id=provider_transaction_id,
            order_id=order_id,
            payment_url=payment_url,
            description=description,
            promo_code=promo_code,
            promotion_id=promotion_id,
            original_amount=original_amount,
            discount_amount=discount_amount,
            provider=provider,
            status=PaymentStatus.PENDING,
        )
        self.session.add(pay)
        await self.session.commit()
        await self.session.refresh(pay)
        return pay

    async def get_by_id(self, payment_id: int) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_yookassa_id(self, yookassa_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.yookassa_id == yookassa_id)
        )
        return result.scalar_one_or_none()

    async def get_by_payment_ref(self, payment_ref: str) -> Optional[Payment]:
        """Найти платёж по ID провайдера или order_id."""
        result = await self.session.execute(
            select(Payment).where(self._payment_ref_filter(payment_ref))
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 20) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_user(self, telegram_id: int, limit: int = 10) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.telegram_id == telegram_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def record_webhook(
        self,
        payment: Payment,
        *,
        provider_status: str,
        paid_amount: float | None = None,
        transaction_id: str | None = None,
    ) -> Payment:
        payment.webhook_received_at = datetime.utcnow()
        payment.provider_status = provider_status
        if paid_amount is not None and paid_amount > 0:
            payment.paid_amount = paid_amount
        if transaction_id and not payment.yookassa_id:
            payment.yookassa_id = transaction_id
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def mark_paid(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = datetime.utcnow()
        await self.session.commit()
        return payment

    async def mark_cancelled(self, payment: Payment, provider_status: str = "") -> Payment:
        payment.status = PaymentStatus.CANCELLED
        if provider_status:
            payment.provider_status = provider_status
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def mark_fulfilled(self, payment: Payment) -> Payment:
        payment.fulfilled_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def count_succeeded_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Payment.id)).where(
                and_(Payment.user_id == user_id, Payment.status == PaymentStatus.SUCCEEDED)
            )
        )
        return result.scalar() or 0

    async def claim_payment(self, payment_ref: str) -> Optional[Payment]:
        """Идемпотентно пометить платёж оплаченным (только из PENDING)."""
        return await self.claim_success(payment_ref)

    async def claim_success(
        self,
        payment_ref: str,
        *,
        provider_status: str | None = None,
        paid_amount: float | None = None,
        transaction_id: str | None = None,
    ) -> Optional[Payment]:
        """Идемпотентно подтвердить оплату и сохранить данные провайдера."""
        now = datetime.utcnow()
        values: dict = {
            "status": PaymentStatus.SUCCEEDED,
            "paid_at": now,
            "webhook_received_at": now,
        }
        if provider_status:
            values["provider_status"] = provider_status
        if paid_amount is not None and paid_amount > 0:
            values["paid_amount"] = paid_amount

        result = await self.session.execute(
            update(Payment)
            .where(
                and_(
                    self._payment_ref_filter(payment_ref),
                    Payment.status == PaymentStatus.PENDING,
                )
            )
            .values(**values)
            .returning(Payment)
        )
        payment = result.scalar_one_or_none()
        if payment:
            if transaction_id and not payment.yookassa_id:
                payment.yookassa_id = transaction_id
            await self.session.commit()
            await self.session.refresh(payment)
            return payment

        return None


class PromoRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> Optional[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code.upper())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, promo_id: int) -> Optional[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.id == promo_id)
        )
        return result.scalar_one_or_none()

    async def user_has_used(self, promo_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            select(PromoCodeUsage.id).where(
                PromoCodeUsage.promo_code_id == promo_id,
                PromoCodeUsage.user_id == user_id,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def payment_has_usage(self, payment_id: int) -> bool:
        result = await self.session.execute(
            select(PromoCodeUsage.id).where(
                PromoCodeUsage.payment_id == payment_id,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def create_personal(
        self,
        *,
        code: str,
        telegram_id: int,
        discount_pct: int = 0,
        discount_amount: int = 0,
        plans: list | None = None,
        months: list | None = None,
        min_amount: int = 0,
        expires_at: datetime | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> PromoCode:
        promo = PromoCode(
            code=code.upper().strip(),
            name=name,
            description=description,
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            plans=plans,
            months=months,
            min_amount=min_amount,
            max_uses=1,
            one_per_user=True,
            assigned_telegram_id=telegram_id,
            is_active=True,
            expires_at=expires_at,
        )
        self.session.add(promo)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def use(
        self,
        promo: PromoCode,
        *,
        user_id: int,
        telegram_id: int,
        payment_id: int | None = None,
    ) -> PromoCode:
        promo.uses_count += 1
        usage = PromoCodeUsage(
            promo_code_id=promo.id,
            user_id=user_id,
            telegram_id=telegram_id,
            payment_id=payment_id,
        )
        self.session.add(usage)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo


class PromotionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> list[Promotion]:
        result = await self.session.execute(
            select(Promotion)
            .where(Promotion.is_active == True)  # noqa: E712
            .order_by(Promotion.priority.desc(), Promotion.created_at.desc())
        )
        promos = list(result.scalars().all())
        return [p for p in promos if p.is_valid]

    async def list_all(self) -> list[Promotion]:
        result = await self.session.execute(
            select(Promotion).order_by(Promotion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, promotion_id: int) -> Optional[Promotion]:
        result = await self.session.execute(
            select(Promotion).where(Promotion.id == promotion_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **fields) -> Promotion:
        promotion = Promotion(**fields)
        self.session.add(promotion)
        await self.session.commit()
        await self.session.refresh(promotion)
        return promotion

    async def update(self, promotion_id: int, **fields) -> Optional[Promotion]:
        promotion = await self.get_by_id(promotion_id)
        if not promotion:
            return None
        for key, val in fields.items():
            if hasattr(promotion, key):
                setattr(promotion, key, val)
        await self.session.commit()
        await self.session.refresh(promotion)
        return promotion

    async def delete(self, promotion_id: int) -> bool:
        from sqlalchemy import delete as sql_delete
        result = await self.session.execute(
            sql_delete(Promotion).where(Promotion.id == promotion_id)
        )
        await self.session.commit()
        return result.rowcount > 0
