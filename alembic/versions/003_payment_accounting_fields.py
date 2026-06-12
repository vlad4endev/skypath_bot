"""Payment accounting fields

Revision ID: 003
Revises: 002
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("payments", sa.Column("provider", sa.String(length=32), server_default="platega", nullable=False))
    op.add_column("payments", sa.Column("description", sa.String(length=256), nullable=True))
    op.add_column("payments", sa.Column("paid_amount", sa.Float(), nullable=True))
    op.add_column("payments", sa.Column("provider_status", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("promo_code", sa.String(length=32), nullable=True))
    op.add_column("payments", sa.Column("webhook_received_at", sa.DateTime(), nullable=True))
    op.add_column("payments", sa.Column("fulfilled_at", sa.DateTime(), nullable=True))
    op.create_index("ix_payments_telegram_id", "payments", ["telegram_id"])
    op.create_index("ix_payments_user_status", "payments", ["user_id", "status"])
    op.create_index("ix_payments_telegram_created", "payments", ["telegram_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_telegram_created", table_name="payments")
    op.drop_index("ix_payments_user_status", table_name="payments")
    op.drop_index("ix_payments_telegram_id", table_name="payments")
    op.drop_column("payments", "fulfilled_at")
    op.drop_column("payments", "webhook_received_at")
    op.drop_column("payments", "promo_code")
    op.drop_column("payments", "provider_status")
    op.drop_column("payments", "paid_amount")
    op.drop_column("payments", "description")
    op.drop_column("payments", "provider")
    op.drop_column("payments", "telegram_id")
