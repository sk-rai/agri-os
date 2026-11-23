"""Sync API endpoint: POST /api/v1/sync/events

Receives batch of offline events from mobile clients.
Returns: {accepted: [], conflicts: [], failed: []}

Per governance:
- Idempotent: duplicate event_id returns 200 with accepted
- Tenant-scoped: X-Tenant-ID enforced
- Audit-chained: every event gets immutable audit record
- Batch-resilient: partial success is valid (some accepted, some conflicted)
"""

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.core.human_auth import (
    AuthenticatedPrincipal,
    require_detached_authenticated_human,
)
from app.modules.sync import service
from app.modules.sync.authorization import authorize_sync_events
from app.modules.sync.ingress import PreflightEvent, preflight_sync_request
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


class AcceptedDetail(BaseModel):
    event_id: UUID
    entity_type: str
    entity_id: UUID
    activity_id: UUID
    outcome: Literal["COMMITTED", "EXACT_REPLAY"]
    intent_version: str = Field(pattern=r"^crop_activity_intent\.v[0-9]+$")
    intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_activity_identity(self):
        if self.entity_type.lower() not in {"crop_activity", "cropactivity"}:
            raise ValueError("accepted activity detail has invalid entity type")
        if self.entity_id != self.activity_id:
            raise ValueError("accepted activity detail identity mismatch")
        return self


class SyncBatchResponse(BaseModel):
    """Response from sync batch processing."""
    accepted: list[str]
    conflicts: list[ConflictInfo]
    failed: list[FailedInfo]
    accepted_details: list[AcceptedDetail] = Field(default_factory=list)
    total_processed: int


def process_validated_sync_events(
    *,
    events: list[PreflightEvent[SyncEventPayload] | SyncEventPayload],
    principal: AuthenticatedPrincipal,
    db: Session,
) -> SyncBatchResponse:
    """Authorize and process events that already passed lossless ingress.

    This seam is intentionally below the HTTP raw-body boundary. Production
    callers must not use it to bypass ``preflight_sync_request``.
    """
    events_data = []
    for item in events:
        if isinstance(item, PreflightEvent):
            event = item.validated
            canonical_envelope = item.canonical_envelope
        else:
            event = item
            canonical_envelope = None
        if (
            event.entity_type.lower() in {"crop_activity", "cropactivity"}
            and event.operation == "CREATE"
            and canonical_envelope is None
        ):
            raise RuntimeError(
                "Queued activity CREATE requires lossless ingress preflight"
            )
        events_data.append({
            "event_id": str(event.event_id),
            "entity_type": event.entity_type,
            "entity_id": (
                str(event.entity_id)
                if event.entity_id
                else None
            ),
            "operation": event.operation,
            "payload": event.payload,
            "version": event.version,
            "dependency_ids": [
                str(dependency_id)
                for dependency_id in event.dependency_ids
            ],
            "metadata": event.metadata,
            "_sync_envelope_canonical": canonical_envelope,
        })

    authorized_events, denied_events = authorize_sync_events(
        db,
        principal=principal,
        events=events_data,
    )

    def authorize_farmer(farmer_id) -> None:
        from app.modules.workflow.api import (
            _require_principal_can_operate_cycle_farmer,
        )

        _require_principal_can_operate_cycle_farmer(
            db,
            principal=principal,
            farmer_id=farmer_id,
        )

    result = service.process_sync_batch(
        db=db,
        tenant_id=principal.tenant_id,
        actor_id=str(principal.user_id),
        events=authorized_events,
        authorize_farmer=authorize_farmer,
    )
    result.failed.extend(denied_events)

    accepted_details = [
        AcceptedDetail(**detail)
        for detail in result.accepted_details
    ]
    accepted_ids = set(result.accepted)
    detail_event_ids = [str(detail.event_id) for detail in accepted_details]
    accepted_activity_ids = {
        str(event["event_id"])
        for event in authorized_events
        if str(event.get("entity_type") or "").lower()
        in {"crop_activity", "cropactivity"}
        and event.get("operation") == "CREATE"
        and str(event["event_id"]) in accepted_ids
    }
    if (
        len(detail_event_ids) != len(set(detail_event_ids))
        or any(event_id not in accepted_ids for event_id in detail_event_ids)
        or set(detail_event_ids) != accepted_activity_ids
    ):
        raise RuntimeError("Invalid accepted activity correlation")

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
        accepted_details=accepted_details,
        total_processed=len(events_data),
    )


def process_validated_sync_events_in_session(
    *,
    events: list[PreflightEvent[SyncEventPayload] | SyncEventPayload],
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
        events=logical_events,
        principal=principal,
    )
