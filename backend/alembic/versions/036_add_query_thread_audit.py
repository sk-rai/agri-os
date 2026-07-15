"""add query thread audit events

Revision ID: 036
Revises: 035
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "query_thread_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("query_threads.id"), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_query_thread_audit_events_tenant_id", "query_thread_audit_events", ["tenant_id"])
    op.create_index("ix_query_thread_audit_events_thread_id", "query_thread_audit_events", ["thread_id"])
    op.create_index("ix_query_thread_audit_events_action", "query_thread_audit_events", ["action"])
    op.create_index("ix_query_thread_audit_events_actor_id", "query_thread_audit_events", ["actor_id"])


def downgrade():
    op.drop_index("ix_query_thread_audit_events_actor_id", table_name="query_thread_audit_events")
    op.drop_index("ix_query_thread_audit_events_action", table_name="query_thread_audit_events")
    op.drop_index("ix_query_thread_audit_events_thread_id", table_name="query_thread_audit_events")
    op.drop_index("ix_query_thread_audit_events_tenant_id", table_name="query_thread_audit_events")
    op.drop_table("query_thread_audit_events")
