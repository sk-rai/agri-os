"""Add immutable tenant app-config audit events.

Revision ID: 068
Revises: 067
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_app_config_audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
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
            "patched_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "before_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "config_patch",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_tenant_app_config_audit_tenant_created",
        "tenant_app_config_audit_events",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_app_config_audit_actor",
        "tenant_app_config_audit_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_app_config_audit_action",
        "tenant_app_config_audit_events",
        ["action"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "idx_tenant_app_config_audit_action",
        table_name="tenant_app_config_audit_events",
    )
    op.drop_index(
        "idx_tenant_app_config_audit_actor",
        table_name="tenant_app_config_audit_events",
    )
    op.drop_index(
        "idx_tenant_app_config_audit_tenant_created",
        table_name="tenant_app_config_audit_events",
    )
    op.drop_table("tenant_app_config_audit_events")
