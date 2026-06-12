"""
PostgreSQL модели через SQLAlchemy (вместо NocoDB)
"""
import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger, String, DateTime, Enum, Boolean,
    Integer, Float, Text, ForeignKey, Index, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SubscriptionStatus(enum.Enum):
    PENDING = "ОЖИДАЕТ ОПЛАТУ"
    ACTIVE = "АКТИВНА"
    EXPIRED = "ИСТЕКЛА"
    BLOCKED = "ЗАБЛОКИРОВАНА"
    FREE_TRIAL = "ПРОБНЫЙ ПЕРИОД"


class PlanType(enum.Enum):
    FREE = "FREE"
    BASIC = "BASIC"
    MULTI = "MULTI"
    SUPER = "SUPER"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class User(Base):
    """Пользователи бота"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    referrer_id: Mapped[int | None] = mapped_column(BigInteger)
    is_marketing_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        return " ".join(p for p in parts if p).strip() or f"User {self.telegram_id}"


class Subscription(Base):
    """Подписки пользователей — связь с VPN ключами"""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # Тариф
    plan: Mapped[PlanType] = mapped_column(Enum(PlanType), default=PlanType.FREE)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, index=True
    )

    # VPN данные (3X-UI)
    vpn_uuid: Mapped[str | None] = mapped_column(String(36))        # UUID в 3X-UI
    vpn_email: Mapped[str | None] = mapped_column(String(128))      # email ключ в 3X-UI
    vpn_sub_id: Mapped[str | None] = mapped_column(String(64))      # subId для sub-ссылки
    vpn_key: Mapped[str | None] = mapped_column(Text)               # Готовая vless:// ссылка
    inbound_id: Mapped[int | None] = mapped_column(Integer)         # ID inbound в 3X-UI

    # Сроки
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    months_paid: Mapped[int] = mapped_column(Integer, default=0)

    # Промокод
    promo_code: Mapped[str | None] = mapped_column(String(32))
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)

    # Устройства
    limit_ip: Mapped[int] = mapped_column(Integer, default=1)
    traffic_gb: Mapped[int] = mapped_column(Integer, default=0)

    # Уведомления
    notified_1day: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    # VPN lifecycle: отключение → напоминания 7 дней → удаление из 3X-UI
    vpn_disabled_at: Mapped[datetime | None] = mapped_column(DateTime)
    grace_reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    vpn_purged_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        Index("ix_sub_expires_status", "expires_at", "status"),
    )

    @property
    def is_active(self) -> bool:
        if self.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL):
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True

    @property
    def days_left(self) -> int:
        if not self.expires_at:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)


class Payment(Base):
    """История платежей — заказ, статус провайдера, связь с подпиской."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subscriptions.id"))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    # Platega / платёжный провайдер
    provider: Mapped[str] = mapped_column(String(32), default="platega")
    order_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    yookassa_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    payment_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(256))

    # Сумма заказа и фактическая сумма из webhook
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    provider_status: Mapped[str | None] = mapped_column(String(64))

    plan: Mapped[str | None] = mapped_column(String(16))
    months: Mapped[int] = mapped_column(Integer, default=1)
    promo_code: Mapped[str | None] = mapped_column(String(32))
    promotion_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("promotions.id"))
    original_amount: Mapped[float | None] = mapped_column(Float)
    discount_amount: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship()

    __table_args__ = (
        Index("ix_payments_user_status", "user_id", "status"),
        Index("ix_payments_telegram_created", "telegram_id", "created_at"),
    )


class Promotion(Base):
    """Акции — автоматические скидки при оплате"""
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    plans: Mapped[list | None] = mapped_column(JSON)
    months: Mapped[list | None] = mapped_column(JSON)
    min_amount: Mapped[int] = mapped_column(Integer, default=0)
    new_users_only: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    stackable_with_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        now = datetime.utcnow()
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True


class PromoCode(Base):
    """Промокоды — вводятся пользователем при оплате"""
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512))
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    plans: Mapped[list | None] = mapped_column(JSON)
    months: Mapped[list | None] = mapped_column(JSON)
    min_amount: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    one_per_user: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.uses_count >= self.max_uses:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True


class PromoCodeUsage(Base):
    """История использования промокодов (лимит на пользователя)"""
    __tablename__ = "promo_code_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    payment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("payments.id"))
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_promo_usage_code_user", "promo_code_id", "user_id"),
    )


class BroadcastStatus(enum.Enum):
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Broadcast(Base):
    """Рассылки — массовые сообщения в Telegram"""
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(32), default="all", index=True)
    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(
            BroadcastStatus,
            name="broadcaststatus",
            values_callable=lambda obj: [e.value for e in obj],
            create_constraint=False,
        ),
        default=BroadcastStatus.SCHEDULED,
        index=True,
    )
    send_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    target_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_broadcasts_status_send_at", "status", "send_at"),
    )
