"""Add NWDP boundary review staging tables.

Revision ID: 054
Revises: 053
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    ]


def upgrade() -> None:
    op.create_table(
        "geography_boundary_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_dataset", sa.String(length=160), nullable=False),
        sa.Column("source_producer_agency", sa.String(length=160), nullable=True),
        sa.Column("state_or_ut", sa.String(length=120), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False),
        sa.Column("source_resource_url", sa.Text(), nullable=True),
        sa.Column("source_download_url", sa.Text(), nullable=True),
        sa.Column("source_file_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("source_crs", sa.String(length=120), nullable=True),
        sa.Column("source_epsg", sa.String(length=30), nullable=True),
        sa.Column("target_crs", sa.String(length=60), nullable=False, server_default="EPSG:4326"),
        sa.Column("manifest_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("geometry_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("crosswalk_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="MANUAL_REVIEW"),
        sa.Column("reviewer_id", sa.String(length=80), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
    )
    op.create_index("idx_geography_boundary_import_batches_source", "geography_boundary_import_batches", ["source_system", "state_or_ut", "source_format"])
    op.create_index("idx_geography_boundary_import_batches_status", "geography_boundary_import_batches", ["status", "review_status"])

    op.create_table(
        "geography_boundary_source_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_import_batches.id"), nullable=False),
        sa.Column("source_feature_index", sa.Integer(), nullable=False),
        sa.Column("source_feature_hash", sa.String(length=64), nullable=True),
        sa.Column("source_stcode", sa.String(length=20), nullable=True),
        sa.Column("source_dtcode", sa.String(length=20), nullable=True),
        sa.Column("source_sdcode", sa.String(length=20), nullable=True),
        sa.Column("source_bkcode", sa.String(length=20), nullable=True),
        sa.Column("source_vlcode", sa.String(length=30), nullable=True),
        sa.Column("source_state_name", sa.String(length=120), nullable=True),
        sa.Column("source_district_name", sa.String(length=160), nullable=True),
        sa.Column("source_subdistrict_name", sa.String(length=160), nullable=True),
        sa.Column("source_block_name", sa.String(length=160), nullable=True),
        sa.Column("source_village_name", sa.String(length=220), nullable=True),
        sa.Column("source_agency", sa.String(length=160), nullable=True),
        sa.Column("feature_category", sa.String(length=60), nullable=False, server_default="VILLAGE_BOUNDARY"),
        sa.Column("source_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_geometry_hash", sa.String(length=64), nullable=True),
        sa.Column("source_bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transformed_bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transformed_centroid", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("geometry_validation_status", sa.String(length=40), nullable=False, server_default="NOT_VALIDATED"),
        sa.Column("eligible_for_runtime_after_promotion", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("import_batch_id", "source_feature_index", name="uq_geography_boundary_source_feature_batch_index"),
    )
    op.create_index("idx_geography_boundary_source_features_batch", "geography_boundary_source_features", ["import_batch_id"])
    op.create_index("idx_geography_boundary_source_features_codes", "geography_boundary_source_features", ["source_dtcode", "source_sdcode", "source_bkcode", "source_vlcode"])
    op.create_index("idx_geography_boundary_source_features_review", "geography_boundary_source_features", ["feature_category", "geometry_validation_status"])

    op.create_table(
        "geography_boundary_crosswalk_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_import_batches.id"), nullable=False),
        sa.Column("source_feature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_source_features.id"), nullable=False),
        sa.Column("source_feature_index", sa.Integer(), nullable=False),
        sa.Column("candidate_bucket", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.String(length=80), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="MANUAL_REVIEW"),
        sa.Column("proposed_scope", sa.String(length=60), nullable=False),
        sa.Column("proposed_state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_states.id"), nullable=True),
        sa.Column("proposed_district_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_districts.id"), nullable=True),
        sa.Column("proposed_block_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_blocks.id"), nullable=True),
        sa.Column("proposed_village_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=True),
        sa.Column("proposed_state_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("proposed_district_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("proposed_block_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("proposed_village_lgd_code", sa.String(length=30), nullable=True),
        sa.Column("source_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("match_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reviewer_decision", sa.String(length=60), nullable=True),
        sa.Column("reviewer_id", sa.String(length=80), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("promotion_status", sa.String(length=40), nullable=False, server_default="NOT_PROMOTED"),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(length=80), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("import_batch_id", "source_feature_index", name="uq_geography_boundary_candidate_batch_index"),
        sa.CheckConstraint("is_active = false", name="ck_geography_boundary_candidates_inactive_by_default"),
    )
    op.create_index("idx_geography_boundary_candidates_batch", "geography_boundary_crosswalk_candidates", ["import_batch_id"])
    op.create_index("idx_geography_boundary_candidates_feature", "geography_boundary_crosswalk_candidates", ["source_feature_id"])
    op.create_index("idx_geography_boundary_candidates_bucket", "geography_boundary_crosswalk_candidates", ["candidate_bucket", "review_status"])
    op.create_index("idx_geography_boundary_candidates_scope", "geography_boundary_crosswalk_candidates", ["proposed_scope", "promotion_status"])
    op.create_index("idx_geography_boundary_candidates_village", "geography_boundary_crosswalk_candidates", ["proposed_village_id"])


def downgrade() -> None:
    op.drop_index("idx_geography_boundary_candidates_village", table_name="geography_boundary_crosswalk_candidates")
    op.drop_index("idx_geography_boundary_candidates_scope", table_name="geography_boundary_crosswalk_candidates")
    op.drop_index("idx_geography_boundary_candidates_bucket", table_name="geography_boundary_crosswalk_candidates")
    op.drop_index("idx_geography_boundary_candidates_feature", table_name="geography_boundary_crosswalk_candidates")
    op.drop_index("idx_geography_boundary_candidates_batch", table_name="geography_boundary_crosswalk_candidates")
    op.drop_table("geography_boundary_crosswalk_candidates")

    op.drop_index("idx_geography_boundary_source_features_review", table_name="geography_boundary_source_features")
    op.drop_index("idx_geography_boundary_source_features_codes", table_name="geography_boundary_source_features")
    op.drop_index("idx_geography_boundary_source_features_batch", table_name="geography_boundary_source_features")
    op.drop_table("geography_boundary_source_features")

    op.drop_index("idx_geography_boundary_import_batches_status", table_name="geography_boundary_import_batches")
    op.drop_index("idx_geography_boundary_import_batches_source", table_name="geography_boundary_import_batches")
    op.drop_table("geography_boundary_import_batches")
