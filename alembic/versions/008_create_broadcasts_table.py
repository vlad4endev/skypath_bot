"""create broadcasts table if missing

Revision ID: 008
Revises: 007
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def _scalar(sql: str, **params: object) -> bool:
    result = op.get_bind().execute(sa.text(sql), params)
    return bool(result.scalar())


def _table_exists(name: str) -> bool:
    return _scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :name)",
        name=name,
    )


def _column_exists(table: str, column: str) -> bool:
    return _scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column)",
        table=table,
        column=column,
    )


def _index_exists(table: str, index: str) -> bool:
    return _scalar(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = :table AND indexname = :index)",
        table=table,
        index=index,
    )


def upgrade() -> None:
    broadcast_status = sa.Enum(
        "scheduled", "sending", "sent", "cancelled", "failed",
        name="broadcaststatus",
    )
    broadcast_status.create(op.get_bind(), checkfirst=True)

    if not _table_exists("broadcasts"):
        op.create_table(
            "broadcasts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("target", sa.String(length=32), server_default="all", nullable=False),
            sa.Column("status", broadcast_status, server_default="sent", nullable=False),
            sa.Column("send_at", sa.DateTime(), nullable=True),
            sa.Column("sent", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("sent_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("target_count", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
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

    for index, cols in (
        ("ix_broadcasts_status", ["status"]),
        ("ix_broadcasts_send_at", ["send_at"]),
        ("ix_broadcasts_target", ["target"]),
        ("ix_broadcasts_status_send_at", ["status", "send_at"]),
    ):
        if not _index_exists("broadcasts", index):
            op.create_index(index, "broadcasts", cols)


def downgrade() -> None:
    if _table_exists("broadcasts"):
        op.drop_table("broadcasts")
    sa.Enum(name="broadcaststatus").drop(op.get_bind(), checkfirst=True)
