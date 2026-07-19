"""add company discovery candidates

Revision ID: 047
Revises: 046
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_discovery_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("candidate_name", sa.String(length=250), nullable=False),
        sa.Column("normalized_name", sa.String(length=250), nullable=True),
        sa.Column("company_type", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discovered_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("operating_geography", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("crop_focus", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.DECIMAL(5, 4), nullable=True),
        sa.Column("duplicate_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("matched_company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id"), nullable=True),
        sa.Column("review_status", sa.String(length=50), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.create_index("idx_company_discovery_candidate_tenant_status", "company_discovery_candidates", ["tenant_id", "review_status"])
    op.create_index("idx_company_discovery_candidate_source", "company_discovery_candidates", ["source"])
    op.create_index("idx_company_discovery_candidate_normalized_name", "company_discovery_candidates", ["normalized_name"])
    op.create_index("idx_company_discovery_candidate_matched_tenant", "company_discovery_candidates", ["matched_tenant_id"])


def downgrade():
    op.drop_index("idx_company_discovery_candidate_matched_tenant", table_name="company_discovery_candidates")
    op.drop_index("idx_company_discovery_candidate_normalized_name", table_name="company_discovery_candidates")
    op.drop_index("idx_company_discovery_candidate_source", table_name="company_discovery_candidates")
    op.drop_index("idx_company_discovery_candidate_tenant_status", table_name="company_discovery_candidates")
    op.drop_table("company_discovery_candidates")
