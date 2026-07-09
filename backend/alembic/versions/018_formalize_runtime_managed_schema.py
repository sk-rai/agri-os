"""Formalize input assignment, audit, and workflow pinning schema.

Revision ID: 018
Revises: 017
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    tables = _table_names()

    if "project_input_assignments" not in tables:
        op.create_table(
            "project_input_assignments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("input_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_inputs.id"), nullable=False),
            sa.Column("input_code", sa.String(50), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("reason", sa.Text()),
            sa.Column("effective_from", sa.Date()),
            sa.Column("effective_to", sa.Date()),
            sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("version", sa.String(20), server_default="v1.0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("tenant_id", "project_id", "input_code", name="uq_project_input_assignment"),
        )
    _create_index_if_missing(
        "idx_project_input_assignment_project",
        "project_input_assignments",
        ["project_id", "enabled"],
    )
    _create_index_if_missing(
        "idx_project_input_assignment_code",
        "project_input_assignments",
        ["input_code"],
    )

    if "project_input_assignment_audit_events" not in tables:
        op.create_table(
            "project_input_assignment_audit_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("input_code", sa.String(50), nullable=False),
            sa.Column(
                "assignment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("project_input_assignments.id"),
            ),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("before_payload", postgresql.JSONB()),
            sa.Column("after_payload", postgresql.JSONB()),
            sa.Column("reason", sa.Text()),
            sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("version", sa.String(20), server_default="v1.0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    _create_index_if_missing(
        "idx_project_input_assignment_audit_project",
        "project_input_assignment_audit_events",
        ["project_id", "created_at"],
    )
    _create_index_if_missing(
        "idx_project_input_assignment_audit_input",
        "project_input_assignment_audit_events",
        ["project_id", "input_code"],
    )

    if "agricultural_input_audit_events" not in tables:
        op.create_table(
            "agricultural_input_audit_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("input_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agricultural_inputs.id"), nullable=False),
            sa.Column("input_code", sa.String(50), nullable=False),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("before_payload", postgresql.JSONB()),
            sa.Column("after_payload", postgresql.JSONB()),
            sa.Column("reason", sa.Text()),
            sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("version", sa.String(20), server_default="v1.0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    _create_index_if_missing(
        "idx_agricultural_input_audit_input",
        "agricultural_input_audit_events",
        ["input_code", "created_at"],
    )
    _create_index_if_missing(
        "idx_agricultural_input_audit_tenant",
        "agricultural_input_audit_events",
        ["tenant_id", "created_at"],
    )

    if "workflow_template_audit_events" not in tables:
        op.create_table(
            "workflow_template_audit_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_templates.id"), nullable=False),
            sa.Column(
                "template_version_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("workflow_template_versions.id"),
            ),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
            sa.Column("action", sa.String(60), nullable=False),
            sa.Column("target_type", sa.String(40), nullable=False),
            sa.Column("target_id", sa.String(120)),
            sa.Column("target_code", sa.String(220)),
            sa.Column("before", postgresql.JSONB()),
            sa.Column("after", postgresql.JSONB()),
            sa.Column("reason", sa.Text()),
            sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing(
        "idx_workflow_template_audit_template",
        "workflow_template_audit_events",
        ["template_id", "created_at"],
    )
    _create_index_if_missing(
        "idx_workflow_template_audit_version",
        "workflow_template_audit_events",
        ["template_version_id", "created_at"],
    )
    _create_index_if_missing(
        "idx_workflow_template_audit_action",
        "workflow_template_audit_events",
        ["action"],
    )
    _create_index_if_missing(
        "idx_workflow_template_audit_actor",
        "workflow_template_audit_events",
        ["actor_id"],
    )

    if "workflow_template_version_id" not in _column_names("crop_cycles"):
        op.add_column(
            "crop_cycles",
            sa.Column(
                "workflow_template_version_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("workflow_template_versions.id"),
            ),
        )
    _create_index_if_missing(
        "idx_crop_cycle_workflow_version",
        "crop_cycles",
        ["workflow_template_version_id"],
    )


def downgrade() -> None:
    if "idx_crop_cycle_workflow_version" in _index_names("crop_cycles"):
        op.drop_index("idx_crop_cycle_workflow_version", table_name="crop_cycles")
    if "workflow_template_version_id" in _column_names("crop_cycles"):
        op.drop_column("crop_cycles", "workflow_template_version_id")

    tables = _table_names()
    for table_name in [
        "workflow_template_audit_events",
        "agricultural_input_audit_events",
        "project_input_assignment_audit_events",
        "project_input_assignments",
    ]:
        if table_name in tables:
            op.drop_table(table_name)
