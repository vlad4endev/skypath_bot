"""promotions and enhanced promo codes

Revision ID: 005
Revises: 004
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
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

    op.add_column("promo_codes", sa.Column("name", sa.String(length=128), nullable=True))
    op.add_column("promo_codes", sa.Column("description", sa.String(length=512), nullable=True))
    op.add_column("promo_codes", sa.Column("plans", sa.JSON(), nullable=True))
    op.add_column("promo_codes", sa.Column("months", sa.JSON(), nullable=True))
    op.add_column("promo_codes", sa.Column("min_amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "promo_codes",
        sa.Column("one_per_user", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.add_column("payments", sa.Column("promotion_id", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("original_amount", sa.Float(), nullable=True))
    op.add_column("payments", sa.Column("discount_amount", sa.Float(), nullable=True))
    op.create_foreign_key(
        "fk_payments_promotion_id",
        "payments",
        "promotions",
        ["promotion_id"],
        ["id"],
    )

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
    op.create_index("ix_promo_usage_code_user", "promo_code_usages", ["promo_code_id", "user_id"])
    op.create_index("ix_promo_code_usages_telegram_id", "promo_code_usages", ["telegram_id"])


def downgrade() -> None:
    op.drop_index("ix_promo_code_usages_telegram_id", table_name="promo_code_usages")
    op.drop_index("ix_promo_usage_code_user", table_name="promo_code_usages")
    op.drop_table("promo_code_usages")

    op.drop_constraint("fk_payments_promotion_id", "payments", type_="foreignkey")
    op.drop_column("payments", "discount_amount")
    op.drop_column("payments", "original_amount")
    op.drop_column("payments", "promotion_id")

    op.drop_column("promo_codes", "one_per_user")
    op.drop_column("promo_codes", "min_amount")
    op.drop_column("promo_codes", "months")
    op.drop_column("promo_codes", "plans")
    op.drop_column("promo_codes", "description")
    op.drop_column("promo_codes", "name")

    op.drop_table("promotions")
