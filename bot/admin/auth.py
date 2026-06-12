"""Session auth for web admin panel (Redis-backed tokens)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone

import redis.asyncio as aioredis

from bot.config import Config

logger = logging.getLogger(__name__)

SESSION_PREFIX = "admin:session:"
SESSION_TTL_SEC = 60 * 60 * 24  # 24 hours


def _password_digest(password: str, secret: str) -> str:
    return hashlib.sha256(f"{secret}:{password}".encode()).hexdigest()


def verify_password(password: str, config: Config) -> bool:
    expected = (config.ADMIN_PASSWORD or "").strip()
    if not expected:
        return False
    digest = _password_digest(password, config.ADMIN_PASSWORD_SALT)
    return hmac.compare_digest(digest, expected)


def hash_password_for_env(password: str, salt: str) -> str:
    """Utility: generate ADMIN_PASSWORD hash for .env."""
    return _password_digest(password, salt)


class AdminAuth:
    def __init__(self, config: Config):
        self.config = config
        self._redis: aioredis.Redis | None = None

    async def _redis_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.config.REDIS_URL, decode_responses=True)
        return self._redis

    async def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        payload = json.dumps({"created_at": datetime.now(timezone.utc).isoformat()})
        r = await self._redis_client()
        await r.setex(f"{SESSION_PREFIX}{token}", SESSION_TTL_SEC, payload)
        return token

    async def validate_session(self, token: str | None) -> bool:
        if not token:
            return False
        r = await self._redis_client()
        return bool(await r.exists(f"{SESSION_PREFIX}{token}"))

    async def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        r = await self._redis_client()
        await r.delete(f"{SESSION_PREFIX}{token}")

    def extract_token(self, request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() or None
        return request.cookies.get("admin_token")
