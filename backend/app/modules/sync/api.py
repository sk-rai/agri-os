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
from app.core.human_auth import AuthenticatedPrincipal, require_authenticated_human
from app.modules.sync import service
from app.modules.sync.authorization import authorize_sync_events

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
    detail_code: Optional[str] = None
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
    principal: AuthenticatedPrincipal = Depends(
        require_authenticated_human()
    ),
    db: Session = Depends(get_db),
):
    """Process authenticated offline sync events.

    Tenant and actor identity are derived from the verified bearer principal.
    Each event is also checked against personal-farmer ownership, explicit
    project assignment, or bounded web-administrator authority.
    """
    events_data = [
        {
            "event_id": str(event.event_id),
            "entity_type": event.entity_type,
            "entity_id": str(event.entity_id) if event.entity_id else None,
            "operation": event.operation,
            "payload": event.payload,
            "version": event.version,
            "dependency_ids": [
                str(dependency_id)
                for dependency_id in event.dependency_ids
            ],
            "metadata": event.metadata,
        }
        for event in body.events
    ]

    authorized_events, denied_events = authorize_sync_events(
        db,
        principal=principal,
        events=events_data,
    )
    result = service.process_sync_batch(
        db=db,
        tenant_id=principal.tenant_id,
        actor_id=str(principal.user_id),
        events=authorized_events,
    )
    result.failed.extend(denied_events)

    return SyncBatchResponse(
        accepted=result.accepted,
        conflicts=[
            ConflictInfo(**conflict)
            for conflict in result.conflicts
        ],
        failed=[
            FailedInfo(**failure)
            for failure in result.failed
        ],
        total_processed=len(events_data),
    )
