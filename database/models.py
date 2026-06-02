"""
PostgreSQL модели через SQLAlchemy (вместо NocoDB)
"""
import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger, String, DateTime, Enum, Boolean,
    Integer, Float, Text, ForeignKey, Index
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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        Index("ix_sub_expires_status", "expires_at", "status"),
    )

    @property
    def is_active(self) -> bool:
        if self.status != SubscriptionStatus.ACTIVE:
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
    """История платежей"""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subscriptions.id"))

    # YooKassa
    yookassa_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    payment_url: Mapped[str | None] = mapped_column(Text)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)

    plan: Mapped[str | None] = mapped_column(String(16))
    months: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship()


class PromoCode(Base):
    """Промокоды"""
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
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


class Broadcast(Base):
    """Рассылки"""
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(32), default="all")  # all / active / expired
    send_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
