"""broadcasts enhanced — status, stats, scheduling

Revision ID: 007
Revises: 006
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
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


def _table_exists(table: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :table)"
        ),
        {"table": table},
    )
    return bool(result.scalar())


def upgrade() -> None:
    if not _table_exists("broadcasts"):
        return

    broadcast_status = sa.Enum(
        "scheduled", "sending", "sent", "cancelled", "failed",
        name="broadcaststatus",
    )
    broadcast_status.create(op.get_bind(), checkfirst=True)

    columns = [
        ("name", sa.Column("name", sa.String(128), nullable=True)),
        ("status", sa.Column(
            "status",
            broadcast_status,
            nullable=False,
            server_default="sent",
        )),
        ("failed_count", sa.Column("failed_count", sa.Integer(), server_default="0")),
        ("target_count", sa.Column("target_count", sa.Integer(), nullable=True)),
        ("started_at", sa.Column("started_at", sa.DateTime(), nullable=True)),
        ("completed_at", sa.Column("completed_at", sa.DateTime(), nullable=True)),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True)),
    ]
    for col_name, col_def in columns:
        if not _column_exists("broadcasts", col_name):
            op.add_column("broadcasts", col_def)

    if not _index_exists("broadcasts", "ix_broadcasts_status"):
        op.create_index("ix_broadcasts_status", "broadcasts", ["status"])
    if not _index_exists("broadcasts", "ix_broadcasts_send_at"):
        op.create_index("ix_broadcasts_send_at", "broadcasts", ["send_at"])
    if not _index_exists("broadcasts", "ix_broadcasts_target"):
        op.create_index("ix_broadcasts_target", "broadcasts", ["target"])
    if not _index_exists("broadcasts", "ix_broadcasts_status_send_at"):
        op.create_index("ix_broadcasts_status_send_at", "broadcasts", ["status", "send_at"])


def downgrade() -> None:
    if not _table_exists("broadcasts"):
        return

    for index in (
        "ix_broadcasts_status_send_at",
        "ix_broadcasts_target",
        "ix_broadcasts_send_at",
        "ix_broadcasts_status",
    ):
        if _index_exists("broadcasts", index):
            op.drop_index(index, table_name="broadcasts")

    for col in (
        "error_message", "completed_at", "started_at", "target_count",
        "failed_count", "status", "name",
    ):
        if _column_exists("broadcasts", col):
            op.drop_column("broadcasts", col)

    sa.Enum(name="broadcaststatus").drop(op.get_bind(), checkfirst=True)
