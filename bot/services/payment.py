"""
Platega.io — создание платежей и обработка webhook
"""
import uuid
import logging
from typing import Any, Optional
import httpx
from bot.config import Config

logger = logging.getLogger(__name__)

PAID_STATUSES = frozenset({
    "CONFIRMED", "PAID", "SUCCESS", "SUCCEEDED", "COMPLETED",
})
PAID_STATUSES_LOWER = frozenset({
    "paid", "success", "succeeded", "completed", "confirmed",
})


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
        Возвращает: {payment_id, payment_url, order_id}
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

        transaction_id = data.get("id") or data.get("transactionId") or order_id
        logger.info("Payment created: %s / %s RUB", transaction_id, amount)
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
        if status.upper() in PAID_STATUSES or status.lower() in PAID_STATUSES_LOWER:
            return "succeeded"
        if status.upper() == "CANCELED" or status.lower() in ("canceled", "cancelled", "failed"):
            return "cancelled"
        return "pending"


def parse_platega_webhook(body: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Парсинг webhook Platega при успешной оплате."""
    if not body or not isinstance(body, dict):
        return None

    status_raw = str(body.get("status", ""))
    status_upper = status_raw.upper()
    if status_upper not in PAID_STATUSES and status_raw.lower() not in PAID_STATUSES_LOWER:
        return None

    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    order_id = body.get("orderId") or payload.get("orderId")
    transaction_id = body.get("id") or body.get("transactionId")

    if not order_id and not transaction_id:
        return None

    telegram_id = payload.get("telegram_id") or payload.get("userId")
    plan = payload.get("plan")
    months = payload.get("months", 1)
    subscription_id = payload.get("subscription_id", 0)

    try:
        months = int(months)
    except (TypeError, ValueError):
        months = 1

    try:
        subscription_id = int(subscription_id) if subscription_id else 0
    except (TypeError, ValueError):
        subscription_id = 0

    return {
        "order_id": order_id,
        "transaction_id": transaction_id,
        "telegram_id": str(telegram_id) if telegram_id is not None else None,
        "plan": plan,
        "months": months,
        "subscription_id": subscription_id,
        "amount": float(body.get("amount", 0) or 0),
    }
