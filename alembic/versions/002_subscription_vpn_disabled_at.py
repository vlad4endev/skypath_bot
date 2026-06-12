"""Add vpn_disabled_at to subscriptions

Revision ID: 002
Revises: 001
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("vpn_disabled_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "vpn_disabled_at")
