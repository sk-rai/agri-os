"""Conflict resolution API.

GET  /api/v1/sync/conflicts         — List pending conflicts
GET  /api/v1/sync/conflicts/{id}    — Get conflict detail
PATCH /api/v1/sync/conflicts/{id}   — Resolve a conflict

Per ADR-007: Resolution strategies are MANUAL_REVIEW, SEMANTIC_MERGE,
APPEND_ONLY, SERVER_AUTHORITY. Operator chooses accept_client or accept_server.

Per Security Framework: every resolution is audit-logged with actor + timestamp.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.modules.sync.models import SyncConflict
from app.modules.sync.service import append_audit

router = APIRouter(prefix="/api/v1/sync/conflicts", tags=["conflicts"])


# --- Schemas ---

class ResolutionStrategy(str, Enum):
    ACCEPT_CLIENT = "ACCEPT_CLIENT"
    ACCEPT_SERVER = "ACCEPT_SERVER"
    SEMANTIC_MERGE = "SEMANTIC_MERGE"


class ConflictListItem(BaseModel):
    id: UUID
    event_id: UUID
    entity_type: str
    entity_id: UUID
    conflict_type: str
    resolution_strategy: Optional[str] = None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class ConflictDetail(BaseModel):
    id: UUID
    event_id: UUID
    entity_type: str
    entity_id: UUID
    conflict_type: str
    client_payload: dict
    server_payload: Optional[dict] = None
    resolution_strategy: Optional[str] = None
    status: str
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[UUID] = None

    class Config:
        from_attributes = True


class ResolveRequest(BaseModel):
    strategy: ResolutionStrategy
    comment: Optional[str] = Field(None, max_length=500)


class ResolveResponse(BaseModel):
    status: str
    strategy: str
    conflict_id: UUID


# --- Endpoints ---

@router.get("", response_model=list[ConflictListItem])
def list_conflicts(
    status: Optional[str] = Query("PENDING_REVIEW", description="Filter by status"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List conflicts for this tenant, filtered by status."""
    query = db.query(SyncConflict).filter(SyncConflict.tenant_id == x_tenant_id)

    if status:
        query = query.filter(SyncConflict.status == status)
    if entity_type:
        query = query.filter(SyncConflict.entity_type == entity_type)

    conflicts = (
        query
        .order_by(SyncConflict.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        ConflictListItem(
            id=c.id,
            event_id=c.event_id,
            entity_type=c.entity_type,
            entity_id=c.entity_id,
            conflict_type=c.conflict_type,
            resolution_strategy=c.resolution_strategy,
            status=c.status,
            created_at=c.created_at.isoformat(),
        )
        for c in conflicts
    ]


@router.get("/{conflict_id}", response_model=ConflictDetail)
def get_conflict(
    conflict_id: UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Get full conflict detail including client and server payloads."""
    conflict = (
        db.query(SyncConflict)
        .filter(
            SyncConflict.id == conflict_id,
            SyncConflict.tenant_id == x_tenant_id,
        )
        .first()
    )
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")

    return ConflictDetail(
        id=conflict.id,
        event_id=conflict.event_id,
        entity_type=conflict.entity_type,
        entity_id=conflict.entity_id,
        conflict_type=conflict.conflict_type,
        client_payload=conflict.client_payload,
        server_payload=conflict.server_payload,
        resolution_strategy=conflict.resolution_strategy,
        status=conflict.status,
        created_at=conflict.created_at.isoformat(),
        resolved_at=conflict.resolved_at.isoformat() if conflict.resolved_at else None,
        resolved_by=conflict.resolved_by,
    )


@router.patch("/{conflict_id}", response_model=ResolveResponse)
def resolve_conflict(
    conflict_id: UUID,
    body: ResolveRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Resolve a pending conflict.

    For MVP: updates conflict status and logs to audit chain.
    Actual entity mutation (applying client_payload to operational tables)
    will be added when those tables exist.

    Per governance: every resolution is immutably audit-logged.
    """
    conflict = (
        db.query(SyncConflict)
        .filter(
            SyncConflict.id == conflict_id,
            SyncConflict.tenant_id == x_tenant_id,
            SyncConflict.status == "PENDING_REVIEW",
        )
        .first()
    )
    if not conflict:
        raise HTTPException(
            status_code=404,
            detail="Conflict not found or already resolved",
        )

    # Map strategy to resolution status
    import uuid as uuid_mod
    status_map = {
        ResolutionStrategy.ACCEPT_CLIENT: "RESOLVED_CLIENT",
        ResolutionStrategy.ACCEPT_SERVER: "RESOLVED_SERVER",
        ResolutionStrategy.SEMANTIC_MERGE: "RESOLVED_MERGE",
    }

    conflict.status = status_map[body.strategy]
    conflict.resolved_at = datetime.now(timezone.utc)
    conflict.resolved_by = uuid_mod.UUID(x_actor_id)

    # Audit the resolution
    correlation_id = str(uuid_mod.uuid4())
    append_audit(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        correlation_id=correlation_id,
        entity_type=conflict.entity_type,
        entity_id=str(conflict.entity_id),
        action="CONFLICT_RESOLVED",
        payload={
            "conflict_id": str(conflict_id),
            "strategy": body.strategy.value,
            "comment": body.comment,
            "conflict_type": conflict.conflict_type,
        },
        metadata={"resolution_strategy": body.strategy.value},
    )

    db.commit()

    return ResolveResponse(
        status="resolved",
        strategy=body.strategy.value,
        conflict_id=conflict_id,
    )
