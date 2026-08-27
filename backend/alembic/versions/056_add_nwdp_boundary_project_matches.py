"""Add NWDP boundary project match table.

Revision ID: 056
Revises: 055
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "056"
down_revision = "055"
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
        "geography_boundary_project_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("village_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("geography_villages.id"), nullable=False),
        sa.Column(
            "boundary_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geography_boundary_crosswalk_candidates.id"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("match_source", sa.String(length=60), nullable=False, server_default="ADMIN_PROJECT_MATCHING"),
        sa.Column("match_status", sa.String(length=40), nullable=False, server_default="PLANNED"),
        sa.Column("applied_by", sa.String(length=80), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_by", sa.String(length=80), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_token", sa.String(length=80), nullable=False),
        sa.Column("dry_run_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("apply_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rollback_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_audit_columns(),
        sa.CheckConstraint(
            "match_status in ('PLANNED', 'APPLIED', 'ROLLED_BACK', 'FAILED')",
            name="ck_geography_boundary_project_matches_status",
        ),
        sa.CheckConstraint(
            "is_active = false or match_status = 'APPLIED'",
            name="ck_geography_boundary_project_matches_active_status",
        ),
    )
    op.create_index(
        "idx_geography_boundary_project_matches_project",
        "geography_boundary_project_matches",
        ["project_id", "is_active"],
    )
    op.create_index(
        "idx_geography_boundary_project_matches_village",
        "geography_boundary_project_matches",
        ["village_id", "source_system"],
    )
    op.create_index(
        "idx_geography_boundary_project_matches_candidate",
        "geography_boundary_project_matches",
        ["boundary_candidate_id"],
    )
    op.create_index(
        "idx_geography_boundary_project_matches_rollback",
        "geography_boundary_project_matches",
        ["rollback_token", "match_status"],
    )
    op.create_index(
        "uq_geography_boundary_project_matches_one_active",
        "geography_boundary_project_matches",
        ["project_id", "village_id", "source_system"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_geography_boundary_project_matches_one_active", table_name="geography_boundary_project_matches")
    op.drop_index("idx_geography_boundary_project_matches_rollback", table_name="geography_boundary_project_matches")
    op.drop_index("idx_geography_boundary_project_matches_candidate", table_name="geography_boundary_project_matches")
    op.drop_index("idx_geography_boundary_project_matches_village", table_name="geography_boundary_project_matches")
    op.drop_index("idx_geography_boundary_project_matches_project", table_name="geography_boundary_project_matches")
    op.drop_table("geography_boundary_project_matches")
