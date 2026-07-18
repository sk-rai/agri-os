"""add agent profiles

Revision ID: 041
Revises: 040
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farmers.id"), nullable=True),
        sa.Column("agent_code", sa.String(length=50), nullable=True),
        sa.Column("role_type", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=True),
        sa.Column("mobile_number", sa.String(length=15), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("skills", postgresql.JSONB(), nullable=True),
        sa.Column("languages", postgresql.JSONB(), nullable=True),
        sa.Column("territory_scope", postgresql.JSONB(), nullable=True),
        sa.Column("availability", postgresql.JSONB(), nullable=True),
        sa.Column("certification", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("idx_agent_profiles_tenant_user", "agent_profiles", ["tenant_id", "user_id"], unique=True)
    op.create_index("idx_agent_profiles_tenant_role", "agent_profiles", ["tenant_id", "role_type"])
    op.create_index("idx_agent_profiles_tenant_status", "agent_profiles", ["tenant_id", "status"])
    op.create_index("ix_agent_profiles_agent_code", "agent_profiles", ["agent_code"])
    op.create_index("ix_agent_profiles_farmer_id", "agent_profiles", ["farmer_id"])
    op.create_index("ix_agent_profiles_mobile_number", "agent_profiles", ["mobile_number"])
    op.create_index("ix_agent_profiles_tenant_id", "agent_profiles", ["tenant_id"])
    op.create_index("ix_agent_profiles_user_id", "agent_profiles", ["user_id"])


def downgrade():
    op.drop_index("ix_agent_profiles_user_id", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_tenant_id", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_mobile_number", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_farmer_id", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_agent_code", table_name="agent_profiles")
    op.drop_index("idx_agent_profiles_tenant_status", table_name="agent_profiles")
    op.drop_index("idx_agent_profiles_tenant_role", table_name="agent_profiles")
    op.drop_index("idx_agent_profiles_tenant_user", table_name="agent_profiles")
    op.drop_table("agent_profiles")
