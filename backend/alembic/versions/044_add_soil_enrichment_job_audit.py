"""add soil enrichment job audit

Revision ID: 044
Revises: 043
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "soil_enrichment_job_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=True),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parcels.id"), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.create_index("idx_soil_enrichment_job_audit_tenant", "soil_enrichment_job_audit_events", ["tenant_id"])
    op.create_index("idx_soil_enrichment_job_audit_farmer", "soil_enrichment_job_audit_events", ["farmer_id"])
    op.create_index("idx_soil_enrichment_job_audit_parcel", "soil_enrichment_job_audit_events", ["parcel_id"])
    op.create_index("idx_soil_enrichment_job_audit_project", "soil_enrichment_job_audit_events", ["project_id"])
    op.create_index("idx_soil_enrichment_job_audit_status", "soil_enrichment_job_audit_events", ["status"])
    op.create_index("idx_soil_enrichment_job_audit_job_type", "soil_enrichment_job_audit_events", ["job_type"])


def downgrade():
    op.drop_index("idx_soil_enrichment_job_audit_job_type", table_name="soil_enrichment_job_audit_events")
    op.drop_index("idx_soil_enrichment_job_audit_status", table_name="soil_enrichment_job_audit_events")
    op.drop_index("idx_soil_enrichment_job_audit_project", table_name="soil_enrichment_job_audit_events")
    op.drop_index("idx_soil_enrichment_job_audit_parcel", table_name="soil_enrichment_job_audit_events")
    op.drop_index("idx_soil_enrichment_job_audit_farmer", table_name="soil_enrichment_job_audit_events")
    op.drop_index("idx_soil_enrichment_job_audit_tenant", table_name="soil_enrichment_job_audit_events")
    op.drop_table("soil_enrichment_job_audit_events")
