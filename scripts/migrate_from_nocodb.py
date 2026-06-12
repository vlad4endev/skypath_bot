#!/usr/bin/env python3
"""
Импорт пользователей, подписок и платежей из NocoDB (CSV/JSON) в PostgreSQL бота.

Подготовка:
  1. Экспортируй таблицы из NocoDB: Users, Subscriptions, Payments (CSV или JSON).
  2. Положи файлы в data/nocodb_export/ или укажи пути через аргументы.
  3. Запусти с --dry-run, проверь отчёт, затем без --dry-run.

Пример (CSV):
  python scripts/migrate_from_nocodb.py --dry-run \\
    --users data/nocodb_export/users.csv \\
    --subscriptions data/nocodb_export/subscriptions.csv \\
    --payments data/nocodb_export/payments.csv

Пример (API SkyPath NocoDB):
  export NOCODB_URL=https://wiki.skypath.fun
  export NOCODB_TOKEN=ваш_api_token
  export NOCODB_BASE_ID=713ce83b-974f-443d-813f-a78cdf43017c
  python scripts/migrate_from_nocodb.py --discover
  python scripts/migrate_from_nocodb.py --from-api --dry-run
  python scripts/migrate_from_nocodb.py --from-api

Переменные окружения:
  DB_URL — PostgreSQL (как в .env бота)
  NOCODB_URL, NOCODB_TOKEN, NOCODB_BASE_ID — для --from-api / --discover
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# корень проекта в PYTHONPATH
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

sys.path.insert(0, str(ROOT / "scripts"))
from nocodb_client import NocoDBClient, discover_schema, guess_table, normalize_row

logger = logging.getLogger(__name__)

DEFAULT_NOCODB_BASE_ID = "713ce83b-974f-443d-813f-a78cdf43017c"
DEFAULT_NOCODB_URL = "https://wiki.skypath.fun"

# --- Настройка соответствия колонок NocoDB → PostgreSQL ---
# Отредактируй под реальные имена колонок в твоём экспорте.

USER_ALIASES: dict[str, list[str]] = {
    "telegram_id": ["telegram_id", "Telegram ID", "telegramId", "tg_id", "user_id", "ID"],
    "username": ["username", "Username", "telegram_username"],
    "first_name": ["first_name", "First Name", "firstName", "name"],
    "last_name": ["last_name", "Last Name", "lastName"],
    "language_code": ["language_code", "language", "lang"],
    "referrer_id": ["referrer_id", "referrer", "referral_id"],
    "created_at": ["created_at", "CreatedAt", "Created At", "created"],
}

SUBSCRIPTION_ALIASES: dict[str, list[str]] = {
    "telegram_id": ["telegram_id", "Telegram ID", "telegramId", "tg_id", "user_telegram_id"],
    "plan": ["plan", "Plan", "tariff", "тариф"],
    "status": ["status", "Status", "статус"],
    "vpn_uuid": ["vpn_uuid", "client_uuid", "uuid", "UUID", "clientUuid"],
    "vpn_email": ["vpn_email", "email", "Email", "client_email"],
    "vpn_sub_id": ["vpn_sub_id", "sub_id", "subId", "subscription_id_panel"],
    "vpn_key": ["vpn_key", "key", "vless", "config", "link"],
    "inbound_id": ["inbound_id", "inboundId", "inbound"],
    "expires_at": ["expires_at", "expiresAt", "Expiry", "expiry", "дата_окончания"],
    "started_at": ["started_at", "startedAt", "start_date"],
    "months_paid": ["months_paid", "months", "monthsPaid"],
    "limit_ip": ["limit_ip", "limitIp", "devices", "limit"],
    "promo_code": ["promo_code", "promo", "promocode"],
}

PAYMENT_ALIASES: dict[str, list[str]] = {
    "telegram_id": ["telegram_id", "Telegram ID", "telegramId", "tg_id"],
    "order_id": ["order_id", "orderId", "Order ID"],
    "amount": ["amount", "Amount", "sum", "сумма"],
    "plan": ["plan", "Plan", "tariff"],
    "months": ["months", "Months", "period"],
    "status": ["status", "Status"],
    "paid_at": ["paid_at", "paidAt", "Paid At", "date_paid"],
    "yookassa_id": ["yookassa_id", "transaction_id", "payment_id", "platega_id"],
}

STATUS_MAP: dict[str, SubscriptionStatus] = {
    "active": SubscriptionStatus.ACTIVE,
    "активна": SubscriptionStatus.ACTIVE,
    "активен": SubscriptionStatus.ACTIVE,
    "trial": SubscriptionStatus.FREE_TRIAL,
    "пробный": SubscriptionStatus.FREE_TRIAL,
    "пробный период": SubscriptionStatus.FREE_TRIAL,
    "free_trial": SubscriptionStatus.FREE_TRIAL,
    "expired": SubscriptionStatus.EXPIRED,
    "истекла": SubscriptionStatus.EXPIRED,
    "истёк": SubscriptionStatus.EXPIRED,
    "pending": SubscriptionStatus.PENDING,
    "ожидает оплату": SubscriptionStatus.PENDING,
    "ожидает": SubscriptionStatus.PENDING,
    "blocked": SubscriptionStatus.BLOCKED,
    "заблокирована": SubscriptionStatus.BLOCKED,
}

PAYMENT_STATUS_MAP: dict[str, PaymentStatus] = {
    "succeeded": PaymentStatus.SUCCEEDED,
    "paid": PaymentStatus.SUCCEEDED,
    "success": PaymentStatus.SUCCEEDED,
    "оплачен": PaymentStatus.SUCCEEDED,
    "pending": PaymentStatus.PENDING,
    "ожидает": PaymentStatus.PENDING,
    "cancelled": PaymentStatus.CANCELLED,
    "canceled": PaymentStatus.CANCELLED,
    "отменён": PaymentStatus.CANCELLED,
    "refunded": PaymentStatus.REFUNDED,
}

PLAN_MAP: dict[str, PlanType] = {
    "free": PlanType.FREE,
    "пробный": PlanType.FREE,
    "basic": PlanType.BASIC,
    "базовый": PlanType.BASIC,
    "multi": PlanType.MULTI,
    "мульти": PlanType.MULTI,
    "super": PlanType.SUPER,
    "супер": PlanType.SUPER,
}


def _pick(row: dict[str, Any], aliases: dict[str, list[str]], field: str) -> Any:
    for key in aliases.get(field, [field]):
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(raw.replace("Z", ""), fmt.replace("Z", ""))
        except ValueError:
            continue
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "list" in data:
            return data["list"]
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected JSON shape in {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def map_user_row(row: dict[str, Any]) -> dict[str, Any] | None:
    tg = _pick(row, USER_ALIASES, "telegram_id")
    if tg is None:
        return None
    return {
        "telegram_id": _parse_int(tg),
        "username": _pick(row, USER_ALIASES, "username"),
        "first_name": _pick(row, USER_ALIASES, "first_name"),
        "last_name": _pick(row, USER_ALIASES, "last_name"),
        "language_code": _pick(row, USER_ALIASES, "language_code"),
        "referrer_id": _parse_int(_pick(row, USER_ALIASES, "referrer_id"), 0) or None,
        "created_at": _parse_dt(_pick(row, USER_ALIASES, "created_at")),
    }


def map_subscription_row(row: dict[str, Any]) -> dict[str, Any] | None:
    tg = _pick(row, SUBSCRIPTION_ALIASES, "telegram_id")
    if tg is None:
        return None
    status_raw = str(_pick(row, SUBSCRIPTION_ALIASES, "status") or "active").strip().lower()
    plan_raw = str(_pick(row, SUBSCRIPTION_ALIASES, "plan") or "basic").strip().lower()
    return {
        "telegram_id": _parse_int(tg),
        "plan": PLAN_MAP.get(plan_raw, PlanType.BASIC),
        "status": STATUS_MAP.get(status_raw, SubscriptionStatus.ACTIVE),
        "vpn_uuid": _pick(row, SUBSCRIPTION_ALIASES, "vpn_uuid"),
        "vpn_email": _pick(row, SUBSCRIPTION_ALIASES, "vpn_email"),
        "vpn_sub_id": _pick(row, SUBSCRIPTION_ALIASES, "vpn_sub_id"),
        "vpn_key": _pick(row, SUBSCRIPTION_ALIASES, "vpn_key"),
        "inbound_id": _parse_int(_pick(row, SUBSCRIPTION_ALIASES, "inbound_id"), 0) or None,
        "expires_at": _parse_dt(_pick(row, SUBSCRIPTION_ALIASES, "expires_at")),
        "started_at": _parse_dt(_pick(row, SUBSCRIPTION_ALIASES, "started_at")),
        "months_paid": _parse_int(_pick(row, SUBSCRIPTION_ALIASES, "months_paid")),
        "limit_ip": _parse_int(_pick(row, SUBSCRIPTION_ALIASES, "limit_ip"), 3),
        "promo_code": _pick(row, SUBSCRIPTION_ALIASES, "promo_code"),
    }


def map_payment_row(row: dict[str, Any]) -> dict[str, Any] | None:
    tg = _pick(row, PAYMENT_ALIASES, "telegram_id")
    order_id = _pick(row, PAYMENT_ALIASES, "order_id")
    if tg is None and not order_id:
        return None
    status_raw = str(_pick(row, PAYMENT_ALIASES, "status") or "succeeded").strip().lower()
    return {
        "telegram_id": _parse_int(tg) if tg is not None else None,
        "order_id": str(order_id) if order_id else None,
        "amount": float(_pick(row, PAYMENT_ALIASES, "amount") or 0),
        "plan": _pick(row, PAYMENT_ALIASES, "plan"),
        "months": _parse_int(_pick(row, PAYMENT_ALIASES, "months"), 1),
        "status": PAYMENT_STATUS_MAP.get(status_raw, PaymentStatus.SUCCEEDED),
        "paid_at": _parse_dt(_pick(row, PAYMENT_ALIASES, "paid_at")),
        "yookassa_id": _pick(row, PAYMENT_ALIASES, "yookassa_id"),
    }


async def migrate(
    users_path: Path | None,
    subs_path: Path | None,
    payments_path: Path | None,
    *,
    dry_run: bool,
) -> None:
    stats = {
        "users_created": 0,
        "users_updated": 0,
        "users_skipped": 0,
        "subs_created": 0,
        "subs_skipped": 0,
        "payments_created": 0,
        "payments_skipped": 0,
    }

    user_rows = load_rows(users_path) if users_path else []
    sub_rows = load_rows(subs_path) if subs_path else []
    pay_rows = load_rows(payments_path) if payments_path else []

    if not dry_run:
        await init_db()

    tg_to_user_id: dict[int, int] = {}

    async with async_session() as session:
        # --- Users ---
        for raw in user_rows:
            mapped = map_user_row(raw)
            if not mapped or not mapped["telegram_id"]:
                stats["users_skipped"] += 1
                continue
            tg = mapped["telegram_id"]
            result = await session.execute(select(User).where(User.telegram_id == tg))
            user = result.scalar_one_or_none()
            if user:
                for k, v in mapped.items():
                    if k != "telegram_id" and v is not None:
                        setattr(user, k, v)
                stats["users_updated"] += 1
                tg_to_user_id[tg] = user.id
            else:
                if dry_run:
                    stats["users_created"] += 1
                    tg_to_user_id[tg] = -tg
                else:
                    user = User(**{k: v for k, v in mapped.items() if v is not None})
                    session.add(user)
                    await session.flush()
                    tg_to_user_id[tg] = user.id
                    stats["users_created"] += 1

        if not dry_run:
            await session.commit()

        # --- Subscriptions ---
        for raw in sub_rows:
            mapped = map_subscription_row(raw)
            if not mapped:
                stats["subs_skipped"] += 1
                continue
            tg = mapped["telegram_id"]
            user_id = tg_to_user_id.get(tg)
            if not user_id:
                if dry_run:
                    user_id = -tg
                else:
                    stats["subs_skipped"] += 1
                    logger.warning("Subscription without user telegram_id=%s", tg)
                    continue

            if not dry_run:
                exists = await session.execute(
                    select(Subscription).where(
                        Subscription.telegram_id == tg,
                        Subscription.vpn_uuid == mapped.get("vpn_uuid"),
                    ).limit(1)
                )
                if mapped.get("vpn_uuid") and exists.scalar_one_or_none():
                    stats["subs_skipped"] += 1
                    continue

                sub = Subscription(user_id=user_id, **mapped)
                session.add(sub)
            stats["subs_created"] += 1

        if not dry_run:
            await session.commit()

        # --- Payments ---
        for raw in pay_rows:
            mapped = map_payment_row(raw)
            if not mapped:
                stats["payments_skipped"] += 1
                continue
            tg = mapped.get("telegram_id")
            user_id = tg_to_user_id.get(tg) if tg else None
            if not user_id and not dry_run:
                stats["payments_skipped"] += 1
                continue

            if not dry_run and mapped.get("order_id"):
                dup = await session.execute(
                    select(Payment).where(Payment.order_id == mapped["order_id"])
                )
                if dup.scalar_one_or_none():
                    stats["payments_skipped"] += 1
                    continue

            if not dry_run:
                pay = Payment(
                    user_id=user_id or 0,
                    telegram_id=tg,
                    subscription_id=None,
                    amount=mapped["amount"],
                    plan=mapped.get("plan"),
                    months=mapped["months"],
                    order_id=mapped.get("order_id"),
                    yookassa_id=mapped.get("yookassa_id"),
                    status=mapped["status"],
                    paid_at=mapped.get("paid_at"),
                    fulfilled_at=mapped.get("paid_at") if mapped["status"] == PaymentStatus.SUCCEEDED else None,
                    provider="platega",
                )
                session.add(pay)
            stats["payments_created"] += 1

        if not dry_run:
            await session.commit()

    print("\n=== Отчёт миграции ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if dry_run:
        print("\nЭто был dry-run. Данные в БД не записаны.")
    else:
        print("\nМиграция завершена.")


async def load_from_nocodb_api(
    *,
    table_users: str | None,
    table_subs: str | None,
    table_payments: str | None,
) -> tuple[list[dict], list[dict], list[dict]]:
    url = os.getenv("NOCODB_URL", DEFAULT_NOCODB_URL)
    token = os.getenv("NOCODB_TOKEN", "")
    base_id = os.getenv("NOCODB_BASE_ID", DEFAULT_NOCODB_BASE_ID)
    if not token:
        raise SystemExit("Задай NOCODB_TOKEN (NocoDB → Account → API Tokens)")

    client = NocoDBClient(url, token, base_id)
    tables = await client.list_tables()
    if not tables:
        raise SystemExit("Таблицы не найдены — проверь NOCODB_BASE_ID и token")

    def resolve(name: str | None, *keywords: str) -> dict:
        if name:
            for t in tables:
                title = str(t.get("title") or t.get("table_name") or "")
                if title.lower() == name.lower():
                    return t
            raise SystemExit(f"Таблица не найдена: {name}")
        found = guess_table(tables, *keywords)
        if not found:
            raise SystemExit(f"Не удалось угадать таблицу по ключам: {keywords}")
        return found

    t_users = resolve(table_users, "user", "пользов", "клиент", "client")
    t_subs = resolve(table_subs, "subscri", "подписк", "vpn", "ключ")
    t_payments = resolve(table_payments, "payment", "плат", "оплат", "order", "заказ")

    logger.info("NocoDB tables: users=%s subs=%s payments=%s",
                t_users.get("title"), t_subs.get("title"), t_payments.get("title"))

    user_rows = [normalize_row(r) for r in await client.fetch_table(t_users)]
    sub_rows = [normalize_row(r) for r in await client.fetch_table(t_subs)]
    pay_rows = [normalize_row(r) for r in await client.fetch_table(t_payments)]
    return user_rows, sub_rows, pay_rows


async def migrate_from_api(
    *,
    dry_run: bool,
    table_users: str | None,
    table_subs: str | None,
    table_payments: str | None,
) -> None:
    user_rows, sub_rows, pay_rows = await load_from_nocodb_api(
        table_users=table_users,
        table_subs=table_subs,
        table_payments=table_payments,
    )
    logger.info("Loaded from API: users=%s subs=%s payments=%s",
                len(user_rows), len(sub_rows), len(pay_rows))

    export_dir = ROOT / "data" / "nocodb_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "users.json").write_text(
        json.dumps(user_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (export_dir / "subscriptions.json").write_text(
        json.dumps(sub_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (export_dir / "payments.json").write_text(
        json.dumps(pay_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    logger.info("Backup saved to data/nocodb_export/*.json")

    if not dry_run:
        await init_db()

    stats = {
        "users_created": 0, "users_updated": 0, "users_skipped": 0,
        "subs_created": 0, "subs_skipped": 0,
        "payments_created": 0, "payments_skipped": 0,
    }
    tg_to_user_id: dict[int, int] = {}

    async with async_session() as session:
        for raw in user_rows:
            mapped = map_user_row(raw)
            if not mapped or not mapped["telegram_id"]:
                stats["users_skipped"] += 1
                continue
            tg = mapped["telegram_id"]
            result = await session.execute(select(User).where(User.telegram_id == tg))
            user = result.scalar_one_or_none()
            if user:
                for k, v in mapped.items():
                    if k != "telegram_id" and v is not None:
                        setattr(user, k, v)
                stats["users_updated"] += 1
                tg_to_user_id[tg] = user.id
            elif dry_run:
                stats["users_created"] += 1
                tg_to_user_id[tg] = -tg
            else:
                user = User(**{k: v for k, v in mapped.items() if v is not None})
                session.add(user)
                await session.flush()
                tg_to_user_id[tg] = user.id
                stats["users_created"] += 1
        if not dry_run:
            await session.commit()

        for raw in sub_rows:
            mapped = map_subscription_row(raw)
            if not mapped:
                stats["subs_skipped"] += 1
                continue
            tg = mapped["telegram_id"]
            user_id = tg_to_user_id.get(tg)
            if not user_id:
                stats["subs_skipped"] += 1
                continue
            if not dry_run:
                sub = Subscription(user_id=user_id, **mapped)
                session.add(sub)
            stats["subs_created"] += 1
        if not dry_run:
            await session.commit()

        for raw in pay_rows:
            mapped = map_payment_row(raw)
            if not mapped:
                stats["payments_skipped"] += 1
                continue
            tg = mapped.get("telegram_id")
            user_id = tg_to_user_id.get(tg) if tg else None
            if not user_id and not dry_run:
                stats["payments_skipped"] += 1
                continue
            if not dry_run:
                pay = Payment(
                    user_id=user_id or 0,
                    telegram_id=tg,
                    amount=mapped["amount"],
                    plan=mapped.get("plan"),
                    months=mapped["months"],
                    order_id=mapped.get("order_id"),
                    yookassa_id=mapped.get("yookassa_id"),
                    status=mapped["status"],
                    paid_at=mapped.get("paid_at"),
                    fulfilled_at=mapped.get("paid_at") if mapped["status"] == PaymentStatus.SUCCEEDED else None,
                    provider="platega",
                )
                session.add(pay)
            stats["payments_created"] += 1
        if not dry_run:
            await session.commit()

    print("\n=== Отчёт миграции (API) ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("\nDry-run." if dry_run else "\nГотово.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Migrate NocoDB export into PostgreSQL")
    parser.add_argument("--users", type=Path, help="CSV/JSON users export")
    parser.add_argument("--subscriptions", type=Path, help="CSV/JSON subscriptions export")
    parser.add_argument("--payments", type=Path, help="CSV/JSON payments export")
    parser.add_argument("--from-api", action="store_true", help="Загрузить из NocoDB API")
    parser.add_argument("--discover", action="store_true", help="Показать таблицы и колонки NocoDB")
    parser.add_argument("--table-users", help="Имя таблицы пользователей в NocoDB")
    parser.add_argument("--table-subscriptions", help="Имя таблицы подписок")
    parser.add_argument("--table-payments", help="Имя таблицы платежей")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()

    if args.discover:
        token = os.getenv("NOCODB_TOKEN", "")
        if not token:
            raise SystemExit(
                "Нужен NOCODB_TOKEN.\n"
                "NocoDB → правый верхний угол → Account Settings → API Tokens → Create"
            )
        client = NocoDBClient(
            os.getenv("NOCODB_URL", DEFAULT_NOCODB_URL),
            token,
            os.getenv("NOCODB_BASE_ID", DEFAULT_NOCODB_BASE_ID),
        )
        asyncio.run(discover_schema(client))
        return

    if args.from_api:
        if not os.getenv("DB_URL") and not args.dry_run:
            parser.error("Задай DB_URL для записи в PostgreSQL")
        asyncio.run(migrate_from_api(
            dry_run=args.dry_run,
            table_users=args.table_users,
            table_subs=args.table_subscriptions,
            table_payments=args.table_payments,
        ))
        return

    default_dir = ROOT / "data" / "nocodb_export"
    users = args.users or (default_dir / "users.csv" if (default_dir / "users.csv").exists() else None)
    subs = args.subscriptions or (default_dir / "subscriptions.csv" if (default_dir / "subscriptions.csv").exists() else None)
    pays = args.payments or (default_dir / "payments.csv" if (default_dir / "payments.csv").exists() else None)

    if not any([users, subs, pays]):
        parser.error(
            "Укажи --from-api, --discover, CSV-файлы или положи экспорт в data/nocodb_export/"
        )

    if not os.getenv("DB_URL") and not args.dry_run:
        parser.error("Задай DB_URL в окружении (как в .env бота)")

    asyncio.run(migrate(users, subs, pays, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
