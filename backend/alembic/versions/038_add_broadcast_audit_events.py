"""add broadcast audit events

Revision ID: 038
Revises: 037
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broadcast_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast_campaigns.id"), nullable=False),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast_deliveries.id"), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broadcast_audit_events_tenant_id", "broadcast_audit_events", ["tenant_id"])
    op.create_index("ix_broadcast_audit_events_campaign_id", "broadcast_audit_events", ["campaign_id"])
    op.create_index("ix_broadcast_audit_events_delivery_id", "broadcast_audit_events", ["delivery_id"])
    op.create_index("ix_broadcast_audit_events_action", "broadcast_audit_events", ["action"])
    op.create_index("ix_broadcast_audit_events_actor_id", "broadcast_audit_events", ["actor_id"])


def downgrade():
    op.drop_index("ix_broadcast_audit_events_actor_id", table_name="broadcast_audit_events")
    op.drop_index("ix_broadcast_audit_events_action", table_name="broadcast_audit_events")
    op.drop_index("ix_broadcast_audit_events_delivery_id", table_name="broadcast_audit_events")
    op.drop_index("ix_broadcast_audit_events_campaign_id", table_name="broadcast_audit_events")
    op.drop_index("ix_broadcast_audit_events_tenant_id", table_name="broadcast_audit_events")
    op.drop_table("broadcast_audit_events")
