"""add village demographic profiles

Revision ID: 057
Revises: 056
Create Date: 2026-08-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geography_village_demographic_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("village_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("source_feature_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_feature_index", sa.Integer(), nullable=True),
        sa.Column("source_vlcode", sa.String(length=40), nullable=True),
        sa.Column("source_state_name", sa.String(length=160), nullable=True),
        sa.Column("source_district_name", sa.String(length=160), nullable=True),
        sa.Column("source_subdistrict_name", sa.String(length=160), nullable=True),
        sa.Column("source_village_name", sa.String(length=240), nullable=True),
        sa.Column("total_population", sa.Integer(), nullable=True),
        sa.Column("male_population", sa.Integer(), nullable=True),
        sa.Column("female_population", sa.Integer(), nullable=True),
        sa.Column("total_households", sa.Integer(), nullable=True),
        sa.Column("average_household_size", sa.Numeric(), nullable=True),
        sa.Column("rural_urban", sa.String(length=40), nullable=True),
        sa.Column("nearest_town_name", sa.String(length=240), nullable=True),
        sa.Column("nearest_town_distance_km", sa.Numeric(), nullable=True),
        sa.Column("total_geographical_area", sa.Numeric(), nullable=True),
        sa.Column("forest_area", sa.Numeric(), nullable=True),
        sa.Column("non_agricultural_area", sa.Numeric(), nullable=True),
        sa.Column("barren_uncultivable_land", sa.Numeric(), nullable=True),
        sa.Column("permanent_pastures_grazing_area", sa.Numeric(), nullable=True),
        sa.Column("culturable_waste_land", sa.Numeric(), nullable=True),
        sa.Column("fallow_land_other_than_current", sa.Numeric(), nullable=True),
        sa.Column("current_fallow_area", sa.Numeric(), nullable=True),
        sa.Column("net_area_sown", sa.Numeric(), nullable=True),
        sa.Column("total_unirrigated_land", sa.Numeric(), nullable=True),
        sa.Column("area_irrigated_by_source", sa.Numeric(), nullable=True),
        sa.Column("canals_area", sa.Numeric(), nullable=True),
        sa.Column("wells_tube_wells_area", sa.Numeric(), nullable=True),
        sa.Column("tanks_lakes_area", sa.Numeric(), nullable=True),
        sa.Column("waterfall_area", sa.Numeric(), nullable=True),
        sa.Column("other_source_area", sa.Numeric(), nullable=True),
        sa.Column("tapwater_treated_status", sa.String(length=80), nullable=True),
        sa.Column("tapwater_untreated_status", sa.String(length=80), nullable=True),
        sa.Column("covered_well_status", sa.String(length=80), nullable=True),
        sa.Column("uncovered_well_status", sa.String(length=80), nullable=True),
        sa.Column("handpump_status", sa.String(length=80), nullable=True),
        sa.Column("tubewell_borehole_status", sa.String(length=80), nullable=True),
        sa.Column("spring_status", sa.String(length=80), nullable=True),
        sa.Column("river_canal_status", sa.String(length=80), nullable=True),
        sa.Column("tank_pond_lake_status", sa.String(length=80), nullable=True),
        sa.Column("closed_drainage_status", sa.String(length=80), nullable=True),
        sa.Column("open_drainage_status", sa.String(length=80), nullable=True),
        sa.Column("village_pin_code_status", sa.String(length=80), nullable=True),
        sa.Column("source_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("match_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="AUTO_CANDIDATE"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("promotion_status", sa.String(length=40), nullable=False, server_default="NOT_PROMOTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index(
        "ix_geography_village_demographic_profiles_village_id",
        "geography_village_demographic_profiles",
        ["village_id"],
    )
    op.create_index(
        "ix_geography_village_demographic_profiles_source",
        "geography_village_demographic_profiles",
        ["source_system", "source_version"],
    )
    op.create_index(
        "ix_geography_village_demographic_profiles_source_vlcode",
        "geography_village_demographic_profiles",
        ["source_vlcode"],
    )
    op.create_index(
        "ix_geography_village_demographic_profiles_review",
        "geography_village_demographic_profiles",
        ["review_status", "promotion_status", "is_active"],
    )
    op.create_index(
        "uq_geography_village_demographic_profiles_source_feature",
        "geography_village_demographic_profiles",
        ["source_system", "source_version", "source_feature_id"],
        unique=True,
        postgresql_where=sa.text("source_feature_id is not null"),
    )
    op.create_index(
        "uq_geography_village_demographic_profiles_active_promoted",
        "geography_village_demographic_profiles",
        ["village_id", "source_system", "source_version"],
        unique=True,
        postgresql_where=sa.text("is_active = true and promotion_status = 'PROMOTED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_geography_village_demographic_profiles_active_promoted", table_name="geography_village_demographic_profiles")
    op.drop_index("uq_geography_village_demographic_profiles_source_feature", table_name="geography_village_demographic_profiles")
    op.drop_index("ix_geography_village_demographic_profiles_review", table_name="geography_village_demographic_profiles")
    op.drop_index("ix_geography_village_demographic_profiles_source_vlcode", table_name="geography_village_demographic_profiles")
    op.drop_index("ix_geography_village_demographic_profiles_source", table_name="geography_village_demographic_profiles")
    op.drop_index("ix_geography_village_demographic_profiles_village_id", table_name="geography_village_demographic_profiles")
    op.drop_table("geography_village_demographic_profiles")
