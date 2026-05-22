"""Create soil, season, crop, and input master data tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- soil_types ---
    op.create_table(
        "soil_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("characteristics", JSONB, server_default="{}"),
        sa.Column("suitable_crops", JSONB, server_default="[]"),
        sa.Column("ph_range_min", sa.String(10)),
        sa.Column("ph_range_max", sa.String(10)),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_soil_types_code", "soil_types", ["code"])

    # --- seasons ---
    op.create_table(
        "seasons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("start_month", sa.Integer, nullable=False),
        sa.Column("end_month", sa.Integer, nullable=False),
        sa.Column("sowing_window_start", sa.Integer),
        sa.Column("sowing_window_end", sa.Integer),
        sa.Column("harvest_window_start", sa.Integer),
        sa.Column("harvest_window_end", sa.Integer),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_seasons_code", "seasons", ["code"])

    # --- crop_categories ---
    op.create_table(
        "crop_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_crop_categories_code", "crop_categories", ["code"])

    # --- crops ---
    op.create_table(
        "crops",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), unique=True, nullable=False),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crop_categories.id"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("scientific_name", sa.String(150)),
        sa.Column("description", sa.Text),
        sa.Column("typical_duration_days", sa.Integer),
        sa.Column("suitable_seasons", ARRAY(sa.String), server_default="{}"),
        sa.Column("suitable_soil_types", ARRAY(sa.String), server_default="{}"),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_crops_code", "crops", ["code"])
    op.create_index("idx_crop_category", "crops", ["category_id"])

    # --- crop_varieties ---
    op.create_table(
        "crop_varieties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "crop_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crops.id"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(150), nullable=False),
        sa.Column("developer", sa.String(200)),
        sa.Column("release_year", sa.Integer),
        sa.Column("duration_days", sa.Integer),
        sa.Column("characteristics", JSONB, server_default="{}"),
        sa.Column(
            "recommended_states", ARRAY(sa.String), server_default="{}"
        ),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_crop_varieties_code", "crop_varieties", ["code"])
    op.create_index("idx_variety_crop", "crop_varieties", ["crop_id"])

    # --- crop_lifecycle_templates ---
    op.create_table(
        "crop_lifecycle_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "crop_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crops.id"),
            nullable=False,
        ),
        sa.Column("season_code", sa.String(20), nullable=False),
        sa.Column("canonical_name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("total_duration_days", sa.Integer),
        sa.Column("stages", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index(
        "ix_crop_lifecycle_templates_code",
        "crop_lifecycle_templates",
        ["code"],
    )
    op.create_index(
        "idx_lifecycle_crop", "crop_lifecycle_templates", ["crop_id"]
    )
    op.create_index(
        "idx_lifecycle_season", "crop_lifecycle_templates", ["season_code"]
    )

    # --- input_categories ---
    op.create_table(
        "input_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_input_categories_code", "input_categories", ["code"])

    # --- manufacturers ---
    op.create_table(
        "manufacturers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("short_name", sa.String(50)),
        sa.Column("country", sa.String(50), server_default="India"),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index("ix_manufacturers_code", "manufacturers", ["code"])

    # --- agricultural_inputs ---
    op.create_table(
        "agricultural_inputs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("input_categories.id"),
            nullable=False,
        ),
        sa.Column(
            "manufacturer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("manufacturers.id"),
        ),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("brand_name", sa.String(200)),
        sa.Column("composition", sa.String(200)),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("standard_weight", sa.DECIMAL(10, 2)),
        sa.Column(
            "applicable_crops", ARRAY(sa.String), server_default="{}"
        ),
        sa.Column("application_method", sa.Text),
        sa.Column("safety_instructions", sa.Text),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.String(10), server_default="v1.0", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_index(
        "ix_agricultural_inputs_code", "agricultural_inputs", ["code"]
    )
    op.create_index(
        "idx_input_category", "agricultural_inputs", ["category_id"]
    )
    op.create_index(
        "idx_input_manufacturer", "agricultural_inputs", ["manufacturer_id"]
    )
    op.create_index(
        "idx_input_search",
        "agricultural_inputs",
        ["canonical_name"],
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_table("agricultural_inputs")
    op.drop_table("manufacturers")
    op.drop_table("input_categories")
    op.drop_table("crop_lifecycle_templates")
    op.drop_table("crop_varieties")
    op.drop_table("crops")
    op.drop_table("crop_categories")
    op.drop_table("seasons")
    op.drop_table("soil_types")
