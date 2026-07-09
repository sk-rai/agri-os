"""Add tenant user and project access audit ledger.

Revision ID: 019
Revises: 018
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_user_access_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("before_payload", postgresql.JSONB()),
        sa.Column("after_payload", postgresql.JSONB()),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tenant_user_access_audit_events_tenant_id", "tenant_user_access_audit_events", ["tenant_id"])
    op.create_index("ix_tenant_user_access_audit_events_target_user_id", "tenant_user_access_audit_events", ["target_user_id"])
    op.create_index("ix_tenant_user_access_audit_events_actor_id", "tenant_user_access_audit_events", ["actor_id"])
    op.create_index("ix_tenant_user_access_audit_events_project_id", "tenant_user_access_audit_events", ["project_id"])
    op.create_index("ix_tenant_user_access_audit_events_action", "tenant_user_access_audit_events", ["action"])
    op.create_index(
        "idx_tenant_user_access_audit_tenant_created",
        "tenant_user_access_audit_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "idx_tenant_user_access_audit_target_created",
        "tenant_user_access_audit_events",
        ["target_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("tenant_user_access_audit_events")
