"""Sync API endpoint: POST /api/v1/sync/events

Receives batch of offline events from mobile clients.
Returns: {accepted: [], conflicts: [], failed: []}

Per governance:
- Idempotent: duplicate event_id returns 200 with accepted
- Tenant-scoped: X-Tenant-ID enforced
- Audit-chained: every event gets immutable audit record
- Batch-resilient: partial success is valid (some accepted, some conflicted)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.modules.sync import service

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


# --- Request/Response Schemas ---

class SyncEventPayload(BaseModel):
    """A single sync event from the mobile client."""
    event_id: UUID
    entity_type: str = Field(..., description="Canonical entity type (farmer, parcel, crop_cycle, crop_stage)")
    entity_id: Optional[UUID] = None
    operation: str = Field(..., pattern="^(CREATE|UPDATE|DELETE)$")
    payload: dict
    version: int = Field(default=1, description="Client-side version counter")
    dependency_ids: list[UUID] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict, description="GPS, device_id, timestamp")


class SyncBatchRequest(BaseModel):
    """Batch of sync events."""
    events: list[SyncEventPayload] = Field(..., min_length=1, max_length=100)


class ConflictInfo(BaseModel):
    event_id: str
    conflict_type: str
    resolution_strategy: Optional[str] = None
    detail: str = ""


class FailedInfo(BaseModel):
    event_id: str
    error_code: str
    message: str


class SyncBatchResponse(BaseModel):
    """Response from sync batch processing."""
    accepted: list[str]
    conflicts: list[ConflictInfo]
    failed: list[FailedInfo]
    total_processed: int


# --- Endpoint ---

@router.post("/events", response_model=SyncBatchResponse)
def process_sync_events(
    body: SyncBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Process a batch of offline sync events.

    Idempotent: re-submitting the same event_id is safe (returns accepted).
    Batch-resilient: some events may succeed while others conflict.

    Requires:
    - Valid JWT (actor_id extracted from token)
    - X-Tenant-ID header
    - Events with unique event_ids
    """
    # Extract actor_id from JWT (for MVP, use a header; proper JWT extraction later)
    actor_id = request.headers.get("X-Actor-ID")
    if not actor_id:
        raise HTTPException(status_code=400, detail="X-Actor-ID header required")

    # Convert events to dicts for service layer
    events_data = [
        {
            "event_id": str(e.event_id),
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "operation": e.operation,
            "payload": e.payload,
            "version": e.version,
            "dependency_ids": [str(d) for d in e.dependency_ids],
            "metadata": e.metadata,
        }
        for e in body.events
    ]

    # Process batch
    result = service.process_sync_batch(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=actor_id,
        events=events_data,
    )

    return SyncBatchResponse(
        accepted=result.accepted,
        conflicts=[ConflictInfo(**c) for c in result.conflicts],
        failed=[FailedInfo(**f) for f in result.failed],
        total_processed=len(result.accepted) + len(result.conflicts) + len(result.failed),
    )
