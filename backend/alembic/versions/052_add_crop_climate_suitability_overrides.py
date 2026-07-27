"""Add crop climate suitability overrides.

Revision ID: 052
Revises: 051
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crop_climate_suitability_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crop_code", sa.String(length=30), sa.ForeignKey("crops.code"), nullable=False),
        sa.Column("season_code", sa.String(length=20), nullable=False),
        sa.Column("region_code", sa.String(length=80), sa.ForeignKey("geography_climate_regions.region_code"), nullable=False),
        sa.Column("geography_scope", sa.String(length=30), nullable=False, server_default="REGION"),
        sa.Column("suitability_status", sa.String(length=30), nullable=False, server_default="UNKNOWN"),
        sa.Column("confidence", sa.String(length=50), nullable=False, server_default="CLIENT_OVERRIDE"),
        sa.Column("irrigation_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("warning_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="PUBLISHED"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("published_by", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "idx_crop_climate_suitability_override_lookup",
        "crop_climate_suitability_overrides",
        ["tenant_id", "project_id", "crop_code", "season_code", "region_code", "review_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_crop_climate_suitability_override_lookup", table_name="crop_climate_suitability_overrides")
    op.drop_table("crop_climate_suitability_overrides")
