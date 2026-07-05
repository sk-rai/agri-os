"""Add versioned workflow template tables.

Revision ID: 015
Revises: 014
Create Date: 2026-07-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "015"
down_revision: Union[str, None] = "014"
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
        "workflow_templates",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("crop_id", UUID(as_uuid=True), nullable=False),
        sa.Column("crop_code", sa.String(length=30), nullable=False),
        sa.Column("season_code", sa.String(length=20), nullable=False),
        sa.Column("propagation_type_code", sa.String(length=50), nullable=True),
        sa.Column("canonical_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lifecycle_template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        *audit_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["lifecycle_template_id"], ["crop_lifecycle_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_workflow_template_tenant_code"),
    )
    op.create_index("idx_workflow_template_crop_season", "workflow_templates", ["crop_code", "season_code"])
    op.create_index("idx_workflow_template_tenant", "workflow_templates", ["tenant_id"])
    op.create_index("idx_workflow_template_default", "workflow_templates", ["crop_code", "season_code", "is_default"])

    op.create_table(
        "workflow_template_versions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("total_duration_days", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.String(length=30), nullable=False, server_default="1.0.0"),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", UUID(as_uuid=True), nullable=True),
        *audit_columns(),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_workflow_template_version_status"),
        sa.ForeignKeyConstraint(["template_id"], ["workflow_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version_number", name="uq_workflow_template_version"),
    )
    op.create_index("idx_workflow_template_version_template", "workflow_template_versions", ["template_id"])
    op.create_index("idx_workflow_template_version_status", "workflow_template_versions", ["status"])

    op.create_table(
        "workflow_template_stages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("template_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("stage_code", sa.String(length=50), nullable=False),
        sa.Column("stage_name", JSONB(), nullable=False, server_default="{}"),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_type", sa.String(length=50), nullable=True),
        sa.Column("phase", sa.String(length=50), nullable=True),
        sa.Column("bbch_range", JSONB(), nullable=True),
        sa.Column("propagation_step", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", JSONB(), nullable=True),
        sa.Column("farmer_actions", JSONB(), nullable=True, server_default="[]"),
        sa.Column("typical_inputs", JSONB(), nullable=True, server_default="[]"),
        sa.Column("key_observations", JSONB(), nullable=True, server_default="[]"),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("color", sa.String(length=30), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        *audit_columns(),
        sa.ForeignKeyConstraint(["template_version_id"], ["workflow_template_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_version_id", "stage_code", name="uq_workflow_template_stage_code"),
        sa.UniqueConstraint("template_version_id", "stage_order", name="uq_workflow_template_stage_order"),
    )
    op.create_index("idx_workflow_template_stage_version", "workflow_template_stages", ["template_version_id"])
    op.create_index("idx_workflow_template_stage_order", "workflow_template_stages", ["template_version_id", "stage_order"])

    op.create_table(
        "workflow_template_recommendations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("template_stage_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("day_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activity_type", sa.String(length=30), nullable=False),
        sa.Column("input_code", sa.String(length=50), nullable=True),
        sa.Column("input_name", sa.String(length=200), nullable=False),
        sa.Column("typical_quantity", sa.String(length=120), nullable=True),
        sa.Column("typical_cost_per_acre", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        *audit_columns(),
        sa.ForeignKeyConstraint(["template_stage_id"], ["workflow_template_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workflow_template_rec_stage", "workflow_template_recommendations", ["template_stage_id"])
    op.create_index("idx_workflow_template_rec_activity", "workflow_template_recommendations", ["activity_type"])


def downgrade() -> None:
    op.drop_index("idx_workflow_template_rec_activity", table_name="workflow_template_recommendations")
    op.drop_index("idx_workflow_template_rec_stage", table_name="workflow_template_recommendations")
    op.drop_table("workflow_template_recommendations")
    op.drop_index("idx_workflow_template_stage_order", table_name="workflow_template_stages")
    op.drop_index("idx_workflow_template_stage_version", table_name="workflow_template_stages")
    op.drop_table("workflow_template_stages")
    op.drop_index("idx_workflow_template_version_status", table_name="workflow_template_versions")
    op.drop_index("idx_workflow_template_version_template", table_name="workflow_template_versions")
    op.drop_table("workflow_template_versions")
    op.drop_index("idx_workflow_template_default", table_name="workflow_templates")
    op.drop_index("idx_workflow_template_tenant", table_name="workflow_templates")
    op.drop_index("idx_workflow_template_crop_season", table_name="workflow_templates")
    op.drop_table("workflow_templates")
