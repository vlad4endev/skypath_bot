"""Grace period reminders and marketing leads

Revision ID: 004
Revises: 003
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("grace_reminders_sent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("vpn_purged_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("is_marketing_lead", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_marketing_lead")
    op.drop_column("subscriptions", "vpn_purged_at")
    op.drop_column("subscriptions", "grace_reminders_sent")
