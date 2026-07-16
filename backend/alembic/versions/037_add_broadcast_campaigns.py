"""add broadcast campaigns

Revision ID: 037
Revises: 036
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broadcast_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broadcast_campaigns_tenant_id", "broadcast_campaigns", ["tenant_id"])
    op.create_index("ix_broadcast_campaigns_project_id", "broadcast_campaigns", ["project_id"])
    op.create_index("ix_broadcast_campaigns_created_by", "broadcast_campaigns", ["created_by"])
    op.create_index("ix_broadcast_campaigns_approved_by", "broadcast_campaigns", ["approved_by"])

    op.create_table(
        "broadcast_contents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast_campaigns.id"), nullable=False),
        sa.Column("language_code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.String(length=100), nullable=True),
        sa.Column("deeplink_url", sa.String(length=500), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broadcast_contents_tenant_id", "broadcast_contents", ["tenant_id"])
    op.create_index("ix_broadcast_contents_campaign_id", "broadcast_contents", ["campaign_id"])

    op.create_table(
        "broadcast_audience_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast_campaigns.id"), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("operator", sa.String(length=30), nullable=False),
        sa.Column("values", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broadcast_audience_rules_tenant_id", "broadcast_audience_rules", ["tenant_id"])
    op.create_index("ix_broadcast_audience_rules_campaign_id", "broadcast_audience_rules", ["campaign_id"])

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast_campaigns.id"), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delivery_status", sa.String(length=30), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broadcast_deliveries_tenant_id", "broadcast_deliveries", ["tenant_id"])
    op.create_index("ix_broadcast_deliveries_campaign_id", "broadcast_deliveries", ["campaign_id"])
    op.create_index("ix_broadcast_deliveries_farmer_id", "broadcast_deliveries", ["farmer_id"])
    op.create_index("ix_broadcast_deliveries_user_id", "broadcast_deliveries", ["user_id"])


def downgrade():
    op.drop_index("ix_broadcast_deliveries_user_id", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_farmer_id", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_campaign_id", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_tenant_id", table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")
    op.drop_index("ix_broadcast_audience_rules_campaign_id", table_name="broadcast_audience_rules")
    op.drop_index("ix_broadcast_audience_rules_tenant_id", table_name="broadcast_audience_rules")
    op.drop_table("broadcast_audience_rules")
    op.drop_index("ix_broadcast_contents_campaign_id", table_name="broadcast_contents")
    op.drop_index("ix_broadcast_contents_tenant_id", table_name="broadcast_contents")
    op.drop_table("broadcast_contents")
    op.drop_index("ix_broadcast_campaigns_approved_by", table_name="broadcast_campaigns")
    op.drop_index("ix_broadcast_campaigns_created_by", table_name="broadcast_campaigns")
    op.drop_index("ix_broadcast_campaigns_project_id", table_name="broadcast_campaigns")
    op.drop_index("ix_broadcast_campaigns_tenant_id", table_name="broadcast_campaigns")
    op.drop_table("broadcast_campaigns")
