"""add project app config audit events

Revision ID: 032
Revises: 031
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_app_config_audit_events",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False, server_default="UPDATE_PROJECT_APP_CONFIG"),
        sa.Column("patched_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("before_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_patch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_project_app_config_audit_tenant_created", "project_app_config_audit_events", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_project_app_config_audit_project_created", "project_app_config_audit_events", ["project_id", "created_at"], unique=False)
    op.create_index("idx_project_app_config_audit_actor", "project_app_config_audit_events", ["actor_id"], unique=False)
    op.create_index("idx_project_app_config_audit_action", "project_app_config_audit_events", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_project_app_config_audit_action", table_name="project_app_config_audit_events")
    op.drop_index("idx_project_app_config_audit_actor", table_name="project_app_config_audit_events")
    op.drop_index("idx_project_app_config_audit_project_created", table_name="project_app_config_audit_events")
    op.drop_index("idx_project_app_config_audit_tenant_created", table_name="project_app_config_audit_events")
    op.drop_table("project_app_config_audit_events")
