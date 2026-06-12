"""promotions and enhanced promo codes

Revision ID: 005
Revises: 004
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _index_exists(table: str, index: str) -> bool:
    return index in {i["name"] for i in _insp().get_indexes(table)}


def _fk_exists(table: str, fk_name: str) -> bool:
    return fk_name in {fk["name"] for fk in _insp().get_foreign_keys(table)}


def upgrade() -> None:
    if not _table_exists("promotions"):
        op.create_table(
            "promotions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=512), nullable=True),
            sa.Column("discount_pct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("discount_amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("plans", sa.JSON(), nullable=True),
            sa.Column("months", sa.JSON(), nullable=True),
            sa.Column("min_amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("new_users_only", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stackable_with_promo", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
        )

    promo_cols = {
        "name": sa.Column("name", sa.String(length=128), nullable=True),
        "description": sa.Column("description", sa.String(length=512), nullable=True),
        "plans": sa.Column("plans", sa.JSON(), nullable=True),
        "months": sa.Column("months", sa.JSON(), nullable=True),
        "min_amount": sa.Column("min_amount", sa.Integer(), nullable=False, server_default="0"),
        "one_per_user": sa.Column(
            "one_per_user", sa.Boolean(), nullable=False, server_default="true"
        ),
    }
    for col_name, col_def in promo_cols.items():
        if not _column_exists("promo_codes", col_name):
            op.add_column("promo_codes", col_def)

    payment_cols = {
        "promotion_id": sa.Column("promotion_id", sa.Integer(), nullable=True),
        "original_amount": sa.Column("original_amount", sa.Float(), nullable=True),
        "discount_amount": sa.Column("discount_amount", sa.Float(), nullable=True),
    }
    for col_name, col_def in payment_cols.items():
        if not _column_exists("payments", col_name):
            op.add_column("payments", col_def)

    if not _fk_exists("payments", "fk_payments_promotion_id"):
        op.create_foreign_key(
            "fk_payments_promotion_id",
            "payments",
            "promotions",
            ["promotion_id"],
            ["id"],
        )

    if not _table_exists("promo_code_usages"):
        op.create_table(
            "promo_code_usages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("promo_code_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("payment_id", sa.Integer(), nullable=True),
            sa.Column("used_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("promo_code_usages", "ix_promo_usage_code_user"):
        op.create_index(
            "ix_promo_usage_code_user", "promo_code_usages", ["promo_code_id", "user_id"]
        )
    if not _index_exists("promo_code_usages", "ix_promo_code_usages_telegram_id"):
        op.create_index(
            "ix_promo_code_usages_telegram_id", "promo_code_usages", ["telegram_id"]
        )


def downgrade() -> None:
    if _index_exists("promo_code_usages", "ix_promo_code_usages_telegram_id"):
        op.drop_index("ix_promo_code_usages_telegram_id", table_name="promo_code_usages")
    if _index_exists("promo_code_usages", "ix_promo_usage_code_user"):
        op.drop_index("ix_promo_usage_code_user", table_name="promo_code_usages")
    if _table_exists("promo_code_usages"):
        op.drop_table("promo_code_usages")

    if _fk_exists("payments", "fk_payments_promotion_id"):
        op.drop_constraint("fk_payments_promotion_id", "payments", type_="foreignkey")
    for col in ("discount_amount", "original_amount", "promotion_id"):
        if _column_exists("payments", col):
            op.drop_column("payments", col)

    for col in ("one_per_user", "min_amount", "months", "plans", "description", "name"):
        if _column_exists("promo_codes", col):
            op.drop_column("promo_codes", col)

    if _table_exists("promotions"):
        op.drop_table("promotions")
