"""Sync engine models: processed events, conflicts, audit chain.

Per ADR-006: Retry capped at 10, then dead_letter.
Per ADR-007: Conflict routing by type (geo, version, workflow).
Per ADR-009: Audit chain with hash chaining for tamper detection.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Boolean,
    ForeignKey, Index, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.models import UUIDPrimaryKey


class SyncProcessedEvent(Base):
    """Idempotency log: tracks every event_id we've already processed.

    INSERT ... ON CONFLICT DO NOTHING pattern for deduplication.
    """

    __tablename__ = "sync_processed_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True))
    operation = Column(String(20), nullable=False)  # CREATE, UPDATE, DELETE
    server_version = Column(Integer, default=1)
    processed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status = Column(String(20), default="COMMITTED", nullable=False)
    # COMMITTED, CONFLICT, FAILED, DEPENDENCY_MISSING

    __table_args__ = (
        Index("idx_sync_processed_tenant_event", "tenant_id", "event_id"),
    )


class SyncConflict(Base, UUIDPrimaryKey):
    """Conflict queue: events that couldn't auto-commit.

    Per ADR-007: Routes to manual review, semantic merge, or server authority.
    """

    __tablename__ = "sync_conflicts"

    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sync_processed_events.event_id"),
        nullable=False,
    )
    tenant_id = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    conflict_type = Column(String(30), nullable=False)
    # VERSION_MISMATCH, GEO_OVERLAP, WORKFLOW_INVALID, DEPENDENCY_MISSING
    client_payload = Column(JSONB, nullable=False)
    server_payload = Column(JSONB)
    resolution_strategy = Column(String(30))
    # MANUAL_REVIEW, SEMANTIC_MERGE, APPEND_ONLY, SERVER_AUTHORITY
    status = Column(String(20), default="PENDING_REVIEW", nullable=False)
    # PENDING_REVIEW, RESOLVED_CLIENT, RESOLVED_SERVER, RESOLVED_MERGE
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(UUID(as_uuid=True))  # Actor who resolved (no FK for MVP flexibility)

    __table_args__ = (
        Index("idx_sync_conflicts_tenant_status", "tenant_id", "status"),
        Index("idx_sync_conflicts_entity", "entity_type", "entity_id"),
    )


class AuditChainEntry(Base):
    """Immutable audit chain with hash chaining.

    Per ADR-009 + Security Framework:
    - Append-only (no UPDATE, no DELETE)
    - chain_hash = SHA256(prev_chain_hash + action + payload_hash + actor_id + timestamp)
    - PII masked: GPS rounded to 2 decimals, mobile hashed
    - Tenant-isolated: all queries scoped
    """

    __tablename__ = "audit_chain"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    correlation_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(UUID(as_uuid=True))
    action = Column(String(50), nullable=False)
    # SYNC_COMMIT, SYNC_CONFLICT, SYNC_FAILED, CONFLICT_RESOLVED
    before_hash = Column(String(64))  # SHA256 of entity state before
    after_hash = Column(String(64))   # SHA256 of entity state after
    chain_hash = Column(String(64), nullable=False)  # Chained hash
    metadata_ = Column("metadata", JSONB, default=dict)
    # Contains: device_id, gps (rounded), retry_count, conflict_type
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_audit_chain_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("idx_audit_chain_correlation", "correlation_id"),
        Index("idx_audit_chain_tenant_time", "tenant_id", "created_at"),
    )
