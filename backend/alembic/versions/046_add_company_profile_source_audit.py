"""add company profile source audit

Revision ID: 046
Revises: 045
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("company_profiles", sa.Column("profile_source", sa.String(length=50), nullable=False, server_default="MANUAL"))
    op.add_column("company_profiles", sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="UNVERIFIED"))
    op.add_column("company_profiles", sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "company_profile_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id"), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False, server_default="UPSERT_COMPANY_PROFILE"),
        sa.Column("patched_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("before_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_company_profile_audit_tenant_created", "company_profile_audit_events", ["tenant_id", "created_at"])
    op.create_index("idx_company_profile_audit_profile_created", "company_profile_audit_events", ["company_profile_id", "created_at"])
    op.create_index("idx_company_profile_audit_actor", "company_profile_audit_events", ["actor_id"])
    op.create_index("idx_company_profile_audit_action", "company_profile_audit_events", ["action"])


def downgrade():
    op.drop_index("idx_company_profile_audit_action", table_name="company_profile_audit_events")
    op.drop_index("idx_company_profile_audit_actor", table_name="company_profile_audit_events")
    op.drop_index("idx_company_profile_audit_profile_created", table_name="company_profile_audit_events")
    op.drop_index("idx_company_profile_audit_tenant_created", table_name="company_profile_audit_events")
    op.drop_table("company_profile_audit_events")
    op.drop_column("company_profiles", "source_references")
    op.drop_column("company_profiles", "verification_status")
    op.drop_column("company_profiles", "profile_source")
