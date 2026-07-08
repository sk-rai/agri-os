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
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.modules.workflow.models import CropCycle, CropStageInstance, CropActivity
from app.modules.workflow.template_service import (
    find_published_workflow_template,
    workflow_template_metadata,
    workflow_version_to_stage_definitions,
    workflow_version_to_stage_definitions_for_scope,
)
from app.modules.master_data.models import Crop, CropLifecycleTemplate
from app.modules.farmer.models import Parcel
from app.modules.sync.service import append_audit

router = APIRouter(prefix="/api/v1/crop-cycles", tags=["crop-cycles"])


def _ensure_crop_cycle_workflow_version_column(db: Session) -> None:
    """Add workflow version pinning column in migration-light MVP environments."""
    db.execute(text(
        "ALTER TABLE crop_cycles "
        "ADD COLUMN IF NOT EXISTS workflow_template_version_id UUID "
        "REFERENCES workflow_template_versions(id)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_crop_cycle_workflow_version "
        "ON crop_cycles(workflow_template_version_id)"
    ))


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


class CropCycleCompleteRequest(BaseModel):
    notes: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class ActivityCreate(BaseModel):
    activity_type: str = Field(..., pattern=r"^(FERTILIZER|PESTICIDE|IRRIGATION|LABOR|MACHINERY|HARVEST|SEED|OTHER)$")
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
    # Irrigation-specific
    irrigation_source: Optional[str] = None
    duration_hours: Optional[float] = None


class CropCycleResponse(BaseModel):
    id: uuid.UUID
    parcel_id: Optional[uuid.UUID] = None
    farmer_id: Optional[uuid.UUID] = None
    status: str
    crop_code: str
    crop_name: Optional[str] = None
    season_code: str
    planned_sowing_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None  # Calculated from template
    workflow_template_version_id: Optional[uuid.UUID] = None
    workflow_template_version: Optional[str] = None
    workflow_template_pinning_status: str = "LEGACY_UNPINNED"
    inferred_current_stage: Optional[str] = None  # If sowing_date is in past
    stages: list[dict]
    events_published: list[str] = []

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


def finalize_crop_cycle_completion(
    cycle: CropCycle,
    stages: list[CropStageInstance],
    actor_id: str,
    completed_on: date,
) -> list[CropStageInstance]:
    """Mark the whole cycle complete when the final harvest is completed.

    Android treats COMPLETED crop cycles as read-only/history. If HARVEST is
    completed after users skipped ahead through testing, older PENDING/ACTIVE
    stages should no longer keep the cycle active.
    """
    auto_completed = []
    actor_uuid = uuid.UUID(actor_id)
    now = datetime.now(timezone.utc)

    for stage in stages:
        if stage.status != "COMPLETED":
            stage.status = "COMPLETED"
            stage.actual_start_date = stage.actual_start_date or completed_on
            stage.actual_end_date = stage.actual_end_date or completed_on
            stage.completed_by = stage.completed_by or actor_uuid
            stage.updated_at = now
            auto_completed.append(stage)

    cycle.status = "COMPLETED"
    cycle.actual_harvest_date = cycle.actual_harvest_date or completed_on
    cycle.updated_at = now
    return auto_completed


def build_crop_cycle_response(
    cycle: CropCycle,
    stages: list[CropStageInstance],
    crop_name: Optional[str] = None,
    events_published: Optional[list[str]] = None,
) -> dict:
    """Build Android-facing crop cycle response with calculated stage schedule."""
    sowing = cycle.planned_sowing_date or cycle.actual_sowing_date or date.today()
    cumulative_days = 0
    stage_schedule = []
    inferred_stage = None

    for s in stages:
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
            "actual_start_date": s.actual_start_date.isoformat() if s.actual_start_date else None,
            "actual_end_date": s.actual_end_date.isoformat() if s.actual_end_date else None,
        })
        cumulative_days += duration

    active_stage = next((s_info for s_info in stage_schedule if s_info["status"] == "ACTIVE"), None)
    if active_stage:
        inferred_stage = active_stage["code"]
    elif cycle.status == "COMPLETED" and stage_schedule:
        inferred_stage = stage_schedule[-1]["code"]
    elif sowing <= date.today():
        days_elapsed = (date.today() - sowing).days
        running_days = 0
        for s_info in stage_schedule:
            running_days += s_info["duration_days"]
            if days_elapsed <= running_days:
                inferred_stage = s_info["code"]
                break
        if not inferred_stage and stage_schedule:
            inferred_stage = stage_schedule[-1]["code"]

    expected_harvest = sowing + timedelta(days=cumulative_days)

    return {
        "id": str(cycle.id),
        "parcel_id": str(cycle.parcel_id) if cycle.parcel_id else None,
        "farmer_id": str(cycle.farmer_id) if cycle.farmer_id else None,
        "status": cycle.status,
        "crop_code": cycle.crop_code,
        "crop_name": crop_name,
        "season_code": cycle.season_code,
        "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
        "actual_sowing_date": cycle.actual_sowing_date.isoformat() if cycle.actual_sowing_date else None,
        "expected_harvest_date": expected_harvest.isoformat(),
        "actual_harvest_date": cycle.actual_harvest_date.isoformat() if cycle.actual_harvest_date else None,
        "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
        "workflow_template_pinning_status": "PINNED" if cycle.workflow_template_version_id else "LEGACY_UNPINNED",
        "inferred_current_stage": inferred_stage,
        "total_input_cost": str(cycle.total_input_cost) if cycle.total_input_cost else "0",
        "stages": stage_schedule,
        "events_published": events_published or [],
    }


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
    _ensure_crop_cycle_workflow_version_column(db)

    # Auto-derive farmer_id from actor (parcel owner or self-enrollment)
    farmer_id = body.farmer_id
    if not farmer_id:
        from app.modules.farmer.models import Farmer, Parcel
        # First: get farmer from the parcel (most reliable)
        parcel = db.query(Parcel).filter(Parcel.id == body.parcel_id).first()
        if parcel and parcel.farmer_id:
            # Verify this farmer actually exists in farmers table
            farmer_exists = db.query(Farmer).filter(Farmer.id == parcel.farmer_id).first()
            if farmer_exists:
                farmer_id = parcel.farmer_id

        # If parcel didn't resolve a valid farmer, try mobile number lookup
        if not farmer_id:
            from app.modules.auth.models import User
            user = db.query(User).filter(User.id == uuid.UUID(x_actor_id)).first()
            if user:
                farmer = db.query(Farmer).filter(
                    Farmer.mobile_number == user.mobile_number,
                    Farmer.tenant_id == x_tenant_id,
                ).first()
                if farmer:
                    farmer_id = farmer.id

        # Last resort: if we still can't find a farmer, check if there's ANY farmer for this tenant
        if not farmer_id:
            any_farmer = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id).first()
            if any_farmer:
                farmer_id = any_farmer.id

    if not farmer_id:
        raise HTTPException(400, "Cannot determine farmer. No farmer record found for this user/tenant.")

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

    # Resolve crop_code: if UUID was sent, convert to short code for storage
    resolved_crop_code = body.crop_code
    try:
        crop_uuid = uuid.UUID(body.crop_code)
        from app.modules.master_data.models import Crop as CropModel
        crop_by_id = db.query(CropModel).filter(CropModel.id == crop_uuid).first()
        if crop_by_id:
            resolved_crop_code = crop_by_id.code
    except (ValueError, AttributeError):
        resolved_crop_code = body.crop_code.upper()

    requested_sowing_date = body.planned_sowing_date or date.today()
    requested_season_code = body.season_code.upper()

    existing_cycles = (
        db.query(CropCycle)
        .filter(
            CropCycle.tenant_id == x_tenant_id,
            CropCycle.farmer_id == farmer_id,
            CropCycle.parcel_id == body.parcel_id,
            CropCycle.status != "ARCHIVED",
        )
        .all()
    )

    in_progress_cycle = next(
        (c for c in existing_cycles if c.status in ("PLANNED", "ACTIVE", "PARTIALLY_TRACKED")),
        None,
    )
    if in_progress_cycle:
        raise HTTPException(
            409,
            {
                "error": "PARCEL_HAS_IN_PROGRESS_CYCLE",
                "message": "Parcel already has an in-progress crop cycle",
                "cycle_id": str(in_progress_cycle.id),
                "status": in_progress_cycle.status,
                "crop_code": in_progress_cycle.crop_code,
                "season_code": in_progress_cycle.season_code,
            },
        )

    duplicate_completed_cycle = next(
        (
            c for c in existing_cycles
            if c.status == "COMPLETED"
            and c.crop_code == resolved_crop_code
            and c.season_code == requested_season_code
            and (c.planned_sowing_date or c.actual_sowing_date)
            and (c.planned_sowing_date or c.actual_sowing_date).year == requested_sowing_date.year
        ),
        None,
    )
    if duplicate_completed_cycle:
        raise HTTPException(
            409,
            {
                "error": "CYCLE_ALREADY_COMPLETED_THIS_SEASON",
                "message": "Parcel already has a completed cycle for this crop/season/year",
                "cycle_id": str(duplicate_completed_cycle.id),
                "status": duplicate_completed_cycle.status,
                "crop_code": duplicate_completed_cycle.crop_code,
                "season_code": duplicate_completed_cycle.season_code,
                "season_year": requested_sowing_date.year,
            },
        )

    # Resolve workflow version before creating the cycle, so the cycle is pinned
    # to the exact version used for stage/recommendation rendering.
    workflow_pair = find_published_workflow_template(
        db,
        crop_code=resolved_crop_code,
        season_code=requested_season_code,
        tenant_id=x_tenant_id,
        lifecycle_template_id=template.id,
    )
    pinned_workflow_version = workflow_pair[1] if workflow_pair else None

    # Create crop cycle
    cycle_id = uuid.uuid4()
    cycle = CropCycle(
        id=cycle_id,
        tenant_id=x_tenant_id,
        farmer_id=farmer_id,
        parcel_id=body.parcel_id,
        project_id=body.project_id,
        crop_code=resolved_crop_code,
        variety_code=body.variety_code,
        season_code=requested_season_code,
        lifecycle_template_id=template_id,
        workflow_template_version_id=pinned_workflow_version.id if pinned_workflow_version else None,
        planned_sowing_date=requested_sowing_date,
        status="PLANNED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(cycle)

    # Auto-instantiate stages from the pinned workflow version when available.
    # Fall back to the legacy JSONB lifecycle template to preserve existing crops.
    if pinned_workflow_version:
        stages_data = workflow_version_to_stage_definitions_for_scope(
            db,
            pinned_workflow_version.id,
            tenant_id=x_tenant_id,
            project_id=body.project_id,
        )
    else:
        stages_data = template.stages or []
    stage_instances = []
    for stage_def in stages_data:
        # stage_name can be a dict (i18n) or a plain string (legacy)
        raw_name = stage_def.get("name", "")
        stage_name = raw_name.get("en", str(raw_name)) if isinstance(raw_name, dict) else str(raw_name)

        instance = CropStageInstance(
            id=uuid.uuid4(),
            crop_cycle_id=cycle_id,
            tenant_id=x_tenant_id,
            stage_code=stage_def["code"],
            stage_name=stage_name,
            stage_order=stage_def["order"],
            expected_duration_days=stage_def.get("duration_days"),
            bbch_range_start=stage_def.get("bbch_range", [None, None])[0] if isinstance(stage_def.get("bbch_range"), list) else stage_def.get("bbch_range_start"),
            bbch_range_end=stage_def.get("bbch_range", [None, None])[1] if isinstance(stage_def.get("bbch_range"), list) else stage_def.get("bbch_range_end"),
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
            "crop_code": resolved_crop_code,
            "season_code": requested_season_code,
            "template_id": str(template_id),
            "workflow_template_version_id": str(pinned_workflow_version.id) if pinned_workflow_version else None,
            "workflow_template_pinning_status": "PINNED" if pinned_workflow_version else "LEGACY_UNPINNED",
            "stages_count": len(stages_data),
        },
        metadata={"device_id": "api"},
    )

    db.commit()

    # Calculate expected dates from template
    sowing = requested_sowing_date
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
    active_stage = next((s_info for s_info in stage_schedule if s_info["status"] == "ACTIVE"), None)
    if active_stage:
        inferred_stage = active_stage["code"]
    elif cycle.status == "COMPLETED" and stage_schedule:
        inferred_stage = stage_schedule[-1]["code"]
    elif sowing <= date.today():
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
        crop_code=resolved_crop_code,
        season_code=requested_season_code,
        planned_sowing_date=sowing,
        expected_harvest_date=expected_harvest,
        workflow_template_version_id=pinned_workflow_version.id if pinned_workflow_version else None,
        workflow_template_pinning_status="PINNED" if pinned_workflow_version else "LEGACY_UNPINNED",
        inferred_current_stage=inferred_stage,
        stages=stage_schedule,
        events_published=["crop_cycle_created.v1"],
    )




@router.get("")
def list_crop_cycles(
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List crop cycles for Android Home/parcel filtering."""
    _ensure_crop_cycle_workflow_version_column(db)
    query = db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id)
    if farmer_id:
        query = query.filter(CropCycle.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(CropCycle.parcel_id == parcel_id)
    if status:
        query = query.filter(CropCycle.status == status.upper())

    cycles = query.order_by(CropCycle.updated_at.desc(), CropCycle.created_at.desc()).all()
    crop_codes = sorted({c.crop_code for c in cycles if c.crop_code})
    crop_names = {
        crop.code: crop.canonical_name
        for crop in db.query(Crop).filter(Crop.code.in_(crop_codes)).all()
    } if crop_codes else {}

    result = []
    for cycle in cycles:
        stages = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == cycle.id,
                CropStageInstance.tenant_id == x_tenant_id,
            )
            .order_by(CropStageInstance.stage_order)
            .all()
        )
        result.append(build_crop_cycle_response(cycle, stages, crop_names.get(cycle.crop_code)))
    return result


@router.get("/eligible-parcels")
def list_eligible_parcels(
    farmer_id: uuid.UUID = Query(...),
    season: Optional[str] = Query(None),
    season_year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return parcels with crop-cycle eligibility and summary for Android dropdowns.

    For MVP Android compatibility, this endpoint defaults to tenant "default"
    when the tenant header is omitted. It also returns cycle-derived placeholder
    parcel rows when older test cycles reference parcels that are missing from
    the parcel master table.
    """
    target_year = season_year or date.today().year
    season_filter = season.upper() if season else None
    _ensure_crop_cycle_workflow_version_column(db)

    parcels = (
        db.query(Parcel)
        .filter(
            Parcel.tenant_id == x_tenant_id,
            Parcel.farmer_id == farmer_id,
            Parcel.status == "ACTIVE",
        )
        .order_by(Parcel.created_at.desc())
        .all()
    )

    cycles = (
        db.query(CropCycle)
        .filter(
            CropCycle.tenant_id == x_tenant_id,
            CropCycle.farmer_id == farmer_id,
        )
        .order_by(CropCycle.updated_at.desc(), CropCycle.created_at.desc())
        .all()
    )

    cycles_by_parcel = {}
    for cycle in cycles:
        cycles_by_parcel.setdefault(cycle.parcel_id, []).append(cycle)

    def cycle_summary(cycle: CropCycle) -> dict:
        stage_durations = [
            duration or 0
            for (duration,) in db.query(CropStageInstance.expected_duration_days)
            .filter(
                CropStageInstance.crop_cycle_id == cycle.id,
                CropStageInstance.tenant_id == x_tenant_id,
            )
            .order_by(CropStageInstance.stage_order)
            .all()
        ]
        sowing = cycle.planned_sowing_date or cycle.actual_sowing_date
        expected_harvest = sowing + timedelta(days=sum(stage_durations)) if sowing else cycle.expected_harvest_date
        return {
            "id": str(cycle.id),
            "crop_code": cycle.crop_code,
            "season_code": cycle.season_code,
            "status": cycle.status,
            "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
            "expected_harvest_date": expected_harvest.isoformat() if expected_harvest else None,
            "actual_harvest_date": cycle.actual_harvest_date.isoformat() if cycle.actual_harvest_date else None,
        }

    def eligibility_for(parcel_cycles: list[CropCycle]) -> tuple[bool, str, Optional[CropCycle], list[CropCycle]]:
        active_cycle = next((c for c in parcel_cycles if c.status == "ACTIVE"), None)
        completed_cycles = [c for c in parcel_cycles if c.status == "COMPLETED"]
        completed_same_season = [
            c for c in completed_cycles
            if (not season_filter or c.season_code == season_filter)
            and ((c.planned_sowing_date or c.actual_sowing_date) and (c.planned_sowing_date or c.actual_sowing_date).year == target_year)
        ]

        if active_cycle:
            return False, "HAS_ACTIVE_CYCLE", active_cycle, completed_cycles
        if completed_same_season:
            return False, "COMPLETED_THIS_SEASON", None, completed_cycles
        return True, "ELIGIBLE", None, completed_cycles

    def append_response_row(
        *,
        parcel_id: uuid.UUID,
        farmer_id_value: uuid.UUID,
        parcel_cycles: list[CropCycle],
        survey_number: Optional[str] = None,
        local_name: Optional[str] = None,
        area: Optional[str] = None,
        unit: Optional[str] = None,
        village_name: Optional[str] = None,
        ownership_type: Optional[str] = None,
        source: str = "parcel",
    ):
        eligible, eligibility_status, active_cycle, completed_cycles = eligibility_for(parcel_cycles)

        def format_decimal_label(value: Optional[str]) -> Optional[str]:
            if value is None:
                return None
            try:
                formatted = f"{float(value):.1f}"
                return formatted
            except (TypeError, ValueError):
                return str(value)

        def title_label(value: Optional[str]) -> Optional[str]:
            return str(value).replace("_", " ").title() if value else None

        if source == "cycle_only":
            label = f"Parcel {str(parcel_id)[:8]}"
        elif area and unit and ownership_type:
            area_label = format_decimal_label(area)
            label = f"{area_label} {title_label(unit)} ({title_label(ownership_type)})"
            if survey_number:
                label = f"{label} - {survey_number}"
            elif local_name:
                label = f"{label} - {local_name}"
        else:
            label = local_name or survey_number
            if not label and area and unit:
                label = f"{format_decimal_label(area)} {title_label(unit)} parcel"
            if not label:
                label = f"Parcel {str(parcel_id)[:8]}"

        response.append({
            "parcel_id": str(parcel_id),
            "farmer_id": str(farmer_id_value),
            "survey_number": survey_number,
            "local_name": local_name,
            "display_name": label,
            "label": label,
            "area": area,
            "unit": unit,
            "village_name": village_name,
            "ownership_type": ownership_type,
            "eligible": eligible,
            "eligibility_status": eligibility_status,
            "source": source,
            "active_cycle": cycle_summary(active_cycle) if active_cycle else None,
            "completed_cycles": [cycle_summary(c) for c in completed_cycles],
        })

    response = []
    known_parcel_ids = set()
    for parcel in parcels:
        known_parcel_ids.add(parcel.id)
        append_response_row(
            parcel_id=parcel.id,
            farmer_id_value=parcel.farmer_id,
            parcel_cycles=cycles_by_parcel.get(parcel.id, []),
            survey_number=parcel.survey_number,
            local_name=parcel.local_name,
            area=str(parcel.reported_area) if parcel.reported_area is not None else None,
            unit=parcel.reported_area_unit,
            village_name=parcel.village_name_manual,
            ownership_type=parcel.ownership_type,
        )

    for parcel_id, parcel_cycles in cycles_by_parcel.items():
        if parcel_id in known_parcel_ids:
            continue
        append_response_row(
            parcel_id=parcel_id,
            farmer_id_value=farmer_id,
            parcel_cycles=parcel_cycles,
            source="cycle_only",
        )

    return response


@router.get("/{cycle_id}/recommended-activities")
def get_recommended_activities(
    cycle_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return cycle-aware recommended activities with calculated dates.

    Merges the crop cycle stage schedule, lifecycle template recommendations,
    and logged activities for this cycle. Templates remain reference data; this
    endpoint is the Android-facing source for dated recommendations.
    """
    _ensure_crop_cycle_workflow_version_column(db)
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")

    template = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.id == cycle.lifecycle_template_id,
            CropLifecycleTemplate.is_active == True,
        )
        .first()
    )
    if not template:
        raise HTTPException(404, "Lifecycle template not found")

    stage_instances = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .order_by(CropStageInstance.stage_order)
        .all()
    )

    sowing = cycle.planned_sowing_date or cycle.actual_sowing_date or date.today()
    cumulative_days = 0
    stage_schedule = {}
    for stage in stage_instances:
        expected_start = sowing + timedelta(days=cumulative_days)
        duration = stage.expected_duration_days or 0
        expected_end = expected_start + timedelta(days=duration)
        anchor_date = stage.actual_start_date or expected_start
        stage_schedule[stage.stage_code] = {
            "id": str(stage.id),
            "code": stage.stage_code,
            "name": stage.stage_name,
            "order": stage.stage_order,
            "status": stage.status,
            "day_offset": cumulative_days,
            "duration_days": duration,
            "expected_start_date": expected_start,
            "expected_end_date": expected_end,
            "actual_start_date": stage.actual_start_date,
            "actual_end_date": stage.actual_end_date,
            "anchor_date": anchor_date,
        }
        cumulative_days += duration

    logged_activities = (
        db.query(CropActivity)
        .filter(
            CropActivity.crop_cycle_id == cycle_id,
            CropActivity.tenant_id == x_tenant_id,
        )
        .all()
    )
    stage_code_by_id = {stage.id: stage.stage_code for stage in stage_instances}
    logged_by_key = {}
    for activity in logged_activities:
        stage_code = stage_code_by_id.get(activity.stage_instance_id)
        key = (
            stage_code,
            (activity.activity_type or "").upper(),
            (activity.input_name or "").strip().lower(),
        )
        logged_by_key.setdefault(key, []).append(activity)

    recommendations = []
    template_stages = None
    if cycle.workflow_template_version_id:
        template_stages = workflow_version_to_stage_definitions_for_scope(
            db,
            cycle.workflow_template_version_id,
            tenant_id=x_tenant_id,
            project_id=cycle.project_id,
        )

    if template_stages is None:
        workflow_pair = find_published_workflow_template(
            db,
            crop_code=cycle.crop_code,
            season_code=cycle.season_code,
            tenant_id=x_tenant_id,
            lifecycle_template_id=template.id,
        )
        if workflow_pair:
            _, workflow_version = workflow_pair
            template_stages = workflow_version_to_stage_definitions_for_scope(
                db,
                workflow_version.id,
                tenant_id=x_tenant_id,
                project_id=cycle.project_id,
            )
        else:
            template_stages = template.stages or []
    for stage_def in template_stages:
        stage_code = stage_def.get("code")
        if not stage_code or stage_code not in stage_schedule:
            continue

        stage_info = stage_schedule[stage_code]
        raw_stage_name = stage_def.get("name")
        if isinstance(raw_stage_name, dict):
            stage_name = raw_stage_name.get("en") or next(iter(raw_stage_name.values()), stage_info["name"])
        else:
            stage_name = str(raw_stage_name or stage_info["name"])

        for rec in stage_def.get("recommended_activities", []) or []:
            day_offset = int(rec.get("day_offset") or 0)
            recommended_date = stage_info["anchor_date"] + timedelta(days=day_offset)
            key = (
                stage_code,
                (rec.get("activity_type") or "").upper(),
                (rec.get("input_name") or "").strip().lower(),
            )
            matched_logs = logged_by_key.get(key, [])

            recommendations.append({
                "stage_code": stage_code,
                "stage_name": stage_name,
                "stage_expected_start_date": stage_info["expected_start_date"].isoformat(),
                "stage_actual_start_date": stage_info["actual_start_date"].isoformat() if stage_info["actual_start_date"] else None,
                "anchor_date": stage_info["anchor_date"].isoformat(),
                "activity_type": rec.get("activity_type"),
                "input_name": rec.get("input_name"),
                "day_offset": day_offset,
                "recommended_date": recommended_date.isoformat(),
                "typical_quantity": rec.get("typical_quantity"),
                "typical_cost_per_acre": rec.get("typical_cost_per_acre"),
                "is_critical": rec.get("is_critical", False),
                "description": rec.get("description"),
                "logged": bool(matched_logs),
                "logged_activity_ids": [str(a.id) for a in matched_logs],
                "logged_activity_date": matched_logs[0].activity_date.isoformat() if matched_logs and matched_logs[0].activity_date else None,
                "logged_cost_amount": str(matched_logs[0].cost_amount) if matched_logs and matched_logs[0].cost_amount is not None else None,
            })

    return {
        "cycle_id": str(cycle.id),
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
        "actual_sowing_date": cycle.actual_sowing_date.isoformat() if cycle.actual_sowing_date else None,
        "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
        "workflow_template_pinning_status": "PINNED" if cycle.workflow_template_version_id else "LEGACY_UNPINNED",
        "recommendations": recommendations,
    }


@router.get("/{cycle_id}")
def get_crop_cycle(
    cycle_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Get a crop cycle with its stages and current status."""
    _ensure_crop_cycle_workflow_version_column(db)
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")

    stages = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .order_by(CropStageInstance.stage_order)
        .all()
    )
    crop = db.query(Crop).filter(Crop.code == cycle.crop_code).first()
    return build_crop_cycle_response(cycle, stages, crop.canonical_name if crop else None)


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
    _ensure_crop_cycle_workflow_version_column(db)
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

    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")
    if cycle.status == "COMPLETED":
        raise HTTPException(409, "Completed crop cycles are read-only")

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

    auto_completed_stages = []
    today = date.today()

    if body.action == "START":
        cycle_stages = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == cycle_id,
                CropStageInstance.tenant_id == x_tenant_id,
            )
            .order_by(CropStageInstance.stage_order)
            .all()
        )

        earlier_stages = [s for s in cycle_stages if s.stage_order < stage.stage_order]
        blocked_stages = [
            s for s in earlier_stages
            if s.status not in ("COMPLETED", "SKIPPED", "ACTIVE")
        ]
        if blocked_stages:
            raise HTTPException(
                409,
                "Cannot start stage before earlier stages are completed or skipped: "
                f"{[s.stage_code for s in blocked_stages]}",
            )

        later_active_stages = [
            s for s in cycle_stages
            if s.id != stage.id and s.stage_order > stage.stage_order and s.status == "ACTIVE"
        ]
        if later_active_stages:
            raise HTTPException(
                409,
                "Cannot start an earlier stage while later stages are active: "
                f"{[s.stage_code for s in later_active_stages]}",
            )

        # Keep a single ACTIVE stage invariant. If a user starts the next stage
        # while the previous one is still active, closing the previous stage
        # matches the field workflow expectation: NURSERY becomes COMPLETED when
        # TRANSPLANTING starts.
        for earlier_stage in earlier_stages:
            if earlier_stage.status == "ACTIVE":
                earlier_stage.status = "COMPLETED"
                earlier_stage.actual_end_date = earlier_stage.actual_end_date or today
                earlier_stage.completed_by = uuid.UUID(x_actor_id)
                earlier_stage.updated_at = datetime.now(timezone.utc)
                auto_completed_stages.append(earlier_stage)

    # Apply transition
    stage.status = new_status
    stage.updated_at = datetime.now(timezone.utc)

    if body.action == "START":
        stage.actual_start_date = today
        stage.started_by = uuid.UUID(x_actor_id)
    elif body.action == "COMPLETE":
        stage.actual_end_date = today
        stage.completed_by = uuid.UUID(x_actor_id)
    elif body.action == "SKIP":
        stage.skip_reason = body.skip_reason or body.notes
    # Update crop cycle status (auto-aggregate). Completing HARVEST is the
    # product-level closeout signal: it force-completes any earlier stages that
    # were left pending/active during testing and marks the cycle COMPLETED.
    all_stages = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .order_by(CropStageInstance.stage_order)
        .all()
    )
    old_cycle_status = cycle.status

    if body.action == "COMPLETE" and stage.stage_code == "HARVEST":
        auto_completed_stages.extend(
            finalize_crop_cycle_completion(cycle, all_stages, x_actor_id, today)
        )
    else:
        cycle.status = compute_cycle_status(all_stages)
        cycle.updated_at = datetime.now(timezone.utc)

    # If first stage started, set actual_sowing_date
    if body.action == "START" and stage.stage_order == 1:
        cycle.actual_sowing_date = date.today()

    # Determine events published
    events_published = []
    for auto_completed_stage in auto_completed_stages:
        events_published.append(f"crop_stage_completed.v1:{auto_completed_stage.stage_code}")
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
            "auto_completed_stage_codes": [s.stage_code for s in auto_completed_stages],
        },
        metadata={
            "gps_lat": body.gps_lat,
            "gps_lng": body.gps_lng,
            "cycle_id": str(cycle_id),
        },
    )

    db.commit()
    db.refresh(cycle)
    updated_stages = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .order_by(CropStageInstance.stage_order)
        .all()
    )
    crop = db.query(Crop).filter(Crop.code == cycle.crop_code).first()

    return {
        "stage_id": str(stage_id),
        "stage_code": stage.stage_code,
        "old_status": transition_key[0],
        "new_status": new_status,
        "cycle_status": cycle.status,
        "auto_completed_stage_codes": [s.stage_code for s in auto_completed_stages],
        "events_published": events_published,
        "crop_cycle": build_crop_cycle_response(
            cycle, updated_stages, crop.canonical_name if crop else None, events_published
        ),
    }


@router.post("/{cycle_id}/complete")
def complete_crop_cycle(
    cycle_id: uuid.UUID,
    body: Optional[CropCycleCompleteRequest] = None,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Explicitly complete a crop cycle and all its stages.

    This is a backend escape hatch for Android/product flows where the user
    finishes harvest and wants the cycle moved to history/read-only.
    """
    _ensure_crop_cycle_workflow_version_column(db)
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")

    stages = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
        )
        .order_by(CropStageInstance.stage_order)
        .all()
    )
    if not stages:
        raise HTTPException(409, "Cannot complete cycle without stages")

    old_cycle_status = cycle.status
    completed_on = date.today()
    auto_completed_stages = finalize_crop_cycle_completion(cycle, stages, x_actor_id, completed_on)

    events_published = [f"crop_stage_completed.v1:{s.stage_code}" for s in auto_completed_stages]
    if cycle.status != old_cycle_status:
        events_published.append(f"crop_cycle_status_changed.v1:{cycle.status}")
    events_published.append("crop_cycle_completed.v1")

    correlation_id = str(uuid.uuid4())
    append_audit(
        db=db,
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        correlation_id=correlation_id,
        entity_type="crop_cycle",
        entity_id=str(cycle_id),
        action="CROP_CYCLE_COMPLETED",
        payload={
            "old_status": old_cycle_status,
            "new_status": cycle.status,
            "auto_completed_stage_codes": [s.stage_code for s in auto_completed_stages],
        },
        metadata={
            "gps_lat": body.gps_lat if body else None,
            "gps_lng": body.gps_lng if body else None,
        },
    )

    db.commit()
    db.refresh(cycle)
    crop = db.query(Crop).filter(Crop.code == cycle.crop_code).first()
    return build_crop_cycle_response(
        cycle, stages, crop.canonical_name if crop else None, events_published
    )


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
    _ensure_crop_cycle_workflow_version_column(db)
    # Verify cycle exists and belongs to tenant
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")
    if cycle.status == "COMPLETED":
        raise HTTPException(409, "Completed crop cycles are read-only")

    # Find currently active stage (if any)
    active_stage = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == x_tenant_id,
            CropStageInstance.status == "ACTIVE",
        )
        .order_by(CropStageInstance.stage_order.desc())
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


@router.get("/{cycle_id}/activities")
def list_activities(
    cycle_id: uuid.UUID,
    stage_code: Optional[str] = Query(None, description="Filter by stage code"),
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List activities for a crop cycle, optionally filtered by stage or type."""
    query = db.query(CropActivity).filter(
        CropActivity.crop_cycle_id == cycle_id,
        CropActivity.tenant_id == x_tenant_id,
    )

    if stage_code:
        # Filter by stage code via stage instance join
        stage_ids = (
            db.query(CropStageInstance.id)
            .filter(
                CropStageInstance.crop_cycle_id == cycle_id,
                CropStageInstance.stage_code == stage_code.upper(),
            )
            .all()
        )
        stage_id_list = [s[0] for s in stage_ids]
        if stage_id_list:
            query = query.filter(CropActivity.stage_instance_id.in_(stage_id_list))
        else:
            return []

    if activity_type:
        query = query.filter(CropActivity.activity_type == activity_type.upper())

    activities = query.order_by(CropActivity.activity_date.desc()).all()

    # Build stage code lookup
    stage_map = {}
    stage_instances = db.query(CropStageInstance).filter(
        CropStageInstance.crop_cycle_id == cycle_id
    ).all()
    for s in stage_instances:
        stage_map[s.id] = s.stage_code

    return [
        {
            "id": str(a.id),
            "activity_type": a.activity_type,
            "input_name": a.input_name,
            "quantity": str(a.quantity) if a.quantity else None,
            "quantity_unit": a.quantity_unit,
            "cost_amount": str(a.cost_amount) if a.cost_amount else None,
            "activity_date": a.activity_date.isoformat() if a.activity_date else None,
            "stage_code": stage_map.get(a.stage_instance_id),
            "notes": a.notes,
        }
        for a in activities
    ]


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

    # Build stage schedule with day_offsets. Prefer normalized workflow tables,
    # falling back to legacy lifecycle JSON if a published workflow has not been seeded.
    workflow_pair = find_published_workflow_template(
        db,
        crop_code=crop_code.upper(),
        season_code=template.season_code,
        tenant_id="default",
        lifecycle_template_id=template.id,
    )
    workflow_metadata = None
    if workflow_pair:
        workflow_template, workflow_version = workflow_pair
        stages = workflow_version_to_stage_definitions_for_scope(db, workflow_version.id, tenant_id="default")
        workflow_metadata = workflow_template_metadata(workflow_template, workflow_version)
    else:
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
            "recommended_activities": s.get("recommended_activities", []),
            "icon": s.get("icon"),
            "color": s.get("color"),
        })
        cumulative += duration

    # Template-level metadata (stored in aliases field in the legacy model)
    metadata = workflow_metadata or (template.aliases if isinstance(template.aliases, dict) else {})

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
        "template_source": metadata.get("source", "legacy_lifecycle_template"),
        "workflow_template_id": metadata.get("workflow_template_id"),
        "workflow_template_version_id": metadata.get("workflow_template_version_id"),
        "workflow_template_version": metadata.get("workflow_template_version"),
        "stages": stage_schedule,
    }
