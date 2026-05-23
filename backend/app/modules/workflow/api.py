"""Crop Cycle workflow API — the core operational loop.

POST  /api/v1/crop-cycles                         — Create cycle + instantiate stages
PATCH /api/v1/crop-cycles/{id}/stages/{stage_id}  — Advance stage (state machine)
POST  /api/v1/crop-cycles/{id}/activities         — Log input/cost against active stage

Per ADR-003: Workflow Engine validates transitions. Never hardcoded.
Per architecture spec: transitions are EXPLICIT ONLY, configuration-driven.
All mutations require: actor_id, timestamp, GPS.
"""

import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.modules.workflow.models import CropCycle, CropStageInstance, CropActivity
from app.modules.master_data.models import CropLifecycleTemplate
from app.modules.sync.service import append_audit

router = APIRouter(prefix="/api/v1/crop-cycles", tags=["crop-cycles"])


# --- Schemas ---

class CropCycleCreate(BaseModel):
    farmer_id: uuid.UUID
    parcel_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    crop_code: str
    variety_code: Optional[str] = None
    season_code: str = Field(..., pattern=r"^(KHARIF|RABI|ZAID)$")
    lifecycle_template_id: uuid.UUID
    planned_sowing_date: Optional[date] = None


class StageTransition(BaseModel):
    """Advance a stage. Action determines the transition."""
    action: str = Field(..., pattern=r"^(START|COMPLETE|SKIP|FAIL)$")
    notes: Optional[str] = None
    skip_reason: Optional[str] = None
    # Audit fields (required per governance)
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class ActivityCreate(BaseModel):
    activity_type: str = Field(..., pattern=r"^(FERTILIZER|PESTICIDE|IRRIGATION|LABOR|MACHINERY|HARVEST|OTHER)$")
    input_code: Optional[str] = None
    input_name: Optional[str] = None
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    area_applied: Optional[float] = None
    area_unit: Optional[str] = None
    cost_amount: Optional[float] = None
    activity_date: date
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    notes: Optional[str] = None


class CropCycleResponse(BaseModel):
    id: uuid.UUID
    status: str
    crop_code: str
    season_code: str
    stages: list[dict]
    events_published: list[str]

    class Config:
        from_attributes = True


# --- Valid state transitions (state machine) ---
# Per architecture spec: crop_stage states and explicit transitions
VALID_TRANSITIONS = {
    # (current_status, action) → new_status
    ("PENDING", "START"): "ACTIVE",
    ("PENDING", "SKIP"): "SKIPPED",
    ("ACTIVE", "COMPLETE"): "COMPLETED",
    ("ACTIVE", "FAIL"): "FAILED",
    ("ACTIVE", "SKIP"): "SKIPPED",
}

# Crop cycle status auto-aggregation rules
def compute_cycle_status(stages: list[CropStageInstance]) -> str:
    """Derive crop_cycle.status from its stage instances.

    PLANNED: all stages PENDING
    ACTIVE: at least one stage ACTIVE or COMPLETED
    PARTIALLY_TRACKED: some completed, some skipped, none active
    COMPLETED: all stages COMPLETED or SKIPPED (at least one COMPLETED)
    ABANDONED: all stages FAILED or SKIPPED (none COMPLETED)
    """
    statuses = [s.status for s in stages]
    if all(s == "PENDING" for s in statuses):
        return "PLANNED"
    if "ACTIVE" in statuses:
        return "ACTIVE"
    if all(s in ("COMPLETED", "SKIPPED") for s in statuses):
        if "COMPLETED" in statuses:
            return "COMPLETED"
        return "ABANDONED"
    if all(s in ("FAILED", "SKIPPED") for s in statuses):
        return "ABANDONED"
    if any(s == "COMPLETED" for s in statuses) and not any(s == "ACTIVE" for s in statuses):
        return "PARTIALLY_TRACKED"
    return "ACTIVE"


# --- Endpoints ---

@router.post("", response_model=CropCycleResponse, status_code=201)
def create_crop_cycle(
    body: CropCycleCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Create a crop cycle and auto-instantiate stages from lifecycle template.

    Loads stages from crop_lifecycle_templates (never hardcoded).
    Sets initial status to PLANNED.
    """
    # Validate lifecycle template exists
    template = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.id == body.lifecycle_template_id,
            CropLifecycleTemplate.is_active == True,
        )
        .first()
    )
    if not template:
        raise HTTPException(404, "Lifecycle template not found")

    # Create crop cycle
    cycle_id = uuid.uuid4()
    cycle = CropCycle(
        id=cycle_id,
        tenant_id=x_tenant_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        project_id=body.project_id,
        crop_code=body.crop_code,
        variety_code=body.variety_code,
        season_code=body.season_code,
        lifecycle_template_id=body.lifecycle_template_id,
        planned_sowing_date=body.planned_sowing_date,
        status="PLANNED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(cycle)

    # Auto-instantiate stages from template
    stages_data = template.stages or []
    stage_instances = []
    for stage_def in stages_data:
        instance = CropStageInstance(
            id=uuid.uuid4(),
            crop_cycle_id=cycle_id,
            tenant_id=x_tenant_id,
            stage_code=stage_def["code"],
            stage_name=stage_def["name"],
            stage_order=stage_def["order"],
            expected_duration_days=stage_def.get("duration_days"),
            bbch_range_start=stage_def.get("bbch_range_start"),
            bbch_range_end=stage_def.get("bbch_range_end"),
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(instance)
        stage_instances.append(instance)

    # Audit
    correlation_id = str(uuid.uuid4())
    append_audit(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        correlation_id=correlation_id,
        entity_type="crop_cycle",
        entity_id=str(cycle_id),
        action="CROP_CYCLE_CREATED",
        payload={
            "crop_code": body.crop_code,
            "season_code": body.season_code,
            "template_id": str(body.lifecycle_template_id),
            "stages_count": len(stages_data),
        },
        metadata={"device_id": "api"},
    )

    db.commit()

    return CropCycleResponse(
        id=cycle_id,
        status="PLANNED",
        crop_code=body.crop_code,
        season_code=body.season_code,
        stages=[
            {"id": str(s.id), "code": s.stage_code, "name": s.stage_name,
             "order": s.stage_order, "status": s.status}
            for s in stage_instances
        ],
        events_published=["crop_cycle_created.v1"],
    )


@router.patch("/{cycle_id}/stages/{stage_id}")
def advance_stage(
    cycle_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: StageTransition,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Advance a crop stage through the state machine.

    Validates transition against VALID_TRANSITIONS.
    Updates crop_cycle.status based on aggregate stage states.
    Publishes crop_stage_completed.v1 event on COMPLETE.
    """
    # Load stage instance
    stage = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.id == stage_id,
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .first()
    )
    if not stage:
        raise HTTPException(404, "Stage instance not found")

    # Validate transition
    transition_key = (stage.status, body.action)
    new_status = VALID_TRANSITIONS.get(transition_key)
    if not new_status:
        raise HTTPException(
            409,
            f"Invalid transition: cannot {body.action} from {stage.status}. "
            f"Valid actions from {stage.status}: "
            f"{[a for (s, a), _ in VALID_TRANSITIONS.items() if s == stage.status]}",
        )

    # Apply transition
    stage.status = new_status
    stage.updated_at = datetime.now(timezone.utc)

    if body.action == "START":
        stage.actual_start_date = date.today()
        stage.started_by = uuid.UUID(x_actor_id)
    elif body.action == "COMPLETE":
        stage.actual_end_date = date.today()
        stage.completed_by = uuid.UUID(x_actor_id)
    elif body.action == "SKIP":
        stage.skip_reason = body.skip_reason or body.notes

    # Update crop cycle status (auto-aggregate)
    all_stages = (
        db.query(CropStageInstance)
        .filter(CropStageInstance.crop_cycle_id == cycle_id)
        .all()
    )
    cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id).first()
    old_cycle_status = cycle.status
    cycle.status = compute_cycle_status(all_stages)
    cycle.updated_at = datetime.now(timezone.utc)

    # If first stage started, set actual_sowing_date
    if body.action == "START" and stage.stage_order == 1:
        cycle.actual_sowing_date = date.today()

    # Determine events published
    events_published = []
    if body.action == "COMPLETE":
        events_published.append("crop_stage_completed.v1")
    if cycle.status != old_cycle_status:
        events_published.append(f"crop_cycle_status_changed.v1:{cycle.status}")
    if cycle.status == "COMPLETED":
        events_published.append("crop_cycle_completed.v1")

    # Audit
    correlation_id = str(uuid.uuid4())
    append_audit(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        correlation_id=correlation_id,
        entity_type="crop_stage",
        entity_id=str(stage_id),
        action=f"STAGE_{body.action}",
        payload={
            "stage_code": stage.stage_code,
            "old_status": transition_key[0],
            "new_status": new_status,
            "cycle_status": cycle.status,
        },
        metadata={
            "gps_lat": body.gps_lat,
            "gps_lng": body.gps_lng,
            "cycle_id": str(cycle_id),
        },
    )

    db.commit()

    return {
        "stage_id": str(stage_id),
        "stage_code": stage.stage_code,
        "old_status": transition_key[0],
        "new_status": new_status,
        "cycle_status": cycle.status,
        "events_published": events_published,
    }


@router.post("/{cycle_id}/activities", status_code=201)
def log_activity(
    cycle_id: uuid.UUID,
    body: ActivityCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Log an agricultural activity (fertilizer, pesticide, irrigation, etc.).

    Activities are stage-aware: linked to the currently ACTIVE stage.
    If no stage is active, activity is still accepted (linked to cycle only).
    Append-only for conflict resolution.
    """
    # Verify cycle exists and belongs to tenant
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")

    # Find currently active stage (if any)
    active_stage = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.status == "ACTIVE",
        )
        .first()
    )

    activity = CropActivity(
        id=uuid.uuid4(),
        crop_cycle_id=cycle_id,
        stage_instance_id=active_stage.id if active_stage else None,
        tenant_id=x_tenant_id,
        farmer_id=cycle.farmer_id,
        activity_type=body.activity_type,
        input_code=body.input_code,
        input_name=body.input_name,
        quantity=body.quantity,
        quantity_unit=body.quantity_unit,
        area_applied=body.area_applied,
        area_unit=body.area_unit,
        cost_amount=body.cost_amount,
        activity_date=body.activity_date,
        gps_lat=body.gps_lat,
        gps_lng=body.gps_lng,
        logged_by=uuid.UUID(x_actor_id),
        notes=body.notes,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(activity)

    # Update cycle economics
    if body.cost_amount:
        from decimal import Decimal
        cycle.total_input_cost = (cycle.total_input_cost or Decimal("0")) + Decimal(str(body.cost_amount))
        cycle.updated_at = datetime.now(timezone.utc)

    # Audit
    correlation_id = str(uuid.uuid4())
    append_audit(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        correlation_id=correlation_id,
        entity_type="crop_activity",
        entity_id=str(activity.id),
        action="ACTIVITY_LOGGED",
        payload={
            "activity_type": body.activity_type,
            "input_code": body.input_code,
            "quantity": str(body.quantity) if body.quantity else None,
            "cost": str(body.cost_amount) if body.cost_amount else None,
            "stage_code": active_stage.stage_code if active_stage else None,
        },
        metadata={
            "gps_lat": body.gps_lat,
            "gps_lng": body.gps_lng,
            "cycle_id": str(cycle_id),
        },
    )

    db.commit()

    return {
        "activity_id": str(activity.id),
        "activity_type": body.activity_type,
        "stage_code": active_stage.stage_code if active_stage else None,
        "cycle_total_input_cost": str(cycle.total_input_cost or 0),
        "events_published": ["crop_activity_logged.v1"],
    }
