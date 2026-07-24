"""Add DigiPin fields to farmers and parcels.

Revision ID: 048
Revises: 047
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("farmers", sa.Column("home_digipin", sa.String(length=10), nullable=True))
    op.add_column("farmers", sa.Column("home_digipin_algorithm_version", sa.String(length=64), nullable=True))
    op.add_column("farmers", sa.Column("home_digipin_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_farmers_home_digipin", "farmers", ["home_digipin"], unique=False)

    op.add_column("parcels", sa.Column("centroid_digipin", sa.String(length=10), nullable=True))
    op.add_column("parcels", sa.Column("centroid_digipin_algorithm_version", sa.String(length=64), nullable=True))
    op.add_column("parcels", sa.Column("centroid_digipin_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_parcels_centroid_digipin", "parcels", ["centroid_digipin"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_parcels_centroid_digipin", table_name="parcels")
    op.drop_column("parcels", "centroid_digipin_generated_at")
    op.drop_column("parcels", "centroid_digipin_algorithm_version")
    op.drop_column("parcels", "centroid_digipin")

    op.drop_index("idx_farmers_home_digipin", table_name="farmers")
    op.drop_column("farmers", "home_digipin_generated_at")
    op.drop_column("farmers", "home_digipin_algorithm_version")
    op.drop_column("farmers", "home_digipin")
