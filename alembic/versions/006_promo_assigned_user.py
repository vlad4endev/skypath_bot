"""promo assigned telegram user

Revision ID: 006
Revises: 005
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column("assigned_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_promo_codes_assigned_telegram_id",
        "promo_codes",
        ["assigned_telegram_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_promo_codes_assigned_telegram_id", table_name="promo_codes")
    op.drop_column("promo_codes", "assigned_telegram_id")
