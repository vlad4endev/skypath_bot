"""Admin-specific database queries with pagination and analytics."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Broadcast,
    BroadcastStatus,
    Payment,
    PaymentStatus,
    PlanType,
    PromoCode,
    PromoCodeUsage,
    Promotion,
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

    async def get_client_analytics(self) -> dict[str, Any]:
        now = datetime.utcnow()
        month_ago = now - timedelta(days=30)

        total_users = (await self.session.execute(select(func.count(User.id)))).scalar() or 0

        paying_users = (await self.session.execute(
            select(func.count(func.distinct(Payment.user_id))).where(
                Payment.status == PaymentStatus.SUCCEEDED
            )
        )).scalar() or 0

        repeat_payers = (await self.session.execute(
            select(func.count())
            .select_from(
                select(Payment.user_id)
                .where(Payment.status == PaymentStatus.SUCCEEDED)
                .group_by(Payment.user_id)
                .having(func.count(Payment.id) >= 2)
                .subquery()
            )
        )).scalar() or 0

        total_revenue = (await self.session.execute(
            select(func.coalesce(func.sum(Payment.paid_amount), func.sum(Payment.amount))).where(
                Payment.status == PaymentStatus.SUCCEEDED
            )
        )).scalar() or 0

        payments_count = (await self.session.execute(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.SUCCEEDED)
        )).scalar() or 0

        revenue_30d = (await self.session.execute(
            select(func.coalesce(func.sum(Payment.paid_amount), func.sum(Payment.amount))).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar() or 0

        inactive_30d = await self.count_inactive_payers(30)
        inactive_60d = await self.count_inactive_payers(60)
        inactive_90d = await self.count_inactive_payers(90)

        active_with_payment = (await self.session.execute(
            select(func.count(func.distinct(Subscription.user_id))).where(
                and_(
                    Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    Subscription.user_id.in_(
                        select(Payment.user_id).where(Payment.status == PaymentStatus.SUCCEEDED)
                    ),
                )
            )
        )).scalar() or 0

        expired_paid = (await self.session.execute(
            select(func.count(func.distinct(Subscription.user_id))).where(
                and_(
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    Subscription.user_id.in_(
                        select(Payment.user_id).where(Payment.status == PaymentStatus.SUCCEEDED)
                    ),
                )
            )
        )).scalar() or 0

        never_paid = max(0, total_users - paying_users)
        conversion = round(paying_users / total_users * 100, 1) if total_users else 0.0
        avg_ltv = round(float(total_revenue) / paying_users, 2) if paying_users else 0.0
        avg_payment = round(float(total_revenue) / payments_count, 2) if payments_count else 0.0
        repeat_rate = round(repeat_payers / paying_users * 100, 1) if paying_users else 0.0

        return {
            "paying_users": paying_users,
            "never_paid": never_paid,
            "repeat_payers": repeat_payers,
            "repeat_rate_pct": repeat_rate,
            "conversion_pct": conversion,
            "total_revenue": float(total_revenue),
            "revenue_30d": float(revenue_30d),
            "avg_ltv": avg_ltv,
            "avg_payment": avg_payment,
            "active_paying": active_with_payment,
            "expired_paid": expired_paid,
            "inactive_payers": {
                "days_30": inactive_30d,
                "days_60": inactive_60d,
                "days_90": inactive_90d,
            },
        }

    async def _last_payment_subquery(self):
        amount_expr = func.coalesce(Payment.paid_amount, Payment.amount)
        return (
            select(
                Payment.user_id.label("user_id"),
                func.max(Payment.paid_at).label("last_paid_at"),
                func.count(Payment.id).label("payments_count"),
                func.coalesce(func.sum(amount_expr), 0).label("total_spent"),
            )
            .where(Payment.status == PaymentStatus.SUCCEEDED)
            .group_by(Payment.user_id)
            .subquery()
        )

    async def count_inactive_payers(self, days: int) -> int:
        days = min(max(1, days), 365)
        cutoff = datetime.utcnow() - timedelta(days=days)
        last_pay = await self._last_payment_subquery()
        result = await self.session.execute(
            select(func.count()).select_from(last_pay).where(last_pay.c.last_paid_at < cutoff)
        )
        return result.scalar() or 0

    async def get_inactive_payers(
        self,
        *,
        days: int = 30,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        days = min(max(1, days), 365)
        limit = min(max(1, limit), 50)
        cutoff = datetime.utcnow() - timedelta(days=days)
        last_pay = await self._last_payment_subquery()

        result = await self.session.execute(
            select(
                User,
                last_pay.c.last_paid_at,
                last_pay.c.payments_count,
                last_pay.c.total_spent,
            )
            .join(last_pay, last_pay.c.user_id == User.id)
            .where(last_pay.c.last_paid_at < cutoff)
            .order_by(last_pay.c.last_paid_at.asc())
            .limit(limit)
        )
        rows = result.all()
        sub_map = await self._subscription_summaries_by_telegram(
            [row[0].telegram_id for row in rows]
        )

        items: list[dict[str, Any]] = []
        for user, last_paid_at, payments_count, total_spent in rows:
            days_since = (datetime.utcnow() - last_paid_at).days if last_paid_at else 0
            items.append({
                "user": user,
                "subscription": sub_map.get(
                    user.telegram_id,
                    self.subscription_summary(None),
                ),
                "last_paid_at": last_paid_at.isoformat() if last_paid_at else None,
                "days_since_payment": days_since,
                "payments_count": int(payments_count or 0),
                "total_spent": float(total_spent or 0),
            })
        return items

    async def get_recent_users(self, limit: int = 8) -> list[dict[str, Any]]:
        limit = min(max(1, limit), 20)
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        users = list(result.scalars().all())
        sub_map = await self._subscription_summaries_by_telegram(
            [u.telegram_id for u in users]
        )
        return [
            {
                "user": user,
                "subscription": sub_map.get(
                    user.telegram_id,
                    self.subscription_summary(None),
                ),
            }
            for user in users
        ]

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
                    User.web_email.ilike(like),
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
            delete(PromoCodeUsage).where(PromoCodeUsage.user_id == user_id)
        )
        await self.session.execute(
            delete(Payment).where(Payment.user_id == user_id)
        )
        await self.session.execute(
            delete(Subscription).where(Subscription.user_id == user_id)
        )
        await self.session.delete(user)
        await self.session.commit()
        return True

    async def list_users_for_xui_sync(
        self,
        *,
        user_ids: list[int] | None = None,
    ) -> list[tuple[User, Subscription | None]]:
        q = select(User).options(selectinload(User.subscriptions)).order_by(User.id)
        if user_ids:
            q = q.where(User.id.in_(user_ids))
        result = await self.session.execute(q)
        users = list(result.scalars().unique().all())
        return [
            (user, self._pick_primary_subscription(list(user.subscriptions)))
            for user in users
        ]

    async def build_vpn_lookup_index(self) -> dict[str, Any]:
        """Индекс VPN-подписок в БД для сопоставления с клиентами панели."""
        result = await self.session.execute(select(Subscription))
        subs = list(result.scalars().all())
        by_email: dict[str, Subscription] = {}
        by_sub_id: dict[str, Subscription] = {}
        by_uuid: dict[str, Subscription] = {}

        for sub in subs:
            if sub.vpn_email:
                by_email[sub.vpn_email.strip()] = sub
            if sub.vpn_sub_id:
                by_sub_id[sub.vpn_sub_id.strip()] = sub
            if sub.vpn_uuid:
                by_uuid[sub.vpn_uuid.strip()] = sub

        return {
            "by_email": by_email,
            "by_sub_id": by_sub_id,
            "by_uuid": by_uuid,
        }

    async def upsert_user_from_panel_client(
        self,
        *,
        telegram_id: int,
        plan: PlanType,
        vpn_uuid: str | None,
        vpn_email: str | None,
        vpn_sub_id: str | None,
        vpn_key: str | None,
        inbound_id: int | None,
        expires_at: datetime | None,
        limit_ip: int,
        traffic_gb: int,
        status: SubscriptionStatus,
    ) -> tuple[User, Subscription, bool]:
        """Создать пользователя и подписку из клиента 3X-UI. bool = новый пользователь."""
        user = await self.get_user_by_telegram(telegram_id)
        created_user = False
        if not user:
            user = User(telegram_id=telegram_id)
            self.session.add(user)
            await self.session.flush()
            created_user = True
        else:
            user = await self.get_user_detail(user.id)
            if not user:
                raise RuntimeError(f"User {telegram_id} disappeared during import")

        sub = self._pick_primary_subscription(list(user.subscriptions))
        if sub:
            await self.apply_panel_client_to_subscription(
                sub.id,
                plan=plan,
                vpn_uuid=vpn_uuid,
                vpn_email=vpn_email,
                vpn_sub_id=vpn_sub_id,
                vpn_key=vpn_key,
                inbound_id=inbound_id,
                expires_at=expires_at,
                limit_ip=limit_ip,
                traffic_gb=traffic_gb,
                status=status,
            )
            refreshed = await self.get_subscription(sub.id)
            if not refreshed:
                raise RuntimeError(f"Subscription {sub.id} missing after panel import")
            return user, refreshed, created_user

        sub = Subscription(
            user_id=user.id,
            telegram_id=telegram_id,
            plan=plan,
            status=status,
            started_at=datetime.utcnow(),
            expires_at=expires_at,
            limit_ip=limit_ip,
            traffic_gb=traffic_gb,
            vpn_uuid=vpn_uuid,
            vpn_email=vpn_email,
            vpn_sub_id=vpn_sub_id,
            vpn_key=vpn_key,
            inbound_id=inbound_id,
            months_paid=0 if plan == PlanType.FREE else 1,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        await self.session.refresh(user)
        return user, sub, created_user

    async def apply_panel_client_to_subscription(
        self,
        sub_id: int,
        *,
        vpn_uuid: str | None,
        vpn_email: str | None,
        vpn_sub_id: str | None,
        vpn_key: str | None,
        inbound_id: int | None,
        expires_at: datetime | None,
        limit_ip: int,
        traffic_gb: int,
        status: SubscriptionStatus,
        plan: PlanType | None = None,
    ) -> Subscription | None:
        sub = await self.get_subscription(sub_id)
        if not sub:
            return None

        if plan is not None:
            sub.plan = plan
        sub.vpn_uuid = vpn_uuid
        sub.vpn_email = vpn_email
        sub.vpn_sub_id = vpn_sub_id
        sub.vpn_key = vpn_key
        if inbound_id:
            sub.inbound_id = inbound_id
        if expires_at is not None:
            sub.expires_at = expires_at
        sub.limit_ip = limit_ip
        sub.traffic_gb = traffic_gb
        sub.status = status
        if status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL):
            sub.vpn_disabled_at = None
            if not sub.started_at:
                sub.started_at = datetime.utcnow()
        sub.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

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
        disable_vpn: bool = False,
    ) -> Subscription | None:
        sub = await self.get_subscription(sub_id)
        if not sub:
            return None

        if disable_vpn:
            sub.status = SubscriptionStatus.BLOCKED
            sub.vpn_disabled_at = datetime.utcnow()

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
            sub.vpn_disabled_at = None
        if extend_months:
            base = max(sub.expires_at, datetime.utcnow()) if sub.expires_at else datetime.utcnow()
            sub.expires_at = base + timedelta(days=30 * extend_months)
            sub.months_paid += extend_months
            sub.status = SubscriptionStatus.ACTIVE
            sub.notified_1day = False
            sub.notified_expired = False
            sub.vpn_disabled_at = None

        if sub.status in ACTIVE_SUBSCRIPTION_STATUSES:
            sub.vpn_disabled_at = None
        elif sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.BLOCKED):
            if not sub.vpn_disabled_at:
                sub.vpn_disabled_at = datetime.utcnow()

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
        await self.session.execute(
            update(PromoCodeUsage)
            .where(PromoCodeUsage.payment_id == payment_id)
            .values(payment_id=None)
        )
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
        name: str | None = None,
        description: str | None = None,
        discount_pct: int = 0,
        discount_amount: int = 0,
        plans: list | None = None,
        months: list | None = None,
        min_amount: int = 0,
        max_uses: int = 1,
        one_per_user: bool = True,
        is_active: bool = True,
        expires_at: datetime | None = None,
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
            max_uses=max_uses,
            one_per_user=one_per_user,
            is_active=is_active,
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

    # ── Promotions ─────────────────────────────────────────────

    async def list_promotions(self) -> list[Promotion]:
        result = await self.session.execute(
            select(Promotion).order_by(Promotion.priority.desc(), Promotion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_promotion(self, promotion_id: int) -> Promotion | None:
        result = await self.session.execute(
            select(Promotion).where(Promotion.id == promotion_id)
        )
        return result.scalar_one_or_none()

    async def create_promotion(self, **fields) -> Promotion:
        promotion = Promotion(**fields)
        self.session.add(promotion)
        await self.session.commit()
        await self.session.refresh(promotion)
        return promotion

    async def update_promotion(self, promotion_id: int, **fields) -> Promotion | None:
        promotion = await self.get_promotion(promotion_id)
        if not promotion:
            return None
        for key, val in fields.items():
            if hasattr(promotion, key):
                setattr(promotion, key, val)
        await self.session.commit()
        await self.session.refresh(promotion)
        return promotion

    async def delete_promotion(self, promotion_id: int) -> bool:
        result = await self.session.execute(
            delete(Promotion).where(Promotion.id == promotion_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    # ── Broadcasts (рассылки) ─────────────────────────────────

    async def list_broadcasts(self, *, status: str | None = None) -> list[Broadcast]:
        query = select(Broadcast).order_by(Broadcast.created_at.desc())
        if status:
            try:
                query = query.where(Broadcast.status == BroadcastStatus(status))
            except ValueError:
                pass
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_broadcast(self, broadcast_id: int) -> Broadcast | None:
        result = await self.session.execute(
            select(Broadcast).where(Broadcast.id == broadcast_id)
        )
        return result.scalar_one_or_none()

    async def create_broadcast(self, **fields) -> Broadcast:
        broadcast = Broadcast(**fields)
        self.session.add(broadcast)
        await self.session.commit()
        await self.session.refresh(broadcast)
        return broadcast

    async def cancel_broadcast(self, broadcast_id: int) -> Broadcast | None:
        broadcast = await self.get_broadcast(broadcast_id)
        if not broadcast:
            return None
        if broadcast.status != BroadcastStatus.SCHEDULED:
            return broadcast
        broadcast.status = BroadcastStatus.CANCELLED
        broadcast.completed_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(broadcast)
        return broadcast

    async def delete_broadcast(self, broadcast_id: int) -> bool:
        broadcast = await self.get_broadcast(broadcast_id)
        if not broadcast:
            return False
        if broadcast.status in (BroadcastStatus.SENDING,):
            return False
        await self.session.delete(broadcast)
        await self.session.commit()
        return True
