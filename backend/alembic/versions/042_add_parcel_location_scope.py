"""add parcel location scope

Revision ID: 042
Revises: 041
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("parcels", sa.Column("pin_code", sa.String(length=6), nullable=True))
    op.add_column("parcels", sa.Column("location_scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.alter_column("parcels", "location_scope", server_default=None)
    op.create_index("ix_parcels_pin_code", "parcels", ["pin_code"])
    op.create_index("idx_parcel_pin_code", "parcels", ["tenant_id", "pin_code"])
    op.create_index("idx_parcel_location_scope", "parcels", ["location_scope"], postgresql_using="gin")


def downgrade():
    op.drop_index("idx_parcel_location_scope", table_name="parcels")
    op.drop_index("idx_parcel_pin_code", table_name="parcels")
    op.drop_index("ix_parcels_pin_code", table_name="parcels")
    op.drop_column("parcels", "location_scope")
    op.drop_column("parcels", "pin_code")
