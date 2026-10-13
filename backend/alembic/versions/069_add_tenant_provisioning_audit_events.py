"""Add immutable tenant provisioning audit events.

Revision ID: 069
Revises: 068
Create Date: 2026-10-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "069"
down_revision: Union[str, None] = "068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_provisioning_audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "target_tenant_id",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "actor_tenant_id",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "after_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["target_tenant_id"],
            ["tenants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["actor_tenant_id"],
            ["tenants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_provisioning_audit_events_target_tenant_id",
        "tenant_provisioning_audit_events",
        ["target_tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_provisioning_audit_events_actor_tenant_id",
        "tenant_provisioning_audit_events",
        ["actor_tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_provisioning_audit_events_actor_id",
        "tenant_provisioning_audit_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_provisioning_audit_target_created",
        "tenant_provisioning_audit_events",
        ["target_tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_provisioning_audit_actor_created",
        "tenant_provisioning_audit_events",
        ["actor_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_provisioning_audit_action",
        "tenant_provisioning_audit_events",
        ["action"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tenant_provisioning_audit_action",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_index(
        "idx_tenant_provisioning_audit_actor_created",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_index(
        "idx_tenant_provisioning_audit_target_created",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_index(
        "ix_tenant_provisioning_audit_events_actor_id",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_index(
        "ix_tenant_provisioning_audit_events_actor_tenant_id",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_index(
        "ix_tenant_provisioning_audit_events_target_tenant_id",
        table_name="tenant_provisioning_audit_events",
    )
    op.drop_table("tenant_provisioning_audit_events")
