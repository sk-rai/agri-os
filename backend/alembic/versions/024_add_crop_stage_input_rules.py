"""Add crop-stage input compatibility and dosage rules.

Revision ID: 024
Revises: 023
Create Date: 2026-07-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def audit_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    ]


def upgrade() -> None:
    op.create_table(
        "crop_stage_input_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("crop_code", sa.String(30), nullable=False),
        sa.Column("season_code", sa.String(20)),
        sa.Column("stage_code", sa.String(50), nullable=False),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("input_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_inputs.id"), nullable=False),
        sa.Column("input_code", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("dosage_quantity", sa.Numeric(12, 3)),
        sa.Column("dosage_unit", sa.String(20)),
        sa.Column("dosage_area_unit", sa.String(20), nullable=False, server_default="ACRE"),
        sa.Column("min_quantity", sa.Numeric(12, 3)),
        sa.Column("max_quantity", sa.Numeric(12, 3)),
        sa.Column("application_method", sa.Text()),
        sa.Column("timing_note", sa.Text()),
        sa.Column("safety_note", sa.Text()),
        sa.Column("allowed_product_codes", postgresql.JSONB(), server_default="[]"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("reason", sa.Text()),
        *audit_columns(),
        sa.UniqueConstraint("tenant_id", "project_id", "crop_code", "season_code", "stage_code", "activity_type", "input_code", name="uq_crop_stage_input_rule_scope"),
    )
    for col in ["tenant_id", "project_id", "crop_code", "season_code", "stage_code", "activity_type", "input_id", "input_code"]:
        op.create_index(f"ix_crop_stage_input_rules_{col}", "crop_stage_input_rules", [col])
    op.create_index("idx_crop_stage_input_rule_lookup", "crop_stage_input_rules", ["tenant_id", "project_id", "crop_code", "stage_code", "activity_type"])
    op.create_index("idx_crop_stage_input_rule_input", "crop_stage_input_rules", ["input_code", "enabled"])

    op.create_table(
        "crop_stage_input_rule_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crop_stage_input_rules.id")),
        sa.Column("input_code", sa.String(50), nullable=False),
        sa.Column("crop_code", sa.String(30), nullable=False),
        sa.Column("stage_code", sa.String(50), nullable=False),
        sa.Column("activity_type", sa.String(30), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("before_payload", postgresql.JSONB()),
        sa.Column("after_payload", postgresql.JSONB()),
        sa.Column("reason", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        *audit_columns(),
    )
    for col in ["tenant_id", "project_id", "rule_id", "input_code", "crop_code", "stage_code", "activity_type"]:
        op.create_index(f"ix_crop_stage_input_rule_audit_events_{col}", "crop_stage_input_rule_audit_events", [col])
    op.create_index("idx_crop_stage_input_rule_audit_rule", "crop_stage_input_rule_audit_events", ["rule_id", "created_at"])
    op.create_index("idx_crop_stage_input_rule_audit_scope", "crop_stage_input_rule_audit_events", ["tenant_id", "project_id", "crop_code", "stage_code"])


def downgrade() -> None:
    op.drop_table("crop_stage_input_rule_audit_events")
    op.drop_table("crop_stage_input_rules")