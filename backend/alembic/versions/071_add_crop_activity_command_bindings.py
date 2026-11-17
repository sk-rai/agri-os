"""Add durable crop activity command and sync-event bindings.

The migration is additive and performs no backfill. Existing activities remain
unverified for replay purposes. Downgrade fails closed if removing this schema
would discard a binding or newly persisted irrigation content.

Revision ID: 071
Revises: 070
Create Date: 2026-11-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "071"
down_revision: Union[str, None] = "070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crop_activities",
        sa.Column("irrigation_source", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "crop_activities",
        sa.Column("duration_hours", sa.Numeric(precision=10, scale=2), nullable=True),
    )

    op.create_table(
        "crop_activity_command_bindings",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crop_cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_kind", sa.String(length=10), nullable=False),
        sa.Column("origin_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("intent_version", sa.String(length=40), nullable=False),
        sa.Column("intent_canonical", sa.Text(), nullable=False),
        sa.Column("intent_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("resolved_stage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_version", sa.String(length=40), nullable=False),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("audit_correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "origin_kind IN ('DIRECT', 'SYNC')",
            name="ck_crop_activity_command_binding_origin_kind",
        ),
        sa.CheckConstraint(
            "(origin_kind = 'DIRECT' AND origin_event_id IS NULL) OR "
            "(origin_kind = 'SYNC' AND origin_event_id IS NOT NULL)",
            name="ck_crop_activity_command_binding_origin_event",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["crop_activities.id"],
            name="fk_crop_activity_command_binding_activity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("activity_id"),
    )
    op.create_index(
        "idx_crop_activity_command_binding_tenant_cycle",
        "crop_activity_command_bindings",
        ["tenant_id", "crop_cycle_id"],
        unique=False,
    )
    op.create_index(
        "idx_crop_activity_command_binding_tenant_event",
        "crop_activity_command_bindings",
        ["tenant_id", "origin_event_id"],
        unique=False,
    )

    op.create_table(
        "crop_activity_sync_event_bindings",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_version", sa.String(length=40), nullable=False),
        sa.Column("intent_canonical", sa.Text(), nullable=False),
        sa.Column("intent_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome = 'COMMITTED'",
            name="ck_crop_activity_sync_event_binding_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["sync_processed_events.event_id"],
            name="fk_crop_activity_sync_event_binding_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["crop_activity_command_bindings.activity_id"],
            name="fk_crop_activity_sync_event_binding_activity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "activity_id",
            name="uq_crop_activity_sync_event_binding_activity",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE crop_activity_sync_event_bindings, "
            "crop_activity_command_bindings, crop_activities "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    has_bindings = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM crop_activity_command_bindings LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM crop_activity_sync_event_bindings LIMIT 1)"
        )
    ).scalar()
    has_irrigation_content = connection.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM crop_activities "
            "WHERE irrigation_source IS NOT NULL OR duration_hours IS NOT NULL "
            "LIMIT 1)"
        )
    ).scalar()
    if has_bindings or has_irrigation_content:
        raise RuntimeError(
            "071_DOWNGRADE_BLOCKED: activity bindings or irrigation content exist"
        )

    op.drop_table("crop_activity_sync_event_bindings")
    op.drop_index(
        "idx_crop_activity_command_binding_tenant_event",
        table_name="crop_activity_command_bindings",
    )
    op.drop_index(
        "idx_crop_activity_command_binding_tenant_cycle",
        table_name="crop_activity_command_bindings",
    )
    op.drop_table("crop_activity_command_bindings")
    op.drop_column("crop_activities", "duration_hours")
    op.drop_column("crop_activities", "irrigation_source")
