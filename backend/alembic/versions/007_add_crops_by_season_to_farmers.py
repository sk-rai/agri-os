"""Add crops_by_season JSONB column to farmers table

Revision ID: 007
Revises: 006
Create Date: 2026-05-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("farmers", sa.Column("crops_by_season", JSONB, server_default="{}"))


def downgrade() -> None:
    op.drop_column("farmers", "crops_by_season")
