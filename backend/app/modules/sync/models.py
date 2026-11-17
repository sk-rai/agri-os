"""Sync engine models: processed events, conflicts, audit chain.

Per ADR-006: Retry capped at 10, then dead_letter.
Per ADR-007: Conflict routing by type (geo, version, workflow).
Per ADR-009: Audit chain with hash chaining for tamper detection.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CHAR, Column, String, Integer, BigInteger, DateTime, Boolean,
    CheckConstraint, ForeignKey, Index, Text, UniqueConstraint,
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


class CropActivityCommandBinding(Base):
    """Immutable request intent and committed result for one activity ID."""

    __tablename__ = "crop_activity_command_bindings"

    activity_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "crop_activities.id",
            name="fk_crop_activity_command_binding_activity",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    tenant_id = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), nullable=False)
    crop_cycle_id = Column(UUID(as_uuid=True), nullable=False)
    origin_kind = Column(String(10), nullable=False)
    origin_event_id = Column(UUID(as_uuid=True))
    intent_version = Column(String(40), nullable=False)
    intent_canonical = Column(Text, nullable=False)
    intent_sha256 = Column(CHAR(64), nullable=False)
    resolved_stage_id = Column(UUID(as_uuid=True))
    result_version = Column(String(40), nullable=False)
    result_payload = Column(JSONB, nullable=False)
    audit_correlation_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "origin_kind IN ('DIRECT', 'SYNC')",
            name="ck_crop_activity_command_binding_origin_kind",
        ),
        CheckConstraint(
            "(origin_kind = 'DIRECT' AND origin_event_id IS NULL) OR "
            "(origin_kind = 'SYNC' AND origin_event_id IS NOT NULL)",
            name="ck_crop_activity_command_binding_origin_event",
        ),
        Index(
            "idx_crop_activity_command_binding_tenant_cycle",
            "tenant_id",
            "crop_cycle_id",
        ),
        Index(
            "idx_crop_activity_command_binding_tenant_event",
            "tenant_id",
            "origin_event_id",
        ),
    )


class CropActivitySyncEventBinding(Base):
    """Committed sync-event identity for one activity command binding."""

    __tablename__ = "crop_activity_sync_event_bindings"

    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "sync_processed_events.event_id",
            name="fk_crop_activity_sync_event_binding_event",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    tenant_id = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    activity_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "crop_activity_command_bindings.activity_id",
            name="fk_crop_activity_sync_event_binding_activity",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    intent_version = Column(String(40), nullable=False)
    intent_canonical = Column(Text, nullable=False)
    intent_sha256 = Column(CHAR(64), nullable=False)
    outcome = Column(String(20), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "outcome = 'COMMITTED'",
            name="ck_crop_activity_sync_event_binding_outcome",
        ),
        UniqueConstraint(
            "activity_id",
            name="uq_crop_activity_sync_event_binding_activity",
        ),
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
