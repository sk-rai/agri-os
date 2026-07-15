"""add query threads

Revision ID: 035
Revises: 034
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_threads",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crop_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage_code", sa.String(length=50), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="OTHER"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("category IN ('CROP_HEALTH', 'INPUT_USAGE', 'IRRIGATION', 'MARKET', 'INSURANCE', 'TECH_SUPPORT', 'OTHER')", name="ck_query_thread_category"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')", name="ck_query_thread_priority"),
        sa.CheckConstraint("status IN ('OPEN', 'ASSIGNED', 'ANSWERED', 'CLOSED')", name="ck_query_thread_status"),
        sa.ForeignKeyConstraint(["crop_cycle_id"], ["crop_cycles.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_query_thread_tenant", "query_threads", ["tenant_id"], unique=False)
    op.create_index("idx_query_thread_project", "query_threads", ["project_id"], unique=False)
    op.create_index("idx_query_thread_farmer", "query_threads", ["farmer_id"], unique=False)
    op.create_index("idx_query_thread_parcel", "query_threads", ["parcel_id"], unique=False)
    op.create_index("idx_query_thread_status", "query_threads", ["status"], unique=False)
    op.create_index("idx_query_thread_category", "query_threads", ["category"], unique=False)
    op.create_index("idx_query_thread_last_message", "query_threads", ["last_message_at"], unique=False)

    op.create_table(
        "query_messages",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_type", sa.String(length=30), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_type", sa.String(length=20), nullable=False, server_default="TEXT"),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("sender_type IN ('FARMER', 'FIELD_AGENT', 'AGRONOMIST', 'ADMIN', 'SYSTEM')", name="ck_query_message_sender_type"),
        sa.CheckConstraint("message_type IN ('TEXT', 'AUDIO', 'PHOTO', 'DOCUMENT', 'SYSTEM')", name="ck_query_message_type"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["query_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_query_message_tenant", "query_messages", ["tenant_id"], unique=False)
    op.create_index("idx_query_message_thread", "query_messages", ["thread_id"], unique=False)
    op.create_index("idx_query_message_sender", "query_messages", ["sender_type", "sender_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_query_message_sender", table_name="query_messages")
    op.drop_index("idx_query_message_thread", table_name="query_messages")
    op.drop_index("idx_query_message_tenant", table_name="query_messages")
    op.drop_table("query_messages")
    op.drop_index("idx_query_thread_last_message", table_name="query_threads")
    op.drop_index("idx_query_thread_category", table_name="query_threads")
    op.drop_index("idx_query_thread_status", table_name="query_threads")
    op.drop_index("idx_query_thread_parcel", table_name="query_threads")
    op.drop_index("idx_query_thread_farmer", table_name="query_threads")
    op.drop_index("idx_query_thread_project", table_name="query_threads")
    op.drop_index("idx_query_thread_tenant", table_name="query_threads")
    op.drop_table("query_threads")