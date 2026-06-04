"""Add aadhaar_number to farmers, annual_rent to parcels

Revision ID: 010
Revises: 009
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Farmer: add aadhaar (father_name, age, gender already exist from migration 005)
    op.add_column("farmers", sa.Column("aadhaar_number", sa.String(12)))

    # Parcel: add annual_rent, widen survey_number
    op.add_column("parcels", sa.Column("annual_rent", sa.DECIMAL(12, 2)))
    op.add_column("parcels", sa.Column("annual_rent_currency", sa.String(3), server_default="INR"))
    op.alter_column("parcels", "survey_number", type_=sa.String(100))


def downgrade() -> None:
    op.alter_column("parcels", "survey_number", type_=sa.String(50))
    op.drop_column("parcels", "annual_rent_currency")
    op.drop_column("parcels", "annual_rent")
    op.drop_column("farmers", "aadhaar_number")
