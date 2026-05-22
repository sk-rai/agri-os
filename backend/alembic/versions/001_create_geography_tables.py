"""Create geography tables

Revision ID: 001
Revises: None
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure extensions exist
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- geography_states ---
    op.create_table(
        "geography_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lgd_code", sa.String(20), unique=True, nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("census_name", sa.String(100)),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_geography_states_lgd_code", "geography_states", ["lgd_code"])

    # --- geography_districts ---
    op.create_table(
        "geography_districts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lgd_code", sa.String(20), unique=True, nullable=False),
        sa.Column(
            "state_id",
            UUID(as_uuid=True),
            sa.ForeignKey("geography_states.id"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("census_name", sa.String(100)),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_geography_districts_lgd_code", "geography_districts", ["lgd_code"])
    op.create_index("idx_district_state", "geography_districts", ["state_id"])

    # --- geography_blocks ---
    op.create_table(
        "geography_blocks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lgd_code", sa.String(20), unique=True, nullable=False),
        sa.Column(
            "district_id",
            UUID(as_uuid=True),
            sa.ForeignKey("geography_districts.id"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_geography_blocks_lgd_code", "geography_blocks", ["lgd_code"])
    op.create_index("idx_block_district", "geography_blocks", ["district_id"])

    # --- geography_villages ---
    op.create_table(
        "geography_villages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lgd_code", sa.String(30), unique=True, nullable=False),
        sa.Column(
            "block_id",
            UUID(as_uuid=True),
            sa.ForeignKey("geography_blocks.id"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            UUID(as_uuid=True),
            sa.ForeignKey("geography_districts.id"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(150), nullable=False),
        sa.Column("census_name", sa.String(150)),
        sa.Column("census_village_code", sa.String(20)),
        sa.Column("pin_codes", ARRAY(sa.String), server_default="{}"),
        sa.Column("latitude", sa.DECIMAL(10, 8)),
        sa.Column("longitude", sa.DECIMAL(11, 8)),
        sa.Column("aliases", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_geography_villages_lgd_code", "geography_villages", ["lgd_code"])
    op.create_index("idx_village_block", "geography_villages", ["block_id"])
    op.create_index("idx_village_district", "geography_villages", ["district_id"])
    op.create_index(
        "idx_village_pin",
        "geography_villages",
        ["pin_codes"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_village_search",
        "geography_villages",
        ["canonical_name"],
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_table("geography_villages")
    op.drop_table("geography_blocks")
    op.drop_table("geography_districts")
    op.drop_table("geography_states")
