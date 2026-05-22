"""Sync engine service: batch processing, conflict detection, audit chain.

Pipeline: Idempotency → Dependency → Conflict Detection → Commit → Audit

Per governance:
- ADR-006: Retry capped at 10, then dead_letter
- ADR-007: Conflict routing by type
- ADR-009: Audit chain with hash chaining
- Sync Engine Contract §3-7: Retry formula, dependency filtering, idempotency
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.modules.sync.models import (
    SyncProcessedEvent,
    SyncConflict,
    AuditChainEntry,
)


# --- Schemas for sync events ---

class SyncEvent:
    """A single sync event from the mobile client."""

    def __init__(self, data: dict):
        self.event_id = data["event_id"]
        self.entity_type = data["entity_type"]
        self.entity_id = data.get("entity_id")
        self.operation = data["operation"]  # CREATE, UPDATE, DELETE
        self.payload = data["payload"]
        self.client_version = data.get("version", 1)
        self.dependency_ids = data.get("dependency_ids", [])
        self.metadata = data.get("metadata", {})


class SyncResult:
    """Result of processing a sync batch."""

    def __init__(self):
        self.accepted: list[str] = []  # event_ids committed
        self.conflicts: list[dict] = []  # event_ids with conflict info
        self.failed: list[dict] = []  # event_ids with error info


# --- Audit Chain ---

def compute_chain_hash(
    prev_hash: str,
    action: str,
    payload_hash: str,
    actor_id: str,
    timestamp: str,
) -> str:
    """Compute chain hash: SHA256(prev + action + payload + actor + time)."""
    data = f"{prev_hash}:{action}:{payload_hash}:{actor_id}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()


def compute_payload_hash(payload: dict) -> str:
    """SHA256 of deterministic JSON serialization."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def get_prev_chain_hash(db: Session, tenant_id: str) -> str:
    """Get the most recent chain_hash for this tenant."""
    result = db.execute(
        text("""
            SELECT chain_hash FROM audit_chain
            WHERE tenant_id = :tenant_id
            ORDER BY id DESC LIMIT 1
        """),
        {"tenant_id": tenant_id},
    ).fetchone()
    return result[0] if result else "0" * 64  # Genesis hash


def append_audit(
    db: Session,
    tenant_id: str,
    actor_id: str,
    correlation_id: str,
    entity_type: str,
    entity_id: Optional[str],
    action: str,
    payload: dict,
    metadata: dict,
) -> str:
    """Append an entry to the audit chain. Returns the new chain_hash."""
    now_str = datetime.now(timezone.utc).isoformat()
    prev_hash = get_prev_chain_hash(db, tenant_id)
    payload_hash = compute_payload_hash(payload)
    chain_hash = compute_chain_hash(prev_hash, action, payload_hash, actor_id, now_str)

    entry = AuditChainEntry(
        tenant_id=tenant_id,
        actor_id=uuid.UUID(actor_id),
        correlation_id=uuid.UUID(correlation_id),
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        action=action,
        after_hash=payload_hash,
        chain_hash=chain_hash,
        metadata_=metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    return chain_hash


# --- Idempotency ---

def filter_already_processed(
    db: Session, tenant_id: str, event_ids: list[str]
) -> set[str]:
    """Return set of event_ids that have already been processed."""
    if not event_ids:
        return set()

    # Use ORM query to avoid raw SQL array casting issues
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    uuid_list = [uuid.UUID(eid) for eid in event_ids]
    results = (
        db.query(SyncProcessedEvent.event_id)
        .filter(
            SyncProcessedEvent.tenant_id == tenant_id,
            SyncProcessedEvent.event_id.in_(uuid_list),
        )
        .all()
    )
    return {str(r[0]) for r in results}


# --- Dependency Validation ---

def validate_dependencies(
    db: Session, tenant_id: str, dependency_ids: list[str]
) -> list[str]:
    """Check which dependency_ids are missing from processed events.

    Per sync-engine-contract §4: dependency skip does NOT count as retry failure.
    Returns list of MISSING dependency event_ids.
    """
    if not dependency_ids:
        return []

    processed = filter_already_processed(db, tenant_id, dependency_ids)
    return [d for d in dependency_ids if d not in processed]


# --- Conflict Detection ---

def detect_conflict(
    db: Session,
    tenant_id: str,
    event: SyncEvent,
) -> Optional[dict]:
    """Detect if an event conflicts with current server state.

    Returns conflict info dict if conflict detected, None if safe to commit.

    Per ADR-007:
    - VERSION_MISMATCH: client version < server version
    - GEO_OVERLAP: parcel geometry overlaps >5% (stub until parcels exist)
    - WORKFLOW_INVALID: stage transition violates lifecycle template
    """
    # Check if entity already exists with higher version
    if event.operation == "UPDATE" and event.entity_id:
        existing = db.execute(
            text("""
                SELECT server_version, status FROM sync_processed_events
                WHERE tenant_id = :tenant_id
                AND entity_id = :entity_id
                AND entity_type = :entity_type
                AND status = 'COMMITTED'
                ORDER BY processed_at DESC LIMIT 1
            """),
            {
                "tenant_id": tenant_id,
                "entity_id": event.entity_id,
                "entity_type": event.entity_type,
            },
        ).fetchone()

        if existing and existing[0] > event.client_version:
            return {
                "conflict_type": "VERSION_MISMATCH",
                "resolution_strategy": "MANUAL_REVIEW",
                "server_version": existing[0],
                "client_version": event.client_version,
            }

    # Workflow validation for crop_cycle stage transitions
    if event.entity_type in ("crop_stage", "crop_cycle") and event.operation == "UPDATE":
        conflict = validate_workflow_transition(db, tenant_id, event)
        if conflict:
            return conflict

    # GEO_OVERLAP detection (stub — will be implemented when parcel geometry exists)
    # if event.entity_type == "parcel" and event.operation in ("CREATE", "UPDATE"):
    #     conflict = detect_geo_overlap(db, tenant_id, event)
    #     if conflict:
    #         return conflict

    return None


def validate_workflow_transition(
    db: Session, tenant_id: str, event: SyncEvent
) -> Optional[dict]:
    """Validate stage transition against lifecycle template.

    Never hardcodes stage names — always loads from crop_lifecycle_templates.
    """
    payload = event.payload
    target_stage_code = payload.get("stage_code")
    template_id = payload.get("lifecycle_template_id")

    if not target_stage_code or not template_id:
        return None  # Can't validate without these — allow through

    # Load template stages
    from app.modules.master_data.models import CropLifecycleTemplate
    template = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.id == uuid.UUID(template_id),
            CropLifecycleTemplate.is_active == True,
        )
        .first()
    )

    if not template:
        return None  # Template not found — allow through (may be tenant-custom)

    stages = template.stages
    valid_codes = {s["code"] for s in stages if isinstance(s, dict)}

    if target_stage_code not in valid_codes:
        return {
            "conflict_type": "WORKFLOW_INVALID",
            "resolution_strategy": "SERVER_AUTHORITY",
            "detail": f"Stage '{target_stage_code}' not in template",
            "valid_stages": sorted(valid_codes),
        }

    return None


# --- Batch Processing Pipeline ---

def process_sync_batch(
    db: Session,
    tenant_id: str,
    actor_id: str,
    events: list[dict],
) -> SyncResult:
    """Process a batch of sync events through the full pipeline.

    Steps:
    1. Idempotency filter (skip already-processed)
    2. Dependency validation (defer if deps missing)
    3. Conflict detection (route to conflict queue)
    4. Transactional commit (all-or-nothing per event)
    5. Audit chain (append immutable record)
    """
    result = SyncResult()
    correlation_id = str(uuid.uuid4())

    # Parse events
    parsed_events = [SyncEvent(e) for e in events]
    all_event_ids = [str(e.event_id) for e in parsed_events]

    # Step 1: Idempotency filter
    already_processed = filter_already_processed(db, tenant_id, all_event_ids)

    for event in parsed_events:
        event_id_str = str(event.event_id)

        # Skip already processed (idempotent)
        if event_id_str in already_processed:
            result.accepted.append(event_id_str)
            continue

        # Step 2: Dependency validation
        missing_deps = validate_dependencies(db, tenant_id, event.dependency_ids)
        if missing_deps:
            # Record as failed with DEPENDENCY_MISSING
            record = SyncProcessedEvent(
                event_id=uuid.UUID(event_id_str),
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                entity_type=event.entity_type,
                entity_id=uuid.UUID(event.entity_id) if event.entity_id else None,
                operation=event.operation,
                status="DEPENDENCY_MISSING",
                processed_at=datetime.now(timezone.utc),
            )
            db.add(record)
            result.failed.append({
                "event_id": event_id_str,
                "error_code": "DEPENDENCY_MISSING",
                "message": f"Missing dependencies: {missing_deps}",
            })
            continue

        # Step 3: Conflict detection
        conflict = detect_conflict(db, tenant_id, event)
        if conflict:
            # Record processed event with CONFLICT status (flush to satisfy FK)
            record = SyncProcessedEvent(
                event_id=uuid.UUID(event_id_str),
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                entity_type=event.entity_type,
                entity_id=uuid.UUID(event.entity_id) if event.entity_id else None,
                operation=event.operation,
                status="CONFLICT",
                processed_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.flush()  # Flush so FK constraint is satisfied

            # Insert conflict record
            conflict_record = SyncConflict(
                id=uuid.uuid4(),
                event_id=uuid.UUID(event_id_str),
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                entity_type=event.entity_type,
                entity_id=uuid.UUID(event.entity_id) if event.entity_id else uuid.uuid4(),
                conflict_type=conflict["conflict_type"],
                client_payload=event.payload,
                server_payload=conflict,
                resolution_strategy=conflict.get("resolution_strategy", "MANUAL_REVIEW"),
                status="PENDING_REVIEW",
                created_at=datetime.now(timezone.utc),
            )
            db.add(conflict_record)

            # Audit: conflict detected
            append_audit(
                db, tenant_id, actor_id, correlation_id,
                event.entity_type, event.entity_id,
                "SYNC_CONFLICT", event.payload,
                {**event.metadata, "conflict_type": conflict["conflict_type"]},
            )

            result.conflicts.append({
                "event_id": event_id_str,
                "conflict_type": conflict["conflict_type"],
                "resolution_strategy": conflict.get("resolution_strategy"),
                "detail": conflict.get("detail", ""),
            })
            continue

        # Step 4: Commit (event is safe)
        record = SyncProcessedEvent(
            event_id=uuid.UUID(event_id_str),
            tenant_id=tenant_id,
            actor_id=uuid.UUID(actor_id),
            entity_type=event.entity_type,
            entity_id=uuid.UUID(event.entity_id) if event.entity_id else None,
            operation=event.operation,
            server_version=event.client_version,
            status="COMMITTED",
            processed_at=datetime.now(timezone.utc),
        )
        db.add(record)

        # Step 5: Audit chain
        append_audit(
            db, tenant_id, actor_id, correlation_id,
            event.entity_type, event.entity_id,
            "SYNC_COMMIT", event.payload, event.metadata,
        )

        result.accepted.append(event_id_str)

    # Commit entire batch
    db.commit()
    return result
