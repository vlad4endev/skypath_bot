"""
Platega.io — создание платежей, проверка статуса и разбор webhook.
"""
import json
import uuid
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional
import httpx
from bot.config import Config

logger = logging.getLogger(__name__)

PAID_STATUSES = frozenset({
    "CONFIRMED", "PAID", "SUCCESS", "SUCCEEDED", "COMPLETED",
})
PAID_STATUSES_LOWER = frozenset({
    "paid", "success", "succeeded", "completed", "confirmed",
})
CANCELLED_STATUSES = frozenset({
    "CANCELED", "CANCELLED", "FAILED", "EXPIRED", "REJECTED",
})
CANCELLED_STATUSES_LOWER = frozenset({
    "canceled", "cancelled", "failed", "expired", "rejected",
})


@dataclass(frozen=True)
class PlategaWebhookEvent:
  """Нормализованное событие от Platega."""
  event_type: Literal["paid", "cancelled", "ignored"]
  order_id: str | None
  transaction_id: str | None
  telegram_id: int | None
  plan: str | None
  months: int
  subscription_id: int
  amount: float
  currency: str
  provider_status: str
  raw: dict[str, Any]


def _extract_amount(body: dict[str, Any]) -> float:
    details = body.get("paymentDetails") or {}
    if isinstance(details, dict):
        raw = details.get("amount") or details.get("sum")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    for key in ("amount", "sum", "total"):
        if body.get(key) is not None:
            try:
                return float(body[key])
            except (TypeError, ValueError):
                pass
    return 0.0


def _extract_currency(body: dict[str, Any]) -> str:
    details = body.get("paymentDetails") or {}
    if isinstance(details, dict) and details.get("currency"):
        return str(details["currency"]).upper()
    return str(body.get("currency") or "RUB").upper()


def _parse_payload_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        return default


def classify_provider_status(status_raw: str) -> Literal["paid", "cancelled", "ignored"]:
    upper = status_raw.upper()
    lower = status_raw.lower()
    if upper in PAID_STATUSES or lower in PAID_STATUSES_LOWER:
        return "paid"
    if upper in CANCELLED_STATUSES or lower in CANCELLED_STATUSES_LOWER:
        return "cancelled"
    return "ignored"


class PlategaClient:
    BASE_URL = "https://app.platega.io/transaction/process"

    def __init__(self, config: Config):
        self.merchant_id = config.PLATEGA_MERCHANT_ID
        self.secret = config.PLATEGA_SECRET
        self.bot_username = config.BOT_USERNAME

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret,
        }

    async def create_payment(
        self,
        amount: float,
        description: str,
        metadata: dict,
        return_url: Optional[str] = None,
    ) -> dict:
        """
        Создать платёж в Platega.
        Возвращает: {payment_id, payment_url, order_id, status}
        """
        order_id = str(uuid.uuid4())
        payload_meta = {**metadata, "orderId": order_id}

        body = {
            "paymentMethod": 2,
            "paymentDetails": {
                "amount": int(amount),
                "currency": "RUB",
            },
            "description": description,
            "return": return_url or f"https://t.me/{self.bot_username}",
            "payload": payload_meta,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                self.BASE_URL,
                json=body,
                headers=self._headers(),
            )

        if resp.status_code not in (200, 201):
            logger.error("Platega error: %s %s", resp.status_code, resp.text)
            raise RuntimeError(f"Platega payment creation failed: {resp.status_code}")

        data = resp.json()
        payment_url = (
            data.get("redirect")
            or data.get("paymentUrl")
            or data.get("url")
        )
        if not payment_url:
            logger.error("Platega response without payment URL: %s", data)
            raise RuntimeError("Platega: payment URL missing in response")

        transaction_id = str(data.get("id") or data.get("transactionId") or order_id)
        logger.info(
            "Platega payment created order=%s tx=%s amount=%s RUB",
            order_id,
            transaction_id,
            amount,
        )
        return {
            "payment_id": transaction_id,
            "payment_url": payment_url,
            "order_id": order_id,
            "status": "pending",
        }

    async def check_payment_status(self, transaction_id: str) -> str:
        """Проверить статус транзакции через API Platega."""
        url = f"https://app.platega.io/transaction/{transaction_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())

        if resp.status_code == 404:
            return "pending"
        if resp.status_code != 200:
            logger.warning("Platega status check %s: %s", resp.status_code, resp.text)
            return "pending"

        data = resp.json()
        status = str(data.get("status", "pending"))
        kind = classify_provider_status(status)
        if kind == "paid":
            return "succeeded"
        if kind == "cancelled":
            return "cancelled"
        return "pending"

    async def fetch_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Получить полные данные транзакции из API."""
        url = f"https://app.platega.io/transaction/{transaction_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None


def parse_platega_webhook(body: dict[str, Any]) -> Optional[PlategaWebhookEvent]:
    """Разбор webhook Platega в единую структуру."""
    if not body or not isinstance(body, dict):
        return None

    status_raw = str(body.get("status", ""))
    event_type = classify_provider_status(status_raw)

    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    order_id = body.get("orderId") or payload.get("orderId")
    transaction_id = body.get("id") or body.get("transactionId")
    if transaction_id is not None:
        transaction_id = str(transaction_id)
    if order_id is not None:
        order_id = str(order_id)

    if not order_id and not transaction_id:
        return None

    telegram_raw = payload.get("telegram_id") or payload.get("userId")
    telegram_id = _parse_payload_int(telegram_raw, 0) or None

    return PlategaWebhookEvent(
        event_type=event_type,
        order_id=order_id,
        transaction_id=transaction_id,
        telegram_id=telegram_id,
        plan=str(payload.get("plan") or "") or None,
        months=_parse_payload_int(payload.get("months"), 1),
        subscription_id=_parse_payload_int(payload.get("subscription_id"), 0),
        amount=_extract_amount(body),
        currency=_extract_currency(body),
        provider_status=status_raw,
        raw=body,
    )


def webhook_event_to_json(event: PlategaWebhookEvent) -> str:
    return json.dumps(event.raw, ensure_ascii=False, default=str)


# Обратная совместимость для старых вызовов
def parse_platega_webhook_legacy(body: dict[str, Any]) -> Optional[dict[str, Any]]:
    event = parse_platega_webhook(body)
    if not event or event.event_type != "paid":
        return None
    return {
        "order_id": event.order_id,
        "transaction_id": event.transaction_id,
        "telegram_id": str(event.telegram_id) if event.telegram_id else None,
        "plan": event.plan,
        "months": event.months,
        "subscription_id": event.subscription_id,
        "amount": event.amount,
    }
