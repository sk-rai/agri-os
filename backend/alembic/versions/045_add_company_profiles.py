"""add company profiles

Revision ID: 045
Revises: 044
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("company_type", sa.String(length=50), nullable=False, server_default="ENTERPRISE"),
        sa.Column("registration_number", sa.String(length=100), nullable=True),
        sa.Column("gstin", sa.String(length=30), nullable=True),
        sa.Column("pan", sa.String(length=20), nullable=True),
        sa.Column("website_url", sa.String(length=300), nullable=True),
        sa.Column("support_email", sa.String(length=200), nullable=True),
        sa.Column("support_phone", sa.String(length=30), nullable=True),
        sa.Column("head_office", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("operating_geography", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("crop_focus", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("service_model", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_company_profiles_tenant_id"),
    )
    op.create_index("idx_company_profile_tenant", "company_profiles", ["tenant_id"])
    op.create_index("idx_company_profile_company_type", "company_profiles", ["company_type"])


def downgrade():
    op.drop_index("idx_company_profile_company_type", table_name="company_profiles")
    op.drop_index("idx_company_profile_tenant", table_name="company_profiles")
    op.drop_table("company_profiles")
