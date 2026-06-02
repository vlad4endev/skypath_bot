"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created via Base.metadata.create_all on first boot.
    # Generate a full revision when schema changes:
    #   alembic revision --autogenerate -m "describe change"
    pass


def downgrade() -> None:
    pass
