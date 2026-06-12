"""Session auth for web cabinet (email + password login)."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone

import redis.asyncio as aioredis

from bot.config import Config

logger = logging.getLogger(__name__)

SESSION_PREFIX = "cabinet:session:"
SESSION_TTL_SEC = 60 * 60 * 24 * 7  # 7 days


class CabinetAuth:
    def __init__(self, config: Config):
        self.config = config
        self._redis: aioredis.Redis | None = None

    async def _redis_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.config.REDIS_URL, decode_responses=True)
        return self._redis

    async def create_session(self, *, user_id: int, telegram_id: int, email: str) -> str:
        token = secrets.token_urlsafe(32)
        payload = json.dumps({
            "user_id": user_id,
            "telegram_id": telegram_id,
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r = await self._redis_client()
        await r.setex(f"{SESSION_PREFIX}{token}", SESSION_TTL_SEC, payload)
        return token

    async def get_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        r = await self._redis_client()
        raw = await r.get(f"{SESSION_PREFIX}{token}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def validate_session(self, token: str | None) -> bool:
        return (await self.get_session(token)) is not None

    async def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        r = await self._redis_client()
        await r.delete(f"{SESSION_PREFIX}{token}")

    def extract_token(self, request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() or None
        return request.cookies.get("cabinet_token")
