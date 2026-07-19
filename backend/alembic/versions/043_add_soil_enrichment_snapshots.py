"""add soil enrichment snapshots

Revision ID: 043
Revises: 042
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "soil_enrichment_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_dataset", sa.String(length=100), nullable=True),
        sa.Column("snapshot_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latitude", sa.DECIMAL(10, 8), nullable=True),
        sa.Column("longitude", sa.DECIMAL(11, 8), nullable=True),
        sa.Column("depth_layer", sa.String(length=50), nullable=True),
        sa.Column("resolution_meters", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(length=30), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ph", sa.DECIMAL(5, 2), nullable=True),
        sa.Column("organic_carbon", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("nitrogen", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("clay_percent", sa.DECIMAL(6, 2), nullable=True),
        sa.Column("silt_percent", sa.DECIMAL(6, 2), nullable=True),
        sa.Column("sand_percent", sa.DECIMAL(6, 2), nullable=True),
        sa.Column("bulk_density", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("cec", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("surface_soil_moisture", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("root_zone_soil_moisture", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("soil_temperature_c", sa.DECIMAL(6, 2), nullable=True),
        sa.Column("evapotranspiration_mm", sa.DECIMAL(8, 3), nullable=True),
        sa.Column("normalized_values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("idx_soil_enrichment_tenant", "soil_enrichment_snapshots", ["tenant_id"])
    op.create_index("idx_soil_enrichment_parcel", "soil_enrichment_snapshots", ["parcel_id"])
    op.create_index("idx_soil_enrichment_farmer", "soil_enrichment_snapshots", ["farmer_id"])
    op.create_index("idx_soil_enrichment_provider", "soil_enrichment_snapshots", ["provider"])
    op.create_index("idx_soil_enrichment_type", "soil_enrichment_snapshots", ["snapshot_type"])
    op.create_index("idx_soil_enrichment_observed", "soil_enrichment_snapshots", ["observed_at"])
    op.create_index("idx_soil_enrichment_latest", "soil_enrichment_snapshots", ["tenant_id", "parcel_id", "provider", "snapshot_type", "observed_at"])


def downgrade():
    op.drop_index("idx_soil_enrichment_latest", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_observed", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_type", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_provider", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_farmer", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_parcel", table_name="soil_enrichment_snapshots")
    op.drop_index("idx_soil_enrichment_tenant", table_name="soil_enrichment_snapshots")
    op.drop_table("soil_enrichment_snapshots")
