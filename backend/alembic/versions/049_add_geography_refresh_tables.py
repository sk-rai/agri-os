"""Add modular geography refresh and postal link tables.

Revision ID: 049
Revises: 048
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All-India LGD subdistrict/village codes are not globally unique.
    # Scope compatibility-table uniqueness to the parent hierarchy before loading pan-India data.
    op.drop_constraint("geography_blocks_lgd_code_key", "geography_blocks", type_="unique")
    op.drop_constraint("geography_villages_lgd_code_key", "geography_villages", type_="unique")
    op.create_unique_constraint("uq_geography_blocks_district_lgd", "geography_blocks", ["district_id", "lgd_code"])
    op.create_unique_constraint("uq_geography_villages_block_lgd", "geography_villages", ["block_id", "lgd_code"])

    op.create_table(
        "geography_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_resource_id", sa.String(length=120), nullable=True),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=255), nullable=True),
        sa.Column("raw_manifest_path", sa.Text(), nullable=True),
        sa.Column("validation_report_path", sa.Text(), nullable=True),
        sa.Column("refresh_mode", sa.String(length=40), nullable=False, server_default="INITIAL_FULL_LOAD"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("snapshot_status", sa.String(length=60), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_id", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("row_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checksums", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("diff_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("idx_geography_import_batches_source", "geography_import_batches", ["source_system", "source_resource_id"])
    op.create_index("idx_geography_import_batches_status", "geography_import_batches", ["status", "refresh_mode"])

    op.create_table(
        "geography_postal_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_import_batches.id"), nullable=True),
        sa.Column("pin_code", sa.String(length=6), nullable=False),
        sa.Column("office_name", sa.String(length=180), nullable=False),
        sa.Column("office_type", sa.String(length=40), nullable=True),
        sa.Column("delivery_status", sa.String(length=40), nullable=True),
        sa.Column("circle_name", sa.String(length=120), nullable=True),
        sa.Column("region_name", sa.String(length=120), nullable=True),
        sa.Column("division_name", sa.String(length=120), nullable=True),
        sa.Column("postal_district_name", sa.String(length=120), nullable=True),
        sa.Column("postal_state_name", sa.String(length=120), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("source_system", sa.String(length=80), nullable=False, server_default="OGD_ALL_INDIA_PINCODE_DIRECTORY"),
        sa.Column("source_row_hash", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("pin_code ~ '^[1-9][0-9]{5}$'", name="ck_geography_postal_references_pin"),
    )
    op.create_index("idx_geography_postal_references_pin", "geography_postal_references", ["pin_code"])
    op.create_index("idx_geography_postal_references_state", "geography_postal_references", ["postal_state_name"])
    op.create_unique_constraint(
        "uq_geography_postal_references_pin_office",
        "geography_postal_references",
        ["pin_code", "office_name", "office_type", "postal_state_name", "postal_district_name"],
    )

    op.create_table(
        "geography_village_pin_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_import_batches.id"), nullable=True),
        sa.Column("geography_village_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=True),
        sa.Column("pin_code", sa.String(length=6), nullable=False),
        sa.Column("state_lgd_code", sa.String(length=20), nullable=False),
        sa.Column("state_name", sa.String(length=120), nullable=True),
        sa.Column("district_lgd_code", sa.String(length=20), nullable=False),
        sa.Column("district_name", sa.String(length=120), nullable=True),
        sa.Column("subdistrict_lgd_code", sa.String(length=20), nullable=False),
        sa.Column("subdistrict_name", sa.String(length=120), nullable=True),
        sa.Column("village_lgd_code", sa.String(length=30), nullable=False),
        sa.Column("village_name", sa.String(length=180), nullable=True),
        sa.Column("source_system", sa.String(length=80), nullable=False, server_default="OGD_LGD_VILLAGES_PIN_CODES"),
        sa.Column("source_row_hash", sa.String(length=64), nullable=True),
        sa.Column("match_status", sa.String(length=40), nullable=False, server_default="UNMATCHED"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("pin_code ~ '^[1-9][0-9]{5}$'", name="ck_geography_village_pin_links_pin"),
    )
    op.create_index("idx_geography_village_pin_links_pin", "geography_village_pin_links", ["pin_code"])
    op.create_index("idx_geography_village_pin_links_village_id", "geography_village_pin_links", ["geography_village_id"])
    op.create_index("idx_geography_village_pin_links_lgd_context", "geography_village_pin_links", ["state_lgd_code", "district_lgd_code", "subdistrict_lgd_code", "village_lgd_code"])
    op.create_unique_constraint(
        "uq_geography_village_pin_links_context_pin",
        "geography_village_pin_links",
        ["state_lgd_code", "district_lgd_code", "subdistrict_lgd_code", "village_lgd_code", "pin_code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_geography_village_pin_links_context_pin", "geography_village_pin_links", type_="unique")
    op.drop_index("idx_geography_village_pin_links_lgd_context", table_name="geography_village_pin_links")
    op.drop_index("idx_geography_village_pin_links_village_id", table_name="geography_village_pin_links")
    op.drop_index("idx_geography_village_pin_links_pin", table_name="geography_village_pin_links")
    op.drop_table("geography_village_pin_links")

    op.drop_constraint("uq_geography_postal_references_pin_office", "geography_postal_references", type_="unique")
    op.drop_index("idx_geography_postal_references_state", table_name="geography_postal_references")
    op.drop_index("idx_geography_postal_references_pin", table_name="geography_postal_references")
    op.drop_table("geography_postal_references")

    op.drop_index("idx_geography_import_batches_status", table_name="geography_import_batches")
    op.drop_index("idx_geography_import_batches_source", table_name="geography_import_batches")
    op.drop_table("geography_import_batches")

    op.drop_constraint("uq_geography_villages_block_lgd", "geography_villages", type_="unique")
    op.drop_constraint("uq_geography_blocks_district_lgd", "geography_blocks", type_="unique")
    op.create_unique_constraint("geography_villages_lgd_code_key", "geography_villages", ["lgd_code"])
    op.create_unique_constraint("geography_blocks_lgd_code_key", "geography_blocks", ["lgd_code"])
