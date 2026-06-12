#!/usr/bin/env python3
"""
Импорт плоского CSV из NocoDB SkyPath (таблицы «Пользователи», «SUPER VPN» и т.д.).

Колонки экспорта:
  Пользователь, telegram_id, Действия подписки, Подписка, Сумма оплаты,
  Промокод, KEY, id_3x_ui, order_pay, EMAL, SUB, [Кол устр,] ТАРИФ, Логин, пароль

Дедупликация:
  - внутри CSV и между несколькими файлами по (telegram_id, vpn_uuid) или (telegram_id, plan)
  - в БД: пользователь по telegram_id, подписка по vpn_uuid, платёж по order_id

Пример:
  python scripts/migrate_skypath_csv.py --dry-run \\
    data/nocodb_export/users_skypath.csv \\
    "/Users/vl4endev/Downloads/SUPER VPN_exported_1.csv"

  export DB_URL=postgresql+asyncpg://...
  python scripts/migrate_skypath_csv.py data/nocodb_export/users_skypath.csv super.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.engine import async_session, init_db
from database.models import (
    User,
    Subscription,
    Payment,
    PlanType,
    SubscriptionStatus,
    PaymentStatus,
)
from sqlalchemy import select
from bot.config import Config, PLANS

logger = logging.getLogger(__name__)
config = Config()

VLESS_UUID_RE = re.compile(r"vless://([0-9a-fA-F-]{36})@")

STATUS_MAP = {
    "активна": SubscriptionStatus.ACTIVE,
    "не активна": SubscriptionStatus.EXPIRED,
    "ожидает оплату": SubscriptionStatus.PENDING,
    "пробная": SubscriptionStatus.FREE_TRIAL,
    "пробный период": SubscriptionStatus.FREE_TRIAL,
}

PLAN_MAP = {
    "free": PlanType.FREE,
    "basic": PlanType.BASIC,
    "multi": PlanType.MULTI,
    "super": PlanType.SUPER,
}

STATUS_RANK = {
    SubscriptionStatus.ACTIVE: 4,
    SubscriptionStatus.FREE_TRIAL: 3,
    SubscriptionStatus.PENDING: 2,
    SubscriptionStatus.EXPIRED: 1,
}


@dataclass
class ParsedRow:
    telegram_id: int
    display_name: str
    first_name: str | None
    last_name: str | None
    plan: PlanType
    status: SubscriptionStatus
    expires_at: datetime | None
    vpn_key: str | None
    vpn_uuid: str | None
    vpn_email: str | None
    vpn_sub_id: str | None
    promo: str | None
    amount: float
    order_pay: str
    limit_ip: int
    source: str


def _parse_name(full: str) -> tuple[str | None, str | None]:
    full = (full or "").strip()
    if not full:
        return None, None
    parts = full.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _parse_date(value: str) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> float:
    if not value or str(value).strip() == "":
        return 0.0
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return 0.0


def _parse_int(value: str) -> int | None:
    if not value or not str(value).strip():
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _extract_uuid(key: str, id_3x: str) -> str | None:
    if id_3x and len(id_3x) >= 36:
        try:
            uuid_lib.UUID(id_3x.strip())
            return id_3x.strip()
        except ValueError:
            pass
    if key:
        m = VLESS_UUID_RE.search(key)
        if m:
            return m.group(1)
    return id_3x.strip() if id_3x else None


def _map_status(raw: str) -> SubscriptionStatus:
    key = (raw or "").strip().lower()
    return STATUS_MAP.get(key, SubscriptionStatus.EXPIRED)


def _map_plan(raw: str) -> PlanType:
    key = (raw or "MULTI").strip().lower()
    return PLAN_MAP.get(key, PlanType.MULTI)


def _limit_ip(plan: PlanType, row: dict[str, str]) -> int:
    devices = _parse_int(row.get("Кол устр", "") or "")
    if devices and devices > 0:
        return devices
    return PLANS.get(plan.value, PLANS["MULTI"]).get("limit_ip", 5)


def _order_id(order_pay: str) -> str | None:
    if not order_pay:
        return None
    raw = order_pay.strip()
    if raw.startswith("order_"):
        return raw
    return None


def _payment_url(order_pay: str) -> str | None:
    if order_pay and order_pay.strip().startswith("http"):
        return order_pay.strip()
    return None


def load_skypath_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_row(row: dict[str, str], *, source: str) -> ParsedRow | None:
    tg_raw = row.get("telegram_id") or row.get("Логин") or ""
    try:
        telegram_id = int(str(tg_raw).strip())
    except (TypeError, ValueError):
        return None

    display_name = row.get("Пользователь", "")
    first_name, last_name = _parse_name(display_name)
    plan = _map_plan(row.get("ТАРИФ", "MULTI"))
    status = _map_status(row.get("Подписка", ""))
    expires_at = _parse_date(row.get("Действия подписки", ""))
    vpn_key = (row.get("KEY") or "").strip() or None
    vpn_uuid = _extract_uuid(vpn_key or "", row.get("id_3x_ui", "") or "")

    return ParsedRow(
        telegram_id=telegram_id,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        plan=plan,
        status=status,
        expires_at=expires_at,
        vpn_key=vpn_key,
        vpn_uuid=vpn_uuid,
        vpn_email=(row.get("EMAL") or "").strip() or None,
        vpn_sub_id=(row.get("SUB") or "").strip() or None,
        promo=(row.get("Промокод") or "").strip() or None,
        amount=_parse_amount(row.get("Сумма оплаты", "")),
        order_pay=(row.get("order_pay") or "").strip(),
        limit_ip=_limit_ip(plan, row),
        source=source,
    )


def _row_score(row: ParsedRow) -> tuple:
    rank = STATUS_RANK.get(row.status, 0)
    expiry_ts = row.expires_at.timestamp() if row.expires_at else 0
    has_key = 1 if row.vpn_key else 0
    return (rank, expiry_ts, has_key)


def _dedupe_key(row: ParsedRow) -> tuple:
    """Один пользователь — одна запись на тариф (берём лучший статус / срок)."""
    return (row.telegram_id, row.plan.value)


def dedupe_rows(rows: list[ParsedRow]) -> tuple[list[ParsedRow], int]:
    """Оставляет лучшую строку на каждый VPN-ключ или тариф пользователя."""
    best: dict[tuple, ParsedRow] = {}
    skipped = 0
    for row in rows:
        key = _dedupe_key(row)
        existing = best.get(key)
        if existing is None:
            best[key] = row
            continue
        if _row_score(row) > _row_score(existing):
            best[key] = row
        skipped += 1
    return list(best.values()), skipped


def _count_status(rows: list[ParsedRow], stats: dict) -> None:
    for row in rows:
        if row.status == SubscriptionStatus.ACTIVE:
            stats["active"] += 1
        elif row.status == SubscriptionStatus.FREE_TRIAL:
            stats["trial"] += 1
        else:
            stats["expired"] += 1


async def _find_subscription(
    session,
    *,
    telegram_id: int,
    vpn_uuid: str | None,
    plan: PlanType,
) -> Subscription | None:
    if vpn_uuid:
        result = await session.execute(
            select(Subscription).where(Subscription.vpn_uuid == vpn_uuid).limit(1)
        )
        sub = result.scalar_one_or_none()
        if sub:
            return sub

    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.telegram_id == telegram_id,
            Subscription.plan == plan,
        )
        .order_by(Subscription.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _apply_subscription_fields(
    sub: Subscription,
    row: ParsedRow,
    *,
    user_id: int,
    default_inbound: int,
) -> None:
    sub.user_id = user_id
    sub.telegram_id = row.telegram_id
    sub.plan = row.plan
    sub.status = row.status
    sub.vpn_uuid = row.vpn_uuid or sub.vpn_uuid
    sub.vpn_email = row.vpn_email or sub.vpn_email
    sub.vpn_sub_id = row.vpn_sub_id or sub.vpn_sub_id
    sub.vpn_key = row.vpn_key or sub.vpn_key
    sub.inbound_id = sub.inbound_id or default_inbound
    sub.expires_at = row.expires_at or sub.expires_at
    sub.limit_ip = row.limit_ip
    sub.promo_code = row.promo or sub.promo_code
    if row.amount > 0 and row.status == SubscriptionStatus.ACTIVE:
        sub.months_paid = max(sub.months_paid, 1)
    if row.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL) and not sub.started_at:
        sub.started_at = datetime.utcnow()


async def migrate_skypath_csv(paths: list[Path], *, dry_run: bool) -> None:
    raw_rows: list[ParsedRow] = []
    stats = {
        "files": len(paths),
        "rows_raw": 0,
        "rows_skipped_no_tg": 0,
        "rows_deduped": 0,
        "rows_import": 0,
        "users_created": 0,
        "users_updated": 0,
        "subs_created": 0,
        "subs_updated": 0,
        "subs_skipped": 0,
        "payments_created": 0,
        "payments_skipped": 0,
        "active": 0,
        "expired": 0,
        "trial": 0,
    }

    for path in paths:
        for row in load_skypath_rows(path):
            stats["rows_raw"] += 1
            parsed = _parse_row(row, source=path.name)
            if not parsed:
                stats["rows_skipped_no_tg"] += 1
                continue
            raw_rows.append(parsed)

    if not raw_rows:
        raise SystemExit("Нет строк для импорта")

    import_rows, deduped = dedupe_rows(raw_rows)
    stats["rows_deduped"] = deduped
    stats["rows_import"] = len(import_rows)
    _count_status(import_rows, stats)

    if dry_run:
        seen_users: set[int] = set()
        for row in import_rows:
            if row.telegram_id in seen_users:
                stats["users_updated"] += 1
            else:
                stats["users_created"] += 1
                seen_users.add(row.telegram_id)
            stats["subs_created"] += 1
            if row.amount > 0 or _order_id(row.order_pay) or _payment_url(row.order_pay):
                stats["payments_created"] += 1
        _print_stats(paths, stats, dry_run=True)
        return

    await init_db()
    default_inbound = list(config.XUI_INBOUND_IDS.values())[0]

    async with async_session() as session:
        for row in import_rows:
            result = await session.execute(
                select(User).where(User.telegram_id == row.telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.first_name = row.first_name or user.first_name
                user.last_name = row.last_name or user.last_name
                stats["users_updated"] += 1
            else:
                user = User(
                    telegram_id=row.telegram_id,
                    first_name=row.first_name,
                    last_name=row.last_name,
                )
                session.add(user)
                await session.flush()
                stats["users_created"] += 1

            existing_sub = await _find_subscription(
                session,
                telegram_id=row.telegram_id,
                vpn_uuid=row.vpn_uuid,
                plan=row.plan,
            )

            if existing_sub:
                if _row_score(row) <= _row_score_from_sub(existing_sub):
                    stats["subs_skipped"] += 1
                    sub = existing_sub
                else:
                    _apply_subscription_fields(
                        existing_sub,
                        row,
                        user_id=user.id,
                        default_inbound=default_inbound,
                    )
                    stats["subs_updated"] += 1
                    sub = existing_sub
            else:
                sub = Subscription(
                    user_id=user.id,
                    telegram_id=row.telegram_id,
                    plan=row.plan,
                    status=row.status,
                    vpn_uuid=row.vpn_uuid,
                    vpn_email=row.vpn_email,
                    vpn_sub_id=row.vpn_sub_id,
                    vpn_key=row.vpn_key,
                    inbound_id=default_inbound,
                    expires_at=row.expires_at,
                    started_at=(
                        datetime.utcnow()
                        if row.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL)
                        else None
                    ),
                    months_paid=1 if row.amount > 0 and row.status == SubscriptionStatus.ACTIVE else 0,
                    limit_ip=row.limit_ip,
                    promo_code=row.promo,
                    traffic_gb=0,
                )
                session.add(sub)
                await session.flush()
                stats["subs_created"] += 1

            oid = _order_id(row.order_pay)
            if row.amount > 0 or oid or _payment_url(row.order_pay):
                if oid:
                    dup = await session.execute(
                        select(Payment).where(Payment.order_id == oid)
                    )
                    if dup.scalar_one_or_none():
                        stats["payments_skipped"] += 1
                        continue

                pay_status = (
                    PaymentStatus.SUCCEEDED
                    if row.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL)
                    else PaymentStatus.PENDING
                )
                payment = Payment(
                    user_id=user.id,
                    telegram_id=row.telegram_id,
                    subscription_id=sub.id,
                    amount=row.amount or 0,
                    paid_amount=row.amount if row.amount > 0 else None,
                    plan=row.plan.value,
                    months=1,
                    order_id=oid or f"migrated_{row.telegram_id}_{sub.id}",
                    yookassa_id=None,
                    payment_url=_payment_url(row.order_pay),
                    status=pay_status,
                    paid_at=datetime.utcnow() if pay_status == PaymentStatus.SUCCEEDED else None,
                    fulfilled_at=(
                        datetime.utcnow()
                        if row.vpn_key and pay_status == PaymentStatus.SUCCEEDED
                        else None
                    ),
                    promo_code=row.promo,
                    provider="platega",
                    description=f"Migrated from NocoDB ({row.source}) — {row.display_name}",
                )
                session.add(payment)
                stats["payments_created"] += 1

        await session.commit()

    _print_stats(paths, stats, dry_run=False)


def _row_score_from_sub(sub: Subscription) -> tuple:
    rank = STATUS_RANK.get(sub.status, 0)
    expiry_ts = sub.expires_at.timestamp() if sub.expires_at else 0
    has_key = 1 if sub.vpn_key else 0
    return (rank, expiry_ts, has_key)


def _print_stats(paths: list[Path], stats: dict, *, dry_run: bool) -> None:
    print("\n=== Миграция SkyPath CSV ===")
    for path in paths:
        print(f"  Файл: {path}")
    for k, v in stats.items():
        if k != "files":
            print(f"  {k}: {v}")
    if dry_run:
        print("\nDry-run: в БД ничего не записано.")
    else:
        print("\nИмпорт завершён.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Import SkyPath NocoDB flat users CSV")
    parser.add_argument(
        "csv_paths",
        type=Path,
        nargs="+",
        help="Один или несколько CSV (Пользователи, SUPER VPN, …)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in args.csv_paths:
        if not path.exists():
            raise SystemExit(f"Файл не найден: {path}")

    if not os.getenv("DB_URL") and not args.dry_run:
        raise SystemExit("Задай DB_URL (из .env бота) для записи в PostgreSQL")

    asyncio.run(migrate_skypath_csv(args.csv_paths, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
