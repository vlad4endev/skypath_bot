"""
YooKassa — создание платежей и обработка webhook
"""
import uuid
import logging
from typing import Optional
import httpx
from bot.config import Config

logger = logging.getLogger(__name__)


class YooKassaClient:
    BASE_URL = "https://api.yookassa.ru/v3"

    def __init__(self, config: Config):
        self.shop_id = config.YOOKASSA_SHOP_ID
        self.secret_key = config.YOOKASSA_SECRET_KEY
        self.return_url = config.YOOKASSA_RETURN_URL

    def _auth(self) -> tuple[str, str]:
        return self.shop_id, self.secret_key

    async def create_payment(
        self,
        amount: float,
        description: str,
        metadata: dict,
        return_url: Optional[str] = None,
    ) -> dict:
        """
        Создать платёж в YooKassa
        Возвращает: {payment_id, payment_url, order_id}
        """
        order_id = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or self.return_url,
            },
            "capture": True,
            "description": description,
            "metadata": {**metadata, "order_id": order_id},
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments",
                json=payload,
                auth=self._auth(),
                headers={
                    "Idempotence-Key": order_id,
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code not in (200, 201):
            logger.error(f"YooKassa error: {resp.status_code} {resp.text}")
            raise RuntimeError(f"YooKassa payment creation failed: {resp.status_code}")

        data = resp.json()
        payment_url = data["confirmation"]["confirmation_url"]
        payment_id = data["id"]

        logger.info(f"✅ Payment created: {payment_id} / {amount} RUB")
        return {
            "payment_id": payment_id,
            "payment_url": payment_url,
            "order_id": order_id,
            "status": data["status"],
        }

    async def get_payment(self, payment_id: str) -> dict:
        """Проверить статус платежа"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.BASE_URL}/payments/{payment_id}",
                auth=self._auth(),
            )
        resp.raise_for_status()
        return resp.json()

    async def check_payment_status(self, payment_id: str) -> str:
        """Вернуть статус: pending / succeeded / cancelled"""
        data = await self.get_payment(payment_id)
        return data.get("status", "pending")


def parse_webhook_event(body: dict) -> Optional[dict]:
    """
    Парсинг YooKassa webhook уведомления
    Возвращает dict с payment_id и metadata при успешной оплате
    """
    event_type = body.get("event", "")
    if event_type != "payment.succeeded":
        return None

    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id")
    metadata = payment_obj.get("metadata", {})
    amount = payment_obj.get("amount", {}).get("value")

    if not payment_id:
        return None

    subscription_id = metadata.get("subscription_id")
    try:
        subscription_id = int(subscription_id) if subscription_id else 0
    except (TypeError, ValueError):
        subscription_id = 0

    return {
        "payment_id": payment_id,
        "order_id": metadata.get("order_id"),
        "telegram_id": metadata.get("telegram_id"),
        "plan": metadata.get("plan"),
        "months": int(metadata.get("months", 1)),
        "amount": float(amount or 0),
        "subscription_id": subscription_id,
    }
