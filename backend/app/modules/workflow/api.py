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
    parcel_id: uuid.UUID
    farmer_id: Optional[uuid.UUID] = None  # Auto-derived from X-Actor-ID if not provided
    project_id: Optional[uuid.UUID] = None
    crop_code: str
    variety_code: Optional[str] = None
    season_code: str = Field(..., pattern=r"^(KHARIF|RABI|ZAID)$")
    lifecycle_template_id: Optional[uuid.UUID] = None  # Auto-looked up from crop_code + season_code
    planned_sowing_date: Optional[date] = None
    # Seed info (from form)
    seed_source: Optional[str] = None
    purchase_source: Optional[str] = None
    seed_brand: Optional[str] = None
    seed_quantity_kg: Optional[float] = None
    seed_price: Optional[float] = None


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
    planned_sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None  # Calculated from template
    inferred_current_stage: Optional[str] = None  # If sowing_date is in past
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
    Auto-derives farmer_id from X-Actor-ID and lifecycle_template_id from crop_code+season.
    """
    # Auto-derive farmer_id from actor (parcel owner or self-enrollment)
    farmer_id = body.farmer_id
    if not farmer_id:
        from app.modules.farmer.models import Farmer, Parcel
        # Try to get farmer from parcel
        parcel = db.query(Parcel).filter(Parcel.id == body.parcel_id).first()
        if parcel:
            farmer_id = parcel.farmer_id
        else:
            # Fallback: find farmer by actor's mobile
            from app.modules.auth.models import User
            user = db.query(User).filter(User.id == uuid.UUID(x_actor_id)).first()
            if user:
                farmer = db.query(Farmer).filter(
                    Farmer.mobile_number == user.mobile_number,
                    Farmer.tenant_id == x_tenant_id,
                ).first()
                if farmer:
                    farmer_id = farmer.id
    if not farmer_id:
        raise HTTPException(400, "Cannot determine farmer. Provide farmer_id or ensure parcel exists.")

    # Auto-lookup lifecycle template from crop_code + season_code
    template_id = body.lifecycle_template_id
    if not template_id:
        from app.modules.master_data.models import Crop
        # crop_code might be a UUID (from Android dropdown) or a code string
        crop = None
        try:
            crop_uuid = uuid.UUID(body.crop_code)
            crop = db.query(Crop).filter(Crop.id == crop_uuid).first()
        except (ValueError, AttributeError):
            crop = db.query(Crop).filter(Crop.code == body.crop_code.upper()).first()

        if crop:
            template = (
                db.query(CropLifecycleTemplate)
                .filter(
                    CropLifecycleTemplate.crop_id == crop.id,
                    CropLifecycleTemplate.season_code == body.season_code.upper(),
                    CropLifecycleTemplate.is_active == True,
                )
                .first()
            )
            if template:
                template_id = template.id

    # Validate lifecycle template exists
    if not template_id:
        raise HTTPException(404, f"No lifecycle template found for {body.crop_code}/{body.season_code}")

    template = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.id == template_id,
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
        farmer_id=farmer_id,
        parcel_id=body.parcel_id,
        project_id=body.project_id,
        crop_code=body.crop_code,
        variety_code=body.variety_code,
        season_code=body.season_code,
        lifecycle_template_id=template_id,
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
            "template_id": str(template_id),
            "stages_count": len(stages_data),
        },
        metadata={"device_id": "api"},
    )

    db.commit()

    # Calculate expected dates from template
    sowing = body.planned_sowing_date or date.today()
    cumulative_days = 0
    stage_schedule = []
    for s in stage_instances:
        expected_start = sowing + timedelta(days=cumulative_days)
        duration = s.expected_duration_days or 0
        expected_end = expected_start + timedelta(days=duration)
        stage_schedule.append({
            "id": str(s.id),
            "code": s.stage_code,
            "name": s.stage_name,
            "order": s.stage_order,
            "status": s.status,
            "day_offset": cumulative_days,
            "expected_start_date": expected_start.isoformat(),
            "expected_end_date": expected_end.isoformat(),
            "duration_days": duration,
        })
        cumulative_days += duration

    expected_harvest = sowing + timedelta(days=cumulative_days)

    # Infer current stage if sowing date is in the past
    inferred_stage = None
    if sowing <= date.today():
        days_elapsed = (date.today() - sowing).days
        running_days = 0
        for s_info in stage_schedule:
            running_days += s_info["duration_days"]
            if days_elapsed <= running_days:
                inferred_stage = s_info["code"]
                break
        if not inferred_stage and stage_schedule:
            inferred_stage = stage_schedule[-1]["code"]  # Past all stages

    return CropCycleResponse(
        id=cycle_id,
        status="PLANNED" if sowing > date.today() else "ACTIVE",
        crop_code=body.crop_code,
        season_code=body.season_code,
        planned_sowing_date=sowing,
        expected_harvest_date=expected_harvest,
        inferred_current_stage=inferred_stage,
        stages=stage_schedule,
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


# --- Crop Template Endpoint ---

@router.get("/templates/{crop_code}")
def get_crop_template(
    crop_code: str,
    season: Optional[str] = Query(None, description="Filter by season (KHARIF/RABI/ZAID)"),
    db: Session = Depends(get_db),
):
    """Get crop lifecycle template with stage definitions and durations.

    Returns stage codes with day_offset for timeline calculation.
    Android uses this to show stage timeline and calculate expected dates.
    """
    from app.modules.master_data.models import Crop

    # Find crop by code
    crop = db.query(Crop).filter(Crop.code == crop_code.upper()).first()
    if not crop:
        raise HTTPException(404, f"Crop '{crop_code}' not found")

    # Find template
    query = db.query(CropLifecycleTemplate).filter(
        CropLifecycleTemplate.crop_id == crop.id,
        CropLifecycleTemplate.is_active == True,
    )
    if season:
        query = query.filter(CropLifecycleTemplate.season_code == season.upper())

    template = query.filter(CropLifecycleTemplate.is_default == True).first()
    if not template:
        template = query.first()
    if not template:
        raise HTTPException(404, f"No lifecycle template found for {crop_code}")

    # Build stage schedule with day_offsets
    stages = template.stages or []
    cumulative = 0
    stage_schedule = []
    for s in stages:
        duration = s.get("duration_days", 0)
        stage_schedule.append({
            "code": s["code"],
            "name": s.get("name") if isinstance(s.get("name"), dict) else {"en": s.get("name", ""), "hi": s.get("name", "")},
            "order": s["order"],
            "day_offset": cumulative,
            "duration_days": duration,
            "stage_type": s.get("stage_type"),
            "phase": s.get("phase"),
            "bbch_range": s.get("bbch_range"),
            "propagation_step": s.get("propagation_step", False),
            "description": s.get("description"),
            "farmer_actions": s.get("farmer_actions", []),
            "typical_inputs": s.get("typical_inputs", []),
            "key_observations": s.get("key_observations", []),
            "icon": s.get("icon"),
            "color": s.get("color"),
        })
        cumulative += duration

    # Template-level metadata (stored in aliases field)
    metadata = template.aliases if isinstance(template.aliases, dict) else {}

    return {
        "template_id": str(template.id),
        "crop_code": crop_code.upper(),
        "crop_name": crop.canonical_name,
        "season_code": template.season_code,
        "total_duration_days": cumulative,
        "crop_group": metadata.get("crop_group"),
        "propagation_method": metadata.get("propagation_method"),
        "has_nursery": metadata.get("has_nursery", False),
        "date_label": metadata.get("date_label", {"en": "Sowing Date", "hi": "बुवाई की तारीख"}),
        "staging_system": metadata.get("staging_system"),
        "stages": stage_schedule,
    }
