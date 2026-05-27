"""Add village_name_manual to farmers and parcels, make village_id nullable

Revision ID: 008
Revises: 007
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add village_name_manual columns
    op.add_column("farmers", sa.Column("village_name_manual", sa.String(200)))
    op.add_column("parcels", sa.Column("village_name_manual", sa.String(200)))

    # Make village_id nullable (for manual village entries)
    op.alter_column("farmers", "village_id", nullable=True)
    op.alter_column("parcels", "village_id", nullable=True)


def downgrade() -> None:
    op.alter_column("parcels", "village_id", nullable=False)
    op.alter_column("farmers", "village_id", nullable=False)
    op.drop_column("parcels", "village_name_manual")
    op.drop_column("farmers", "village_name_manual")
