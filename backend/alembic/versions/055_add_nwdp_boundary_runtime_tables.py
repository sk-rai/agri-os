"""Add NWDP boundary runtime tables.

Revision ID: 055
Revises: 054
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "055"
down_revision = "054"
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
        "geography_boundary_runtime_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_dataset", sa.String(length=160), nullable=False),
        sa.Column("state_or_ut", sa.String(length=120), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False),
        sa.Column("source_file_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_crs", sa.String(length=120), nullable=True),
        sa.Column("source_epsg", sa.String(length=30), nullable=True),
        sa.Column("runtime_crs", sa.String(length=60), nullable=False, server_default="EPSG:4326"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("activation_status", sa.String(length=40), nullable=False, server_default="INACTIVE"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=True),
        sa.Column("review_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("guardrail_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.CheckConstraint("activation_status in ('INACTIVE', 'ACTIVE', 'SUPERSEDED', 'RETIRED')", name="ck_geography_boundary_runtime_sets_activation_status"),
        sa.CheckConstraint("is_active = false or activation_status = 'ACTIVE'", name="ck_geography_boundary_runtime_sets_active_status"),
    )
    op.create_index("idx_geography_boundary_runtime_sets_source", "geography_boundary_runtime_sets", ["source_system", "state_or_ut", "source_format"])
    op.create_index("idx_geography_boundary_runtime_sets_status", "geography_boundary_runtime_sets", ["activation_status", "is_active"])
    op.create_index(
        "uq_geography_boundary_runtime_sets_one_active",
        "geography_boundary_runtime_sets",
        ["source_system", "state_or_ut", "source_format"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "geography_boundary_runtime_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runtime_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_runtime_sets.id"), nullable=False),
        sa.Column("source_feature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_source_features.id"), nullable=False),
        sa.Column("source_feature_index", sa.Integer(), nullable=False),
        sa.Column("source_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feature_category", sa.String(length=60), nullable=False, server_default="VILLAGE_BOUNDARY"),
        sa.Column("geometry_wgs84", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("centroid_wgs84", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("bbox_wgs84", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("geometry_hash", sa.String(length=64), nullable=True),
        sa.Column("geometry_validation_status", sa.String(length=40), nullable=False, server_default="NOT_VALIDATED"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.UniqueConstraint("runtime_set_id", "source_feature_id", name="uq_geography_boundary_runtime_features_set_source"),
    )
    op.create_index("idx_geography_boundary_runtime_features_set", "geography_boundary_runtime_features", ["runtime_set_id", "is_active"])
    op.create_index("idx_geography_boundary_runtime_features_source", "geography_boundary_runtime_features", ["source_feature_id"])
    op.create_index("idx_geography_boundary_runtime_features_validation", "geography_boundary_runtime_features", ["geometry_validation_status", "feature_category"])

    op.create_table(
        "geography_boundary_runtime_crosswalks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runtime_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_runtime_sets.id"), nullable=False),
        sa.Column("runtime_feature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_runtime_features.id"), nullable=False),
        sa.Column("source_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_crosswalk_candidates.id"), nullable=False),
        sa.Column("runtime_scope", sa.String(length=60), nullable=False),
        sa.Column("state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_states.id"), nullable=True),
        sa.Column("district_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_districts.id"), nullable=True),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_blocks.id"), nullable=True),
        sa.Column("village_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=True),
        sa.Column("state_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("district_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("block_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("village_lgd_code", sa.String(length=30), nullable=True),
        sa.Column("confidence", sa.String(length=80), nullable=False),
        sa.Column("reviewer_decision", sa.String(length=60), nullable=False),
        sa.Column("promotion_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.CheckConstraint("runtime_scope in ('village', 'village_review', 'district_subdistrict', 'district_review', 'reference_only')", name="ck_geography_boundary_runtime_crosswalks_scope"),
    )
    op.create_index("idx_geography_boundary_runtime_crosswalks_set", "geography_boundary_runtime_crosswalks", ["runtime_set_id", "is_active"])
    op.create_index("idx_geography_boundary_runtime_crosswalks_feature", "geography_boundary_runtime_crosswalks", ["runtime_feature_id"])
    op.create_index("idx_geography_boundary_runtime_crosswalks_candidate", "geography_boundary_runtime_crosswalks", ["source_candidate_id"])
    op.create_index("idx_geography_boundary_runtime_crosswalks_village", "geography_boundary_runtime_crosswalks", ["village_id", "runtime_scope"])

    op.create_table(
        "geography_boundary_runtime_promotion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runtime_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_runtime_sets.id"), nullable=False),
        sa.Column("source_import_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_boundary_import_batches.id"), nullable=False),
        sa.Column("promoted_by", sa.String(length=80), nullable=False),
        sa.Column("promotion_mode", sa.String(length=40), nullable=False, server_default="REVIEWED_BATCH"),
        sa.Column("promotion_status", sa.String(length=40), nullable=False, server_default="PLANNED"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_feature_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_crosswalk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dry_run_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("promotion_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("guardrail_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.CheckConstraint("promotion_status in ('PLANNED', 'DRY_RUN_VERIFIED', 'APPLIED', 'ROLLED_BACK', 'FAILED')", name="ck_geography_boundary_runtime_promotion_events_status"),
    )
    op.create_index("idx_geography_boundary_runtime_promotion_events_set", "geography_boundary_runtime_promotion_events", ["runtime_set_id"])
    op.create_index("idx_geography_boundary_runtime_promotion_events_batch", "geography_boundary_runtime_promotion_events", ["source_import_batch_id"])
    op.create_index("idx_geography_boundary_runtime_promotion_events_status", "geography_boundary_runtime_promotion_events", ["promotion_status", "promotion_mode"])

    op.create_foreign_key(
        "fk_geography_boundary_runtime_crosswalks_promotion_event",
        "geography_boundary_runtime_crosswalks",
        "geography_boundary_runtime_promotion_events",
        ["promotion_event_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_geography_boundary_runtime_crosswalks_promotion_event", "geography_boundary_runtime_crosswalks", type_="foreignkey")

    op.drop_index("idx_geography_boundary_runtime_promotion_events_status", table_name="geography_boundary_runtime_promotion_events")
    op.drop_index("idx_geography_boundary_runtime_promotion_events_batch", table_name="geography_boundary_runtime_promotion_events")
    op.drop_index("idx_geography_boundary_runtime_promotion_events_set", table_name="geography_boundary_runtime_promotion_events")
    op.drop_table("geography_boundary_runtime_promotion_events")

    op.drop_index("idx_geography_boundary_runtime_crosswalks_village", table_name="geography_boundary_runtime_crosswalks")
    op.drop_index("idx_geography_boundary_runtime_crosswalks_candidate", table_name="geography_boundary_runtime_crosswalks")
    op.drop_index("idx_geography_boundary_runtime_crosswalks_feature", table_name="geography_boundary_runtime_crosswalks")
    op.drop_index("idx_geography_boundary_runtime_crosswalks_set", table_name="geography_boundary_runtime_crosswalks")
    op.drop_table("geography_boundary_runtime_crosswalks")

    op.drop_index("idx_geography_boundary_runtime_features_validation", table_name="geography_boundary_runtime_features")
    op.drop_index("idx_geography_boundary_runtime_features_source", table_name="geography_boundary_runtime_features")
    op.drop_index("idx_geography_boundary_runtime_features_set", table_name="geography_boundary_runtime_features")
    op.drop_table("geography_boundary_runtime_features")

    op.drop_index("uq_geography_boundary_runtime_sets_one_active", table_name="geography_boundary_runtime_sets")
    op.drop_index("idx_geography_boundary_runtime_sets_status", table_name="geography_boundary_runtime_sets")
    op.drop_index("idx_geography_boundary_runtime_sets_source", table_name="geography_boundary_runtime_sets")
    op.drop_table("geography_boundary_runtime_sets")
