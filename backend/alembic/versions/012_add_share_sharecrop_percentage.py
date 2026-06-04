"""Add share_percentage and sharecrop_percentage to parcels

Revision ID: 012
Revises: 011
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("share_percentage", sa.Integer))
    op.add_column("parcels", sa.Column("sharecrop_percentage", sa.Integer))


def downgrade() -> None:
    op.drop_column("parcels", "sharecrop_percentage")
    op.drop_column("parcels", "share_percentage")
