"""user web email and password

Revision ID: 009
Revises: 008
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _scalar(sql: str, **params: object) -> bool:
    result = op.get_bind().execute(sa.text(sql), params)
    return bool(result.scalar())


def _column_exists(table: str, column: str) -> bool:
    return _scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column)",
        table=table,
        column=column,
    )


def _index_exists(index: str) -> bool:
    return _scalar(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :index)",
        index=index,
    )


def upgrade() -> None:
    if not _column_exists("users", "web_email"):
        op.add_column("users", sa.Column("web_email", sa.String(length=255), nullable=True))
    if not _column_exists("users", "password_hash"):
        op.add_column("users", sa.Column("password_hash", sa.String(length=128), nullable=True))
    if not _column_exists("users", "web_registered_at"):
        op.add_column("users", sa.Column("web_registered_at", sa.DateTime(), nullable=True))
    if not _index_exists("ix_users_web_email"):
        op.create_index("ix_users_web_email", "users", ["web_email"], unique=True)


def downgrade() -> None:
    if _index_exists("ix_users_web_email"):
        op.drop_index("ix_users_web_email", table_name="users")
    if _column_exists("users", "web_registered_at"):
        op.drop_column("users", "web_registered_at")
    if _column_exists("users", "password_hash"):
        op.drop_column("users", "password_hash")
    if _column_exists("users", "web_email"):
        op.drop_column("users", "web_email")
