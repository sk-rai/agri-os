"""Add workflow finance report config versions.

Revision ID: 050
Revises: 049
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_finance_report_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crop_code", sa.String(length=30), nullable=True),
        sa.Column("season_code", sa.String(length=20), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(length=80), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.String(length=10), nullable=False, server_default="v1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_workflow_finance_report_config_status"),
    )
    op.create_index(
        "idx_workflow_finance_report_configs_scope",
        "workflow_finance_report_configs",
        ["tenant_id", "project_id", "crop_code", "season_code", "status", "is_active"],
    )
    op.create_unique_constraint(
        "uq_workflow_finance_report_configs_version",
        "workflow_finance_report_configs",
        ["tenant_id", "project_id", "crop_code", "season_code", "config_version"],
    )
    op.create_index(
        "uq_workflow_finance_report_configs_one_published",
        "workflow_finance_report_configs",
        ["tenant_id", "project_id", "crop_code", "season_code"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED' and is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_finance_report_configs_one_published", table_name="workflow_finance_report_configs")
    op.drop_constraint("uq_workflow_finance_report_configs_version", "workflow_finance_report_configs", type_="unique")
    op.drop_index("idx_workflow_finance_report_configs_scope", table_name="workflow_finance_report_configs")
    op.drop_table("workflow_finance_report_configs")
