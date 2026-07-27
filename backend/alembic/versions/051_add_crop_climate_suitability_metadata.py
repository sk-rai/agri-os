"""Add crop climate suitability metadata.

Revision ID: 051
Revises: 050
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    ]


def upgrade() -> None:
    op.create_table(
        "geography_climate_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("region_code", sa.String(length=80), nullable=False),
        sa.Column("region_name", sa.String(length=180), nullable=False),
        sa.Column("region_system", sa.String(length=60), nullable=False),
        sa.Column("parent_region_code", sa.String(length=80), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=False, server_default="IND"),
        sa.Column("rainfall_band_mm", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("temperature_band_c", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("length_of_growing_period_days", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dominant_soil_groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("irrigation_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.String(length=50), nullable=False, server_default="LOCAL_DEMO_SEED"),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="MANUAL_REVIEW"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("region_code", name="uq_geography_climate_regions_code"),
    )
    op.create_index("idx_geography_climate_regions_region_code", "geography_climate_regions", ["region_code"])
    op.create_index("idx_geography_climate_regions_country_code", "geography_climate_regions", ["country_code"])
    op.create_index("idx_geography_climate_region_system", "geography_climate_regions", ["region_system", "review_status"])

    op.create_table(
        "geography_climate_region_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("region_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_climate_regions.id"), nullable=False),
        sa.Column("region_code", sa.String(length=80), nullable=False),
        sa.Column("scope_level", sa.String(length=30), nullable=False),
        sa.Column("state_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("district_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("block_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("village_lgd_code", sa.String(length=30), nullable=True),
        sa.Column("pin_code", sa.String(length=6), nullable=True),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.String(length=50), nullable=False, server_default="LOCAL_DEMO_SEED"),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="MANUAL_REVIEW"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("region_code", "scope_level", "state_lgd_code", "district_lgd_code", "block_lgd_code", "village_lgd_code", "pin_code", name="uq_geography_climate_region_mapping_scope"),
    )
    op.create_index("idx_geography_climate_region_mappings_region_id", "geography_climate_region_mappings", ["region_id"])
    op.create_index("idx_geography_climate_region_mappings_region_code", "geography_climate_region_mappings", ["region_code"])
    op.create_index("idx_geography_climate_region_mappings_scope_level", "geography_climate_region_mappings", ["scope_level"])
    op.create_index("idx_geography_climate_region_mapping_lookup", "geography_climate_region_mappings", ["scope_level", "state_lgd_code", "district_lgd_code", "pin_code"])

    op.create_table(
        "crop_climate_suitability_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("crop_code", sa.String(length=30), sa.ForeignKey("crops.code"), nullable=False),
        sa.Column("season_code", sa.String(length=20), nullable=False),
        sa.Column("region_code", sa.String(length=80), sa.ForeignKey("geography_climate_regions.region_code"), nullable=False),
        sa.Column("geography_scope", sa.String(length=30), nullable=False, server_default="REGION"),
        sa.Column("suitability_status", sa.String(length=30), nullable=False, server_default="UNKNOWN"),
        sa.Column("confidence", sa.String(length=50), nullable=False, server_default="LOCAL_DEMO_SEED"),
        sa.Column("rainfall_min_mm", sa.Integer(), nullable=True),
        sa.Column("rainfall_max_mm", sa.Integer(), nullable=True),
        sa.Column("temperature_min_c", sa.Integer(), nullable=True),
        sa.Column("temperature_max_c", sa.Integer(), nullable=True),
        sa.Column("soil_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("irrigation_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("typical_sowing_window", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("typical_harvest_window", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warning_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="MANUAL_REVIEW"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("crop_code", "season_code", "region_code", "geography_scope", name="uq_crop_climate_suitability_rule_scope"),
    )
    op.create_index("idx_crop_climate_suitability_rules_crop_code", "crop_climate_suitability_rules", ["crop_code"])
    op.create_index("idx_crop_climate_suitability_rules_season_code", "crop_climate_suitability_rules", ["season_code"])
    op.create_index("idx_crop_climate_suitability_rules_region_code", "crop_climate_suitability_rules", ["region_code"])
    op.create_index("idx_crop_climate_suitability_rules_review_status", "crop_climate_suitability_rules", ["review_status"])
    op.create_index("idx_crop_climate_suitability_lookup", "crop_climate_suitability_rules", ["crop_code", "season_code", "region_code", "suitability_status"])


def downgrade() -> None:
    op.drop_index("idx_crop_climate_suitability_lookup", table_name="crop_climate_suitability_rules")
    op.drop_index("idx_crop_climate_suitability_rules_review_status", table_name="crop_climate_suitability_rules")
    op.drop_index("idx_crop_climate_suitability_rules_region_code", table_name="crop_climate_suitability_rules")
    op.drop_index("idx_crop_climate_suitability_rules_season_code", table_name="crop_climate_suitability_rules")
    op.drop_index("idx_crop_climate_suitability_rules_crop_code", table_name="crop_climate_suitability_rules")
    op.drop_table("crop_climate_suitability_rules")
    op.drop_index("idx_geography_climate_region_mapping_lookup", table_name="geography_climate_region_mappings")
    op.drop_index("idx_geography_climate_region_mappings_scope_level", table_name="geography_climate_region_mappings")
    op.drop_index("idx_geography_climate_region_mappings_region_code", table_name="geography_climate_region_mappings")
    op.drop_index("idx_geography_climate_region_mappings_region_id", table_name="geography_climate_region_mappings")
    op.drop_table("geography_climate_region_mappings")
    op.drop_index("idx_geography_climate_region_system", table_name="geography_climate_regions")
    op.drop_index("idx_geography_climate_regions_country_code", table_name="geography_climate_regions")
    op.drop_index("idx_geography_climate_regions_region_code", table_name="geography_climate_regions")
    op.drop_table("geography_climate_regions")