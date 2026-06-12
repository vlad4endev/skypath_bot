"""Add preferred_locale to users."""
from alembic import op
import sqlalchemy as sa

revision = "010_user_preferred_locale"
down_revision = "009_user_web_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_locale", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_locale")
