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


def _column_exists(table: str, column: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column)"
        ),
        {"table": table, "column": column},
    )
    return bool(result.scalar())


def _index_exists(table: str, index: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = :table AND indexname = :index)"
        ),
        {"table": table, "index": index},
    )
    return bool(result.scalar())


def upgrade() -> None:
    if not _column_exists("promo_codes", "assigned_telegram_id"):
        op.add_column(
            "promo_codes",
            sa.Column("assigned_telegram_id", sa.BigInteger(), nullable=True),
        )
    if not _index_exists("promo_codes", "ix_promo_codes_assigned_telegram_id"):
        op.create_index(
            "ix_promo_codes_assigned_telegram_id",
            "promo_codes",
            ["assigned_telegram_id"],
        )


def downgrade() -> None:
    if _index_exists("promo_codes", "ix_promo_codes_assigned_telegram_id"):
        op.drop_index("ix_promo_codes_assigned_telegram_id", table_name="promo_codes")
    if _column_exists("promo_codes", "assigned_telegram_id"):
        op.drop_column("promo_codes", "assigned_telegram_id")
