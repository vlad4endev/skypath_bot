"""Admin-specific database queries with pagination and analytics."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Payment,
    PaymentStatus,
    PlanType,
    PromoCode,
    Subscription,
    SubscriptionStatus,
    User,
)
from database.repository import ACTIVE_SUBSCRIPTION_STATUSES


def _paginate(page: int, per_page: int) -> tuple[int, int]:
    page = max(1, page)
    per_page = min(max(1, per_page), 100)
    return (page - 1) * per_page, per_page


class AdminRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Analytics ──────────────────────────────────────────────

    async def get_dashboard_stats(self) -> dict[str, Any]:
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        tomorrow = now + timedelta(days=1)
        day_after = now + timedelta(days=2)

        total_users = (await self.session.execute(select(func.count(User.id)))).scalar() or 0
        new_24h = (await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= day_ago)
        )).scalar() or 0
        new_7d = (await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )).scalar() or 0
        banned = (await self.session.execute(
            select(func.count(User.id)).where(User.is_banned == True)  # noqa: E712
        )).scalar() or 0

        active_subs = (await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES)
            )
        )).scalar() or 0
        pending_subs = (await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.PENDING
            )
        )).scalar() or 0
        expired_subs = (await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.EXPIRED
            )
        )).scalar() or 0
        expiring_tomorrow = (await self.session.execute(
            select(func.count(Subscription.id)).where(
                and_(
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    Subscription.expires_at >= tomorrow,
                    Subscription.expires_at < day_after,
                )
            )
        )).scalar() or 0

        revenue_30d = (await self.session.execute(
            select(func.coalesce(func.sum(Payment.paid_amount), func.sum(Payment.amount))).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar() or 0
        payments_30d = (await self.session.execute(
            select(func.count(Payment.id)).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar() or 0
        unfulfilled = (await self.session.execute(
            select(func.count(Payment.id)).where(
                and_(
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.fulfilled_at.is_(None),
                )
            )
        )).scalar() or 0
        pending_payments = (await self.session.execute(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
        )).scalar() or 0

        active_promos = (await self.session.execute(
            select(func.count(PromoCode.id)).where(PromoCode.is_active == True)  # noqa: E712
        )).scalar() or 0

        return {
            "users": {
                "total": total_users,
                "new_24h": new_24h,
                "new_7d": new_7d,
                "banned": banned,
            },
            "subscriptions": {
                "active": active_subs,
                "pending": pending_subs,
                "expired": expired_subs,
                "expiring_tomorrow": expiring_tomorrow,
            },
            "payments": {
                "revenue_30d": float(revenue_30d),
                "count_30d": payments_30d,
                "unfulfilled": unfulfilled,
                "pending": pending_payments,
            },
            "promos": {"active": active_promos},
            "updated_at": now.isoformat(),
        }

    async def get_revenue_chart(self, days: int = 30) -> list[dict[str, Any]]:
        days = min(max(1, days), 90)
        start = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(
                func.date_trunc("day", Payment.paid_at).label("day"),
                func.count(Payment.id).label("count"),
                func.coalesce(func.sum(Payment.paid_amount), func.sum(Payment.amount)).label("revenue"),
            )
            .where(and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= start))
            .group_by("day")
            .order_by("day")
        )
        return [
            {
                "date": (row.day.date().isoformat() if row.day else ""),
                "count": row.count,
                "revenue": float(row.revenue or 0),
            }
            for row in result.all()
        ]

    async def get_users_chart(self, days: int = 30) -> list[dict[str, Any]]:
        days = min(max(1, days), 90)
        start = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(
                func.date_trunc("day", User.created_at).label("day"),
                func.count(User.id).label("count"),
            )
            .where(User.created_at >= start)
            .group_by("day")
            .order_by("day")
        )
        return [
            {"date": (row.day.date().isoformat() if row.day else ""), "count": row.count}
            for row in result.all()
        ]

    async def get_plan_distribution(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Subscription.plan, func.count(Subscription.id))
            .where(Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES))
            .group_by(Subscription.plan)
        )
        return [{"plan": row[0].value, "count": row[1]} for row in result.all()]

    # ── Users ──────────────────────────────────────────────────

    @staticmethod
    def _pick_primary_subscription(subs: list[Subscription]) -> Subscription | None:
        if not subs:
            return None
        active = [s for s in subs if s.is_active]
        if active:
            return max(active, key=lambda s: s.expires_at or datetime.min)
        with_expiry = [s for s in subs if s.expires_at]
        if with_expiry:
            return max(with_expiry, key=lambda s: s.expires_at)
        return max(subs, key=lambda s: s.created_at)

    @staticmethod
    def subscription_summary(sub: Subscription | None) -> dict[str, Any]:
        if not sub:
            return {
                "plan": None,
                "status": None,
                "expires_at": None,
                "days_left": 0,
                "is_active": False,
                "is_expired": False,
            }
        now = datetime.utcnow()
        is_expired = (
            sub.status == SubscriptionStatus.EXPIRED
            or (sub.expires_at is not None and sub.expires_at < now)
            or sub.status == SubscriptionStatus.BLOCKED
        )
        return {
            "plan": sub.plan.value,
            "status": sub.status.value,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "days_left": sub.days_left,
            "is_active": sub.is_active,
            "is_expired": is_expired,
            "subscription_id": sub.id,
        }

    async def _subscription_summaries_by_telegram(
        self, telegram_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        if not telegram_ids:
            return {}
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.telegram_id.in_(telegram_ids))
            .order_by(Subscription.created_at.desc())
        )
        subs_by_tg: dict[int, list[Subscription]] = {}
        for sub in result.scalars().all():
            subs_by_tg.setdefault(sub.telegram_id, []).append(sub)
        return {
            tg_id: self.subscription_summary(self._pick_primary_subscription(subs))
            for tg_id, subs in subs_by_tg.items()
        }

    async def list_users(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        banned: str | None = None,
    ) -> dict[str, Any]:
        offset, limit = _paginate(page, per_page)
        q = select(User)
        count_q = select(func.count(User.id))

        filters = []
        if search.strip():
            s = search.strip()
            if s.isdigit():
                filters.append(User.telegram_id == int(s))
            else:
                like = f"%{s}%"
                filters.append(or_(
                    User.username.ilike(like),
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                ))
        if banned == "true":
            filters.append(User.is_banned == True)  # noqa: E712
        elif banned == "false":
            filters.append(User.is_banned == False)  # noqa: E712

        if filters:
            q = q.where(and_(*filters))
            count_q = count_q.where(and_(*filters))

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(
            q.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        users = list(result.scalars().all())
        sub_map = await self._subscription_summaries_by_telegram(
            [u.telegram_id for u in users]
        )
        items = [
            {
                "user": user,
                "subscription": sub_map.get(
                    user.telegram_id,
                    self.subscription_summary(None),
                ),
            }
            for user in users
        ]
        return {"items": items, "total": total, "page": page, "per_page": limit}

    async def get_user_detail(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.subscriptions), selectinload(User.payments))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_stats(self, user: User) -> dict[str, Any]:
        payments = list(user.payments)
        succeeded = [p for p in payments if p.status == PaymentStatus.SUCCEEDED]
        total_paid = sum(p.paid_amount or p.amount for p in succeeded)
        referrals = (await self.session.execute(
            select(func.count(User.id)).where(User.referrer_id == user.telegram_id)
        )).scalar() or 0
        return {
            "payments_total": len(payments),
            "payments_succeeded": len(succeeded),
            "total_spent": float(total_paid),
            "referrals_count": referrals,
            "subscriptions_total": len(user.subscriptions),
        }

    async def get_user_by_telegram(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def set_user_banned(self, user_id: int, banned: bool) -> User | None:
        user = await self.get_user_detail(user_id)
        if not user:
            return None
        user.is_banned = banned
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> bool:
        user = await self.get_user_detail(user_id)
        if not user:
            return False
        await self.session.execute(
            delete(Payment).where(Payment.user_id == user_id)
        )
        await self.session.execute(
            delete(Subscription).where(Subscription.user_id == user_id)
        )
        await self.session.delete(user)
        await self.session.commit()
        return True

    # ── Subscriptions ──────────────────────────────────────────

    async def list_subscriptions(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        plan: str | None = None,
        search: str = "",
    ) -> dict[str, Any]:
        offset, limit = _paginate(page, per_page)
        q = select(Subscription)
        count_q = select(func.count(Subscription.id))
        filters = []

        if status:
            try:
                filters.append(Subscription.status == SubscriptionStatus(status))
            except ValueError:
                pass
        if plan:
            try:
                filters.append(Subscription.plan == PlanType(plan))
            except ValueError:
                pass
        if search.strip():
            s = search.strip()
            if s.isdigit():
                filters.append(Subscription.telegram_id == int(s))

        if filters:
            q = q.where(and_(*filters))
            count_q = count_q.where(and_(*filters))

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(
            q.order_by(Subscription.created_at.desc()).offset(offset).limit(limit)
        )
        return {
            "items": list(result.scalars().all()),
            "total": total,
            "page": page,
            "per_page": limit,
        }

    async def get_subscription(self, sub_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        return result.scalar_one_or_none()

    async def update_subscription(
        self,
        sub_id: int,
        *,
        status: str | None = None,
        plan: str | None = None,
        expires_at: datetime | None = None,
        extend_days: int | None = None,
        extend_months: int | None = None,
        limit_ip: int | None = None,
        vpn_key: str | None = None,
    ) -> Subscription | None:
        sub = await self.get_subscription(sub_id)
        if not sub:
            return None

        if status:
            sub.status = SubscriptionStatus(status)
        if plan:
            sub.plan = PlanType(plan)
        if limit_ip is not None:
            sub.limit_ip = limit_ip
        if vpn_key is not None:
            sub.vpn_key = vpn_key or None
        if expires_at:
            sub.expires_at = expires_at
        if extend_days:
            base = max(sub.expires_at, datetime.utcnow()) if sub.expires_at else datetime.utcnow()
            sub.expires_at = base + timedelta(days=extend_days)
            sub.status = SubscriptionStatus.ACTIVE
            sub.notified_1day = False
            sub.notified_expired = False
        if extend_months:
            base = max(sub.expires_at, datetime.utcnow()) if sub.expires_at else datetime.utcnow()
            sub.expires_at = base + timedelta(days=30 * extend_months)
            sub.months_paid += extend_months
            sub.status = SubscriptionStatus.ACTIVE
            sub.notified_1day = False
            sub.notified_expired = False

        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def create_subscription(
        self,
        *,
        user_id: int,
        telegram_id: int,
        plan: str,
        status: str = "АКТИВНА",
        days: int = 30,
        limit_ip: int = 3,
        vpn_key: str | None = None,
    ) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            telegram_id=telegram_id,
            plan=PlanType(plan),
            status=SubscriptionStatus(status),
            started_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=days),
            limit_ip=limit_ip,
            vpn_key=vpn_key,
            months_paid=max(0, days // 30),
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def delete_subscription(self, sub_id: int) -> bool:
        sub = await self.get_subscription(sub_id)
        if not sub:
            return False
        await self.session.delete(sub)
        await self.session.commit()
        return True

    # ── Payments ───────────────────────────────────────────────

    async def list_payments(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        search: str = "",
        unfulfilled_only: bool = False,
    ) -> dict[str, Any]:
        offset, limit = _paginate(page, per_page)
        q = select(Payment)
        count_q = select(func.count(Payment.id))
        filters = []

        if status:
            try:
                filters.append(Payment.status == PaymentStatus(status))
            except ValueError:
                pass
        if unfulfilled_only:
            filters.append(and_(
                Payment.status == PaymentStatus.SUCCEEDED,
                Payment.fulfilled_at.is_(None),
            ))
        if search.strip():
            s = search.strip()
            if s.isdigit():
                filters.append(or_(
                    Payment.telegram_id == int(s),
                    Payment.id == int(s),
                ))
            else:
                like = f"%{s}%"
                filters.append(or_(
                    Payment.order_id.ilike(like),
                    Payment.yookassa_id.ilike(like),
                ))

        if filters:
            q = q.where(and_(*filters))
            count_q = count_q.where(and_(*filters))

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(
            q.order_by(Payment.created_at.desc()).offset(offset).limit(limit)
        )
        return {
            "items": list(result.scalars().all()),
            "total": total,
            "page": page,
            "per_page": limit,
        }

    async def get_payment(self, payment_id: int) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def update_payment_status(
        self, payment_id: int, status: str
    ) -> Payment | None:
        payment = await self.get_payment(payment_id)
        if not payment:
            return None
        payment.status = PaymentStatus(status)
        if status == PaymentStatus.SUCCEEDED.value and not payment.paid_at:
            payment.paid_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def mark_payment_fulfilled(self, payment_id: int) -> Payment | None:
        payment = await self.get_payment(payment_id)
        if not payment:
            return None
        payment.fulfilled_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def delete_payment(self, payment_id: int) -> bool:
        payment = await self.get_payment(payment_id)
        if not payment:
            return False
        await self.session.delete(payment)
        await self.session.commit()
        return True

    # ── Promos ─────────────────────────────────────────────────

    async def list_promos(self) -> list[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_promo(self, promo_id: int) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.id == promo_id)
        )
        return result.scalar_one_or_none()

    async def create_promo(
        self,
        *,
        code: str,
        discount_pct: int = 0,
        discount_amount: int = 0,
        max_uses: int = 1,
        expires_at: datetime | None = None,
    ) -> PromoCode:
        promo = PromoCode(
            code=code.upper().strip(),
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        self.session.add(promo)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def update_promo(self, promo_id: int, **fields) -> PromoCode | None:
        promo = await self.get_promo(promo_id)
        if not promo:
            return None
        for key, val in fields.items():
            if val is not None and hasattr(promo, key):
                setattr(promo, key, val)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def delete_promo(self, promo_id: int) -> bool:
        result = await self.session.execute(
            delete(PromoCode).where(PromoCode.id == promo_id)
        )
        await self.session.commit()
        return result.rowcount > 0
