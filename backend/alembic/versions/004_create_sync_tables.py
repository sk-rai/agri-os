"""Create sync engine tables: processed events, conflicts, audit chain

Revision ID: 004
Revises: 003
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- sync_processed_events (idempotency log) ---
    op.create_table(
        "sync_processed_events",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("server_version", sa.Integer, server_default="1"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="COMMITTED", nullable=False),
    )
    op.create_index(
        "idx_sync_processed_tenant_event",
        "sync_processed_events",
        ["tenant_id", "event_id"],
    )

    # --- sync_conflicts (conflict queue) ---
    op.create_table(
        "sync_conflicts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id", UUID(as_uuid=True),
            sa.ForeignKey("sync_processed_events.event_id"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conflict_type", sa.String(30), nullable=False),
        sa.Column("client_payload", JSONB, nullable=False),
        sa.Column("server_payload", JSONB),
        sa.Column("resolution_strategy", sa.String(30)),
        sa.Column("status", sa.String(20), server_default="PENDING_REVIEW", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID(as_uuid=True)),
    )
    op.create_index(
        "idx_sync_conflicts_tenant_status",
        "sync_conflicts",
        ["tenant_id", "status"],
    )
    op.create_index(
        "idx_sync_conflicts_entity",
        "sync_conflicts",
        ["entity_type", "entity_id"],
    )

    # --- audit_chain (immutable, append-only) ---
    op.create_table(
        "audit_chain",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("before_hash", sa.String(64)),
        sa.Column("after_hash", sa.String(64)),
        sa.Column("chain_hash", sa.String(64), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_audit_chain_tenant_entity",
        "audit_chain",
        ["tenant_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "idx_audit_chain_correlation",
        "audit_chain",
        ["correlation_id"],
    )
    op.create_index(
        "idx_audit_chain_tenant_time",
        "audit_chain",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("audit_chain")
    op.drop_table("sync_conflicts")
    op.drop_table("sync_processed_events")
