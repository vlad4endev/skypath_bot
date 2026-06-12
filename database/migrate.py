"""Применение Alembic-миграций при старте бота."""
from __future__ import annotations

import asyncio
import logging

from alembic import command
from alembic.config import Config as AlembicConfig

logger = logging.getLogger(__name__)


def _run_upgrade() -> None:
    """Синхронный alembic upgrade — вызывать только вне event loop или через to_thread."""
    cfg = AlembicConfig("alembic.ini")
    command.upgrade(cfg, "head")


async def upgrade_head() -> None:
    """alembic upgrade head — в отдельном потоке, чтобы не конфликтовать с asyncio.run в env.py."""
    await asyncio.to_thread(_run_upgrade)
    logger.info("Database migrations applied (alembic upgrade head)")
