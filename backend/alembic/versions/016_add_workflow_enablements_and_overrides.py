"""Add workflow enablements and overrides.

Revision ID: 016
Revises: 015
Create Date: 2026-07-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), server_default="v1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "workflow_template_enablements",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("display_label", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        *audit_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["workflow_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "project_id", "template_id", name="uq_workflow_template_enablement_scope"),
    )
    op.create_index("idx_workflow_template_enablement_scope", "workflow_template_enablements", ["tenant_id", "project_id"])
    op.create_index("idx_workflow_template_enablement_template", "workflow_template_enablements", ["template_id"])
    op.create_index("idx_workflow_template_enablement_enabled", "workflow_template_enablements", ["enabled"])

    op.create_table(
        "workflow_template_overrides",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_code", sa.String(length=220), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("override_payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("reason", sa.Text(), nullable=True),
        *audit_columns(),
        sa.CheckConstraint("target_type IN ('STAGE', 'RECOMMENDATION')", name="ck_workflow_template_override_target_type"),
        sa.CheckConstraint("operation IN ('HIDE', 'RENAME', 'CHANGE_DURATION', 'CHANGE_OFFSET', 'CHANGE_QUANTITY')", name="ck_workflow_template_override_operation"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["workflow_template_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workflow_template_override_scope", "workflow_template_overrides", ["tenant_id", "project_id"])
    op.create_index("idx_workflow_template_override_version", "workflow_template_overrides", ["template_version_id"])
    op.create_index("idx_workflow_template_override_target", "workflow_template_overrides", ["target_type", "target_code"])


def downgrade() -> None:
    op.drop_index("idx_workflow_template_override_target", table_name="workflow_template_overrides")
    op.drop_index("idx_workflow_template_override_version", table_name="workflow_template_overrides")
    op.drop_index("idx_workflow_template_override_scope", table_name="workflow_template_overrides")
    op.drop_table("workflow_template_overrides")
    op.drop_index("idx_workflow_template_enablement_enabled", table_name="workflow_template_enablements")
    op.drop_index("idx_workflow_template_enablement_template", table_name="workflow_template_enablements")
    op.drop_index("idx_workflow_template_enablement_scope", table_name="workflow_template_enablements")
    op.drop_table("workflow_template_enablements")
