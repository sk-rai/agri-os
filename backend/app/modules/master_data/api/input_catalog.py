"""Read-only agricultural input catalog APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, AgriculturalInputAuditEvent, InputCategory, ProjectInputAssignment, ProjectInputAssignmentAuditEvent
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateRecommendation,
    WorkflowTemplateStage,
    WorkflowTemplateVersion,
)
from app.modules.master_data.input_assignment_service import (
    assignment_map,
    explicit_allowlist_mode,
    input_assignment_decision,
    project_crop_scope,
    project_input_assignments,
)

router = APIRouter(prefix="/api/v1/input-catalog", tags=["input-catalog"])


class ProjectInputAssignmentUpdate(BaseModel):
    enabled: bool
    display_order: Optional[int] = None
    reason: Optional[str] = None
    metadata: Optional[dict] = None


class InputArchiveRequest(BaseModel):
    reason: Optional[str] = None


class AgriculturalInputUpdate(BaseModel):
    canonical_name: Optional[str] = Field(None, min_length=1, max_length=200)
    brand_name: Optional[str] = Field(None, max_length=200)
    composition: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    standard_weight: Optional[str] = None
    applicable_crops: Optional[list[str]] = None
    application_method: Optional[str] = None
    safety_instructions: Optional[str] = None
    aliases: Optional[list[dict[str, str]]] = None
    change_reason: Optional[str] = None

    @field_validator("applicable_crops")
    @classmethod
    def normalize_crops(cls, value):
        if value is None:
            return None
        return sorted({crop.strip().upper() for crop in value if crop and crop.strip()})

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value):
        return value.strip() if value else value

    @field_validator("standard_weight")
    @classmethod
    def validate_standard_weight(cls, value):
        if value in (None, ""):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("standard_weight must be numeric")
        if parsed < 0:
            raise ValueError("standard_weight must be non-negative")
        return str(parsed)



class AgriculturalInputCreate(AgriculturalInputUpdate):
    code: str = Field(..., min_length=2, max_length=50)
    category_code: str = Field(..., min_length=2, max_length=30)
    canonical_name: str = Field(..., min_length=1, max_length=200)
    unit: str = Field(..., min_length=1, max_length=20)

    @field_validator("code", "category_code")
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper().replace(" ", "_")

def _actor_uuid(value: Optional[str]):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


def _assignment_snapshot(assignment: Optional[ProjectInputAssignment]) -> Optional[dict]:
    if not assignment:
        return None
    return {
        "id": str(assignment.id),
        "tenant_id": assignment.tenant_id,
        "project_id": str(assignment.project_id),
        "input_id": str(assignment.input_id),
        "input_code": assignment.input_code,
        "enabled": assignment.enabled,
        "display_order": assignment.display_order,
        "reason": assignment.reason,
        "effective_from": assignment.effective_from.isoformat() if assignment.effective_from else None,
        "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "metadata": assignment.metadata_ or {},
        "is_active": assignment.is_active,
    }


def _audit_payload(event: ProjectInputAssignmentAuditEvent) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "project_id": str(event.project_id),
        "input_code": event.input_code,
        "assignment_id": str(event.assignment_id) if event.assignment_id else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "action": event.action,
        "before": event.before_payload,
        "after": event.after_payload,
        "reason": event.reason,
        "metadata": event.metadata_ or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _input_audit_payload(event: AgriculturalInputAuditEvent) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "input_id": str(event.input_id),
        "input_code": event.input_code,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "action": event.action,
        "before": event.before_payload,
        "after": event.after_payload,
        "reason": event.reason,
        "metadata": event.metadata_ or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _record_input_audit(
    db: Session,
    *,
    tenant_id: str,
    item: AgriculturalInput,
    actor_id,
    action: str,
    before: Optional[dict],
    after: Optional[dict],
    reason: Optional[str],
    metadata: Optional[dict] = None,
) -> None:
    db.add(AgriculturalInputAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        input_id=item.id,
        input_code=item.code,
        actor_id=actor_id,
        action=action,
        before_payload=before,
        after_payload=after,
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))


def _record_input_assignment_audit(
    db: Session,
    *,
    tenant_id: str,
    project_id: uuid.UUID,
    input_code: str,
    assignment_id: uuid.UUID,
    actor_id,
    action: str,
    before: Optional[dict],
    after: Optional[dict],
    reason: Optional[str],
    metadata: Optional[dict] = None,
) -> None:
    db.add(ProjectInputAssignmentAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        input_code=input_code,
        assignment_id=assignment_id,
        actor_id=actor_id,
        action=action,
        before_payload=before,
        after_payload=after,
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))

def category_payload(category: InputCategory) -> dict:
    return {
        "id": str(category.id),
        "code": category.code,
        "canonical_name": category.canonical_name,
        "description": category.description,
        "aliases": category.aliases or [],
    }


def input_payload(item: AgriculturalInput) -> dict:
    return {
        "id": str(item.id),
        "code": item.code,
        "category_code": item.category.code if item.category else None,
        "category_name": item.category.canonical_name if item.category else None,
        "canonical_name": item.canonical_name,
        "brand_name": item.brand_name,
        "composition": item.composition,
        "unit": item.unit,
        "standard_weight": str(item.standard_weight) if item.standard_weight is not None else None,
        "applicable_crops": item.applicable_crops or [],
        "application_method": item.application_method,
        "safety_instructions": item.safety_instructions,
        "aliases": item.aliases or [],
        "is_active": item.is_active,
    }


@router.get("/categories")
def list_input_categories(db: Session = Depends(get_db)):
    categories = (
        db.query(InputCategory)
        .filter(InputCategory.is_active == True)
        .order_by(InputCategory.code)
        .all()
    )
    return {
        "schema_version": "1.0.0",
        "count": len(categories),
        "categories": [category_payload(category) for category in categories],
    }


@router.post("/inputs")
def create_input(
    body: AgriculturalInputCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    existing = db.query(AgriculturalInput).filter(AgriculturalInput.code == body.code).first()
    if existing:
        raise HTTPException(409, f"Input '{body.code}' already exists")
    category = db.query(InputCategory).filter(
        InputCategory.code == body.category_code,
        InputCategory.is_active == True,
    ).first()
    if not category:
        raise HTTPException(404, f"Input category '{body.category_code}' not found")
    item = AgriculturalInput(
        id=uuid.uuid4(),
        code=body.code,
        category_id=category.id,
        canonical_name=body.canonical_name.strip(),
        unit=body.unit.strip(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    _apply_input_update(item, body)
    item.is_active = True
    db.add(item)
    db.flush()
    db.refresh(item)
    after = input_payload(item)
    _record_input_audit(
        db,
        tenant_id=x_tenant_id,
        item=item,
        actor_id=_actor_uuid(x_actor_id),
        action="CREATE_INPUT",
        before=None,
        after=after,
        reason=body.change_reason,
        metadata={"source": "admin_api"},
    )
    db.commit()
    db.refresh(item)
    return input_payload(item)


@router.get("/inputs")
def list_inputs(
    category: Optional[str] = Query(None),
    crop_code: Optional[str] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    q: Optional[str] = Query(None, description="Case-insensitive search over code/name/composition"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = db.query(AgriculturalInput).join(InputCategory)
    if not include_inactive:
        query = query.filter(AgriculturalInput.is_active == True)
    if category:
        query = query.filter(InputCategory.code == category.upper())
    project_scope = project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    assignments = project_input_assignments(db, tenant_id=x_tenant_id, project_id=project_id)
    assignments_by_code = assignment_map(assignments)
    explicit_allowlist = explicit_allowlist_mode(assignments)
    if crop_code:
        crop = crop_code.upper()
        if project_scope is not None and crop not in project_scope:
            return {
                "schema_version": "1.0.0",
                "project_id": str(project_id) if project_id else None,
                "project_crop_scope": sorted(project_scope),
                "filter_policy": "PROJECT_CROP_SCOPE",
                "count": 0,
                "inputs": [],
            }
        # PostgreSQL ARRAY contains a single crop code.
        query = query.filter(AgriculturalInput.applicable_crops.contains([crop]))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AgriculturalInput.code.ilike(pattern)
            | AgriculturalInput.canonical_name.ilike(pattern)
            | AgriculturalInput.composition.ilike(pattern)
        )
    inputs = query.order_by(InputCategory.code, AgriculturalInput.canonical_name).all()
    if project_id:
        inputs = [
            item for item in inputs
            if input_assignment_decision(
                item,
                project_crop_scope=project_scope,
                assignments_by_code=assignments_by_code,
                explicit_allowlist=explicit_allowlist,
                crop_code=crop_code,
            )["visible"]
        ]
    return {
        "schema_version": "1.0.0",
        "project_id": str(project_id) if project_id else None,
        "project_crop_scope": sorted(project_scope) if project_scope is not None else None,
        "filter_policy": "PROJECT_ASSIGNMENT" if project_id else "GLOBAL_CATALOG",
        "explicit_assignment_scope": explicit_allowlist if project_id else False,
        "count": len(inputs),
        "inputs": [input_payload(item) for item in inputs],
    }


def _input_assignment_payload(item: AgriculturalInput, decision: dict) -> dict:
    payload = input_payload(item)
    payload.update({
        "visible": decision["visible"],
        "assignment_rule": decision["assignment_rule"],
        "assignment_reason": decision["assignment_reason"],
        "crop_scope_allowed": decision["crop_scope_allowed"],
        "assignment_scope": decision["assignment_scope"],
        "configured_enabled": decision["configured_enabled"],
        "display_order": decision["display_order"],
        "reason": decision["reason"],
    })
    return payload


@router.get("/projects/{project_id}/input-assignments")
def get_project_input_assignments(
    project_id: uuid.UUID,
    category: Optional[str] = Query(None),
    crop_code: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    project_scope = project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    assignments = project_input_assignments(db, tenant_id=x_tenant_id, project_id=project_id)
    assignments_by_code = assignment_map(assignments)
    explicit_allowlist = explicit_allowlist_mode(assignments)

    query = db.query(AgriculturalInput).join(InputCategory).filter(AgriculturalInput.is_active == True)
    if category:
        query = query.filter(InputCategory.code == category.upper())
    if crop_code:
        query = query.filter(AgriculturalInput.applicable_crops.contains([crop_code.upper()]))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AgriculturalInput.code.ilike(pattern)
            | AgriculturalInput.canonical_name.ilike(pattern)
            | AgriculturalInput.composition.ilike(pattern)
        )
    inputs = query.order_by(InputCategory.code, AgriculturalInput.canonical_name).all()
    rows = [
        _input_assignment_payload(
            item,
            input_assignment_decision(
                item,
                project_crop_scope=project_scope,
                assignments_by_code=assignments_by_code,
                explicit_allowlist=explicit_allowlist,
                crop_code=crop_code,
            ),
        )
        for item in inputs
    ]
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "project_crop_scope": sorted(project_scope) if project_scope is not None else None,
        "explicit_assignment_scope": explicit_allowlist,
        "counts": {
            "total": len(rows),
            "android_visible": sum(1 for row in rows if row["visible"]),
            "disabled_by_project": sum(1 for row in rows if row["assignment_rule"] == "DISABLED_BY_PROJECT"),
            "not_assigned": sum(1 for row in rows if row["assignment_rule"] == "NOT_ASSIGNED"),
            "blocked_by_crop_scope": sum(1 for row in rows if row["assignment_rule"] == "BLOCKED_BY_CROP_SCOPE"),
            "implicit_crop_scope": sum(1 for row in rows if row["assignment_rule"] == "IMPLICIT_CROP_SCOPE"),
        },
        "inputs": rows,
    }


@router.get("/projects/{project_id}/input-assignments/audit")
def get_project_input_assignment_audit(
    project_id: uuid.UUID,
    input_code: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    query = db.query(ProjectInputAssignmentAuditEvent).filter(
        ProjectInputAssignmentAuditEvent.tenant_id == x_tenant_id,
        ProjectInputAssignmentAuditEvent.project_id == project_id,
        ProjectInputAssignmentAuditEvent.is_active == True,
    )
    if input_code:
        query = query.filter(ProjectInputAssignmentAuditEvent.input_code == input_code.upper())
    if action:
        query = query.filter(ProjectInputAssignmentAuditEvent.action == action.upper())
    events = query.order_by(ProjectInputAssignmentAuditEvent.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "count": len(events),
        "events": [_audit_payload(event) for event in events],
    }


@router.put("/projects/{project_id}/input-assignments/{input_code}")
def upsert_project_input_assignment(
    project_id: uuid.UUID,
    input_code: str,
    body: ProjectInputAssignmentUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    item = db.query(AgriculturalInput).filter(
        AgriculturalInput.code == input_code.upper(),
        AgriculturalInput.is_active == True,
    ).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")

    assignment = db.query(ProjectInputAssignment).filter(
        ProjectInputAssignment.tenant_id == x_tenant_id,
        ProjectInputAssignment.project_id == project_id,
        ProjectInputAssignment.input_code == item.code,
    ).first()
    before = _assignment_snapshot(assignment)
    if not assignment:
        assignment = ProjectInputAssignment(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            project_id=project_id,
            input_id=item.id,
            input_code=item.code,
            created_at=datetime.now(timezone.utc),
        )
        db.add(assignment)
    assignment.input_id = item.id
    assignment.enabled = body.enabled
    assignment.display_order = body.display_order if body.display_order is not None else (assignment.display_order or 1000)
    assignment.reason = body.reason
    if body.metadata is not None:
        assignment.metadata_ = body.metadata
    assignment.is_active = True
    assignment.updated_at = datetime.now(timezone.utc)
    after = _assignment_snapshot(assignment)
    if before is None:
        action = "CREATE_INPUT_ASSIGNMENT"
    elif before.get("enabled") != body.enabled:
        action = "ENABLE_INPUT" if body.enabled else "DISABLE_INPUT"
    else:
        action = "UPDATE_INPUT_ASSIGNMENT"
    _record_input_assignment_audit(
        db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        input_code=item.code,
        assignment_id=assignment.id,
        actor_id=_actor_uuid(x_actor_id),
        action=action,
        before=before,
        after=after,
        reason=body.reason,
        metadata={"source": "admin_api"},
    )
    db.commit()
    return get_project_input_assignments(project_id=project_id, category=None, crop_code=None, q=None, db=db, x_tenant_id=x_tenant_id)


def _apply_input_update(item: AgriculturalInput, body: AgriculturalInputUpdate) -> None:
    data = body.model_dump(exclude_unset=True)
    for field in ["canonical_name", "brand_name", "composition", "unit", "application_method", "safety_instructions", "aliases"]:
        if field in data:
            setattr(item, field, data[field])
    if "standard_weight" in data:
        item.standard_weight = Decimal(data["standard_weight"]) if data["standard_weight"] is not None else None
    if "applicable_crops" in data:
        item.applicable_crops = data["applicable_crops"] or []
    item.updated_at = datetime.now(timezone.utc)


def _input_reference_summary(db: Session, input_code: str) -> dict:
    code = input_code.upper()
    workflow_count = db.query(WorkflowTemplateRecommendation).filter(
        WorkflowTemplateRecommendation.input_code == code,
        WorkflowTemplateRecommendation.is_active == True,
    ).count()
    assignment_count = db.query(ProjectInputAssignment).filter(
        ProjectInputAssignment.input_code == code,
        ProjectInputAssignment.is_active == True,
    ).count()
    return {
        "workflow_recommendations": workflow_count,
        "project_assignments": assignment_count,
        "total": workflow_count + assignment_count,
    }


def _input_reference_details(db: Session, input_code: str) -> dict:
    code = input_code.upper()
    workflow_rows = (
        db.query(
            WorkflowTemplateRecommendation,
            WorkflowTemplateStage,
            WorkflowTemplateVersion,
            WorkflowTemplate,
        )
        .join(WorkflowTemplateStage, WorkflowTemplateStage.id == WorkflowTemplateRecommendation.template_stage_id)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.id == WorkflowTemplateStage.template_version_id)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id)
        .filter(
            WorkflowTemplateRecommendation.input_code == code,
            WorkflowTemplateRecommendation.is_active == True,
        )
        .order_by(
            WorkflowTemplate.crop_code,
            WorkflowTemplate.season_code,
            WorkflowTemplateVersion.version_number,
            WorkflowTemplateStage.stage_order,
            WorkflowTemplateRecommendation.sort_order,
        )
        .all()
    )
    assignment_rows = (
        db.query(ProjectInputAssignment, Project)
        .join(Project, Project.id == ProjectInputAssignment.project_id)
        .filter(
            ProjectInputAssignment.input_code == code,
            ProjectInputAssignment.is_active == True,
        )
        .order_by(Project.name, ProjectInputAssignment.display_order)
        .all()
    )
    return {
        "workflow_recommendations": [
            {
                "recommendation_id": str(recommendation.id),
                "workflow_template_id": str(template.id),
                "workflow_code": template.code,
                "workflow_name": template.canonical_name,
                "crop_code": template.crop_code,
                "season_code": template.season_code,
                "workflow_template_version_id": str(version.id),
                "version_number": version.version_number,
                "version_status": version.status,
                "stage_id": str(stage.id),
                "stage_code": stage.stage_code,
                "stage_name": stage.stage_name,
                "activity_type": recommendation.activity_type,
                "input_name": recommendation.input_name,
                "day_offset": recommendation.day_offset,
                "is_critical": recommendation.is_critical,
            }
            for recommendation, stage, version, template in workflow_rows
        ],
        "project_assignments": [
            {
                "assignment_id": str(assignment.id),
                "project_id": str(project.id),
                "project_name": project.name,
                "project_status": project.status,
                "tenant_id": assignment.tenant_id,
                "enabled": assignment.enabled,
                "display_order": assignment.display_order,
                "reason": assignment.reason,
            }
            for assignment, project in assignment_rows
        ],
    }


@router.get("/inputs/{input_code}/references")
def get_input_references(input_code: str, db: Session = Depends(get_db)):
    item = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.code == input_code.upper())
        .first()
    )
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    return {
        "schema_version": "1.0.0",
        "input_code": item.code,
        "references": _input_reference_summary(db, item.code),
        "usage": _input_reference_details(db, item.code),
    }


@router.post("/inputs/{input_code}/archive")
def archive_input(
    input_code: str,
    body: InputArchiveRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper()).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    references = _input_reference_summary(db, item.code)
    if references["total"] > 0:
        raise HTTPException(409, {
            "message": "Input is referenced and cannot be archived safely.",
            "references": references,
        })
    before = input_payload(item)
    item.is_active = False
    item.updated_at = datetime.now(timezone.utc)
    after = input_payload(item)
    if before != after:
        _record_input_audit(
            db,
            tenant_id=x_tenant_id,
            item=item,
            actor_id=_actor_uuid(x_actor_id),
            action="ARCHIVE_INPUT",
            before=before,
            after=after,
            reason=body.reason,
            metadata={"source": "admin_api", "references": references},
        )
    db.commit()
    db.refresh(item)
    return input_payload(item)


@router.post("/inputs/{input_code}/restore")
def restore_input(
    input_code: str,
    body: InputArchiveRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper()).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    before = input_payload(item)
    item.is_active = True
    item.updated_at = datetime.now(timezone.utc)
    after = input_payload(item)
    if before != after:
        _record_input_audit(
            db,
            tenant_id=x_tenant_id,
            item=item,
            actor_id=_actor_uuid(x_actor_id),
            action="RESTORE_INPUT",
            before=before,
            after=after,
            reason=body.reason,
            metadata={"source": "admin_api"},
        )
    db.commit()
    db.refresh(item)
    return input_payload(item)


@router.get("/inputs/{input_code}/audit")
def get_input_audit(
    input_code: str,
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    item = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True)
        .first()
    )
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    query = db.query(AgriculturalInputAuditEvent).filter(
        AgriculturalInputAuditEvent.tenant_id == x_tenant_id,
        AgriculturalInputAuditEvent.input_code == item.code,
        AgriculturalInputAuditEvent.is_active == True,
    )
    if action:
        query = query.filter(AgriculturalInputAuditEvent.action == action.upper())
    events = query.order_by(AgriculturalInputAuditEvent.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "input_code": item.code,
        "count": len(events),
        "events": [_input_audit_payload(event) for event in events],
    }


@router.put("/inputs/{input_code}")
def update_input(
    input_code: str,
    body: AgriculturalInputUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    item = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True)
        .first()
    )
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    before = input_payload(item)
    _apply_input_update(item, body)
    after = input_payload(item)
    if before != after:
        _record_input_audit(
            db,
            tenant_id=x_tenant_id,
            item=item,
            actor_id=_actor_uuid(x_actor_id),
            action="UPDATE_INPUT",
            before=before,
            after=after,
            reason=body.change_reason,
            metadata={"source": "admin_api"},
        )
    db.commit()
    db.refresh(item)
    return input_payload(item)


@router.get("/inputs/{input_code}")
def get_input(input_code: str, db: Session = Depends(get_db)):
    item = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True)
        .first()
    )
    if not item:
        from fastapi import HTTPException
        raise HTTPException(404, f"Input '{input_code}' not found")
    return input_payload(item)
