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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.core.human_auth import (
    AuthenticatedPrincipal,
    require_detached_authenticated_human,
)
from app.modules.sync import service
from app.modules.sync.authorization import authorize_sync_events
from app.modules.sync.ingress import preflight_sync_request
from app.modules.sync.schemas import SyncBatchRequest, SyncEventPayload

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


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


def process_validated_sync_events(
    *,
    events: list[SyncEventPayload],
    principal: AuthenticatedPrincipal,
    db: Session,
) -> SyncBatchResponse:
    """Authorize and process events that already passed lossless ingress.

    This seam is intentionally below the HTTP raw-body boundary. Production
    callers must not use it to bypass ``preflight_sync_request``.
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
        for event in events
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


def process_validated_sync_events_in_session(
    *,
    events: list[SyncEventPayload],
    principal: AuthenticatedPrincipal,
) -> SyncBatchResponse:
    """Create, use, and close the SQLAlchemy session in one worker thread."""

    db = SessionLocal()
    try:
        return process_validated_sync_events(
            events=events,
            principal=principal,
            db=db,
        )
    finally:
        db.close()


# --- Endpoint ---

@router.post("/events", response_model=SyncBatchResponse)
async def process_sync_events(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(
        require_detached_authenticated_human()
    ),
):
    """Process authenticated offline sync events.

    Tenant and actor identity are derived from the verified bearer principal.
    Each event is also checked against personal-farmer ownership, explicit
    project assignment, or bounded web-administrator authority.
    """
    logical_events = await preflight_sync_request(
        request,
        lambda event: SyncEventPayload.model_validate(event),
    )
    return await run_in_threadpool(
        process_validated_sync_events_in_session,
        events=[item.validated for item in logical_events],
        principal=principal,
    )
