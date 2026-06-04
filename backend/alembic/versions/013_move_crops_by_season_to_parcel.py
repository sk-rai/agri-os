"""Add crops_by_season to parcels (moved from farmer to parcel level)

Revision ID: 013
Revises: 012
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("crops_by_season", JSONB, server_default="{}"))


def downgrade() -> None:
    op.drop_column("parcels", "crops_by_season")
