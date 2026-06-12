"""Применение Alembic-миграций при старте бота."""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config as AlembicConfig

logger = logging.getLogger(__name__)


def upgrade_head() -> None:
    """alembic upgrade head — добавляет новые колонки и таблицы."""
    cfg = AlembicConfig("alembic.ini")
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied (alembic upgrade head)")
