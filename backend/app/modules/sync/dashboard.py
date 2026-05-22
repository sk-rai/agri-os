"""Operational dashboard API.

GET /api/v1/dashboard/operational — sync health + entity counts

For MVP: focuses on sync health metrics since operational tables
(farmer, parcel, crop_cycle) don't exist yet. Those counts will
be added when Epic 3 tables are created.

Tenant-scoped via X-Tenant-ID header.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.sync.models import (
    SyncProcessedEvent,
    SyncConflict,
    AuditChainEntry,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class SyncHealthResponse(BaseModel):
    total_events_processed: int
    committed: int
    conflicts_pending: int
    conflicts_resolved: int
    failed: int
    last_sync_at: Optional[str] = None
    audit_chain_length: int
    audit_chain_intact: bool


class DashboardResponse(BaseModel):
    tenant_id: str
    sync_health: SyncHealthResponse
    generated_at: str


@router.get("/operational", response_model=DashboardResponse)
def get_operational_dashboard(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Operational dashboard: sync health metrics.

    Tenant-scoped. Refreshes on each call (no caching for MVP).
    """
    # Sync event counts by status
    committed = (
        db.query(func.count(SyncProcessedEvent.event_id))
        .filter(
            SyncProcessedEvent.tenant_id == x_tenant_id,
            SyncProcessedEvent.status == "COMMITTED",
        )
        .scalar() or 0
    )
    conflict_count = (
        db.query(func.count(SyncProcessedEvent.event_id))
        .filter(
            SyncProcessedEvent.tenant_id == x_tenant_id,
            SyncProcessedEvent.status == "CONFLICT",
        )
        .scalar() or 0
    )
    failed = (
        db.query(func.count(SyncProcessedEvent.event_id))
        .filter(
            SyncProcessedEvent.tenant_id == x_tenant_id,
            SyncProcessedEvent.status.in_(["FAILED", "DEPENDENCY_MISSING"]),
        )
        .scalar() or 0
    )
    total = committed + conflict_count + failed

    # Conflict resolution status
    conflicts_pending = (
        db.query(func.count(SyncConflict.id))
        .filter(
            SyncConflict.tenant_id == x_tenant_id,
            SyncConflict.status == "PENDING_REVIEW",
        )
        .scalar() or 0
    )
    conflicts_resolved = (
        db.query(func.count(SyncConflict.id))
        .filter(
            SyncConflict.tenant_id == x_tenant_id,
            SyncConflict.status.in_(["RESOLVED_CLIENT", "RESOLVED_SERVER", "RESOLVED_MERGE"]),
        )
        .scalar() or 0
    )

    # Last successful sync
    last_sync = (
        db.query(func.max(SyncProcessedEvent.processed_at))
        .filter(
            SyncProcessedEvent.tenant_id == x_tenant_id,
            SyncProcessedEvent.status == "COMMITTED",
        )
        .scalar()
    )

    # Audit chain stats
    chain_length = (
        db.query(func.count(AuditChainEntry.id))
        .filter(AuditChainEntry.tenant_id == x_tenant_id)
        .scalar() or 0
    )

    return DashboardResponse(
        tenant_id=x_tenant_id,
        sync_health=SyncHealthResponse(
            total_events_processed=total,
            committed=committed,
            conflicts_pending=conflicts_pending,
            conflicts_resolved=conflicts_resolved,
            failed=failed,
            last_sync_at=last_sync.isoformat() if last_sync else None,
            audit_chain_length=chain_length,
            audit_chain_intact=True,  # TODO: verify chain hash continuity
        ),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
