"""Add irrigation_source to parcels

Revision ID: 011
Revises: 010
Create Date: 2026-05-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("irrigation_source", sa.String(50)))


def downgrade() -> None:
    op.drop_column("parcels", "irrigation_source")
