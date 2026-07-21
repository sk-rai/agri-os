"""Read-only agricultural input catalog APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, optional_admin_viewer, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, AgriculturalInputAuditEvent, InputCategory, ProjectInputAssignment, ProjectInputAssignmentAuditEvent, CropStageInputRule, CropStageInputRuleAuditEvent
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



class CropStageInputRuleUpsert(BaseModel):
    crop_code: str = Field(..., min_length=2, max_length=30)
    season_code: Optional[str] = Field(None, max_length=20)
    stage_code: str = Field(..., min_length=2, max_length=50)
    activity_type: str = Field(..., min_length=2, max_length=30)
    input_code: str = Field(..., min_length=2, max_length=50)
    project_id: Optional[uuid.UUID] = None
    enabled: bool = True
    priority: int = Field(1000, ge=0)
    dosage_quantity: Optional[str] = None
    dosage_unit: Optional[str] = Field(None, max_length=20)
    dosage_area_unit: str = Field("ACRE", min_length=1, max_length=20)
    min_quantity: Optional[str] = None
    max_quantity: Optional[str] = None
    application_method: Optional[str] = None
    timing_note: Optional[str] = None
    safety_note: Optional[str] = None
    allowed_product_codes: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("crop_code", "season_code", "stage_code", "activity_type", "input_code", "dosage_unit", "dosage_area_unit", mode="before")
    @classmethod
    def normalize_codes(cls, value):
        if value is None:
            return None
        return str(value).strip().upper().replace(" ", "_")

    @field_validator("dosage_quantity", "min_quantity", "max_quantity")
    @classmethod
    def validate_decimal(cls, value):
        if value in (None, ""):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("quantity fields must be numeric")
        if parsed < 0:
            raise ValueError("quantity fields must be non-negative")
        return str(parsed)

    @field_validator("allowed_product_codes")
    @classmethod
    def normalize_product_codes(cls, value):
        return sorted({str(code).strip().upper().replace(" ", "_") for code in (value or []) if str(code).strip()})


class CropStageInputRulePatch(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0)
    dosage_quantity: Optional[str] = None
    dosage_unit: Optional[str] = None
    dosage_area_unit: Optional[str] = None
    min_quantity: Optional[str] = None
    max_quantity: Optional[str] = None
    application_method: Optional[str] = None
    timing_note: Optional[str] = None
    safety_note: Optional[str] = None
    allowed_product_codes: Optional[list[str]] = None
    metadata: Optional[dict] = None
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("dosage_quantity", "min_quantity", "max_quantity")
    @classmethod
    def validate_decimal(cls, value):
        if value in (None, ""):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("quantity fields must be numeric")
        if parsed < 0:
            raise ValueError("quantity fields must be non-negative")
        return str(parsed)

    @field_validator("dosage_unit", "dosage_area_unit", mode="before")
    @classmethod
    def normalize_units(cls, value):
        return str(value).strip().upper().replace(" ", "_") if value is not None else None

    @field_validator("allowed_product_codes")
    @classmethod
    def normalize_product_codes(cls, value):
        if value is None:
            return None
        return sorted({str(code).strip().upper().replace(" ", "_") for code in value if str(code).strip()})

class InputArchiveRequest(BaseModel):
    reason: Optional[str] = None


class InputReviewRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


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
        "catalog_status": item.catalog_status,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "reviewed_by": str(item.reviewed_by) if item.reviewed_by else None,
        "review_reason": item.review_reason,
        "is_active": item.is_active,
    }



def _decimal_payload(value):
    return str(value) if value is not None else None


def _input_rule_payload(rule: CropStageInputRule) -> dict:
    item = rule.input
    return {
        "id": str(rule.id),
        "tenant_id": rule.tenant_id,
        "project_id": str(rule.project_id) if rule.project_id else None,
        "rule_scope": "PROJECT" if rule.project_id else "GLOBAL",
        "crop_code": rule.crop_code,
        "season_code": rule.season_code,
        "stage_code": rule.stage_code,
        "activity_type": rule.activity_type,
        "input_code": rule.input_code,
        "input_name": item.canonical_name if item else rule.input_code,
        "input_category_code": item.category.code if item and item.category else None,
        "enabled": bool(rule.enabled),
        "priority": rule.priority,
        "dosage": {"quantity": _decimal_payload(rule.dosage_quantity), "unit": rule.dosage_unit, "area_unit": rule.dosage_area_unit, "min_quantity": _decimal_payload(rule.min_quantity), "max_quantity": _decimal_payload(rule.max_quantity)},
        "application_method": rule.application_method,
        "timing_note": rule.timing_note,
        "safety_note": rule.safety_note,
        "allowed_product_codes": rule.allowed_product_codes or [],
        "metadata": rule.metadata_ or {},
        "reason": rule.reason,
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _input_rule_audit_payload(event: CropStageInputRuleAuditEvent) -> dict:
    return {
        "id": str(event.id), "tenant_id": event.tenant_id, "project_id": str(event.project_id) if event.project_id else None,
        "rule_id": str(event.rule_id) if event.rule_id else None, "input_code": event.input_code,
        "crop_code": event.crop_code, "stage_code": event.stage_code, "activity_type": event.activity_type,
        "actor_id": str(event.actor_id) if event.actor_id else None, "action": event.action,
        "before": event.before_payload, "after": event.after_payload, "reason": event.reason,
        "metadata": event.metadata_ or {}, "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _record_input_rule_audit(db: Session, *, tenant_id: str, rule: CropStageInputRule, actor_id, action: str, before: Optional[dict], after: Optional[dict], reason: Optional[str]) -> None:
    db.add(CropStageInputRuleAuditEvent(id=uuid.uuid4(), tenant_id=tenant_id, project_id=rule.project_id, rule_id=rule.id,
        input_code=rule.input_code, crop_code=rule.crop_code, stage_code=rule.stage_code, activity_type=rule.activity_type,
        actor_id=actor_id, action=action, before_payload=before, after_payload=after, reason=reason,
        metadata_={"source": "admin_api"}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))


def _assert_project_exists(db: Session, *, tenant_id: str, project_id: Optional[uuid.UUID]) -> None:
    if project_id and not db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id, Project.is_active == True).first():
        raise HTTPException(404, "Project not found")


def _input_rule_lookup_query(db: Session, body: CropStageInputRuleUpsert, tenant_id: str):
    query = db.query(CropStageInputRule).filter(CropStageInputRule.tenant_id == tenant_id, CropStageInputRule.crop_code == body.crop_code,
        CropStageInputRule.stage_code == body.stage_code, CropStageInputRule.activity_type == body.activity_type, CropStageInputRule.input_code == body.input_code)
    query = query.filter(CropStageInputRule.project_id == body.project_id) if body.project_id else query.filter(CropStageInputRule.project_id.is_(None))
    query = query.filter(CropStageInputRule.season_code == body.season_code) if body.season_code else query.filter(CropStageInputRule.season_code.is_(None))
    return query


@router.get("/input-rules")
def list_crop_stage_input_rules(crop_code: Optional[str] = Query(None), season_code: Optional[str] = Query(None), stage_code: Optional[str] = Query(None), activity_type: Optional[str] = Query(None), input_code: Optional[str] = Query(None), project_id: Optional[uuid.UUID] = Query(None), include_disabled: bool = Query(False), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), admin_principal: Optional[AdminPrincipal] = Depends(optional_admin_viewer)):
    if include_disabled and admin_principal is None:
        raise HTTPException(403, "Admin VIEW permission is required to include disabled rules")
    _assert_project_exists(db, tenant_id=x_tenant_id, project_id=project_id)
    query = db.query(CropStageInputRule).join(AgriculturalInput).filter(CropStageInputRule.tenant_id == x_tenant_id, CropStageInputRule.is_active == True, AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED")
    query = query.filter((CropStageInputRule.project_id == project_id) | (CropStageInputRule.project_id.is_(None))) if project_id else query.filter(CropStageInputRule.project_id.is_(None))
    if not include_disabled: query = query.filter(CropStageInputRule.enabled == True)
    if crop_code: query = query.filter(CropStageInputRule.crop_code == crop_code.upper())
    if season_code: query = query.filter((CropStageInputRule.season_code == season_code.upper()) | (CropStageInputRule.season_code.is_(None)))
    if stage_code: query = query.filter(CropStageInputRule.stage_code == stage_code.upper())
    if activity_type: query = query.filter(CropStageInputRule.activity_type == activity_type.upper())
    if input_code: query = query.filter(CropStageInputRule.input_code == input_code.upper())
    rules = query.order_by(CropStageInputRule.project_id.nullsfirst(), CropStageInputRule.priority, CropStageInputRule.input_code).all()
    return {"schema_version": "input_rules.v1", "tenant_id": x_tenant_id, "project_id": str(project_id) if project_id else None, "filter_policy": "PROJECT_PLUS_GLOBAL" if project_id else "GLOBAL_ONLY", "count": len(rules), "rules": [_input_rule_payload(rule) for rule in rules]}


@router.get("/input-rules/audit")
def list_crop_stage_input_rule_audit(project_id: Optional[uuid.UUID] = Query(None), input_code: Optional[str] = Query(None), crop_code: Optional[str] = Query(None), stage_code: Optional[str] = Query(None), action: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    query = db.query(CropStageInputRuleAuditEvent).filter(CropStageInputRuleAuditEvent.tenant_id == x_tenant_id)
    if project_id: query = query.filter(CropStageInputRuleAuditEvent.project_id == project_id)
    if input_code: query = query.filter(CropStageInputRuleAuditEvent.input_code == input_code.upper())
    if crop_code: query = query.filter(CropStageInputRuleAuditEvent.crop_code == crop_code.upper())
    if stage_code: query = query.filter(CropStageInputRuleAuditEvent.stage_code == stage_code.upper())
    if action: query = query.filter(CropStageInputRuleAuditEvent.action == action.upper())
    events = query.order_by(CropStageInputRuleAuditEvent.created_at.desc()).limit(limit).all()
    return {"schema_version": "input_rules_audit.v1", "tenant_id": x_tenant_id, "count": len(events), "events": [_input_rule_audit_payload(event) for event in events]}


@router.post("/input-rules")
def create_crop_stage_input_rule(body: CropStageInputRuleUpsert, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    _assert_project_exists(db, tenant_id=x_tenant_id, project_id=body.project_id)
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == body.input_code, AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").first()
    if not item: raise HTTPException(404, f"Published input '{body.input_code}' not found")
    if _input_rule_lookup_query(db, body, x_tenant_id).first(): raise HTTPException(409, "Input rule already exists for this scope")
    rule = CropStageInputRule(id=uuid.uuid4(), tenant_id=x_tenant_id, project_id=body.project_id, crop_code=body.crop_code, season_code=body.season_code, stage_code=body.stage_code, activity_type=body.activity_type, input_id=item.id, input_code=item.code, enabled=body.enabled, priority=body.priority, dosage_quantity=Decimal(body.dosage_quantity) if body.dosage_quantity is not None else None, dosage_unit=body.dosage_unit, dosage_area_unit=body.dosage_area_unit, min_quantity=Decimal(body.min_quantity) if body.min_quantity is not None else None, max_quantity=Decimal(body.max_quantity) if body.max_quantity is not None else None, application_method=body.application_method, timing_note=body.timing_note, safety_note=body.safety_note, allowed_product_codes=body.allowed_product_codes, metadata_=body.metadata, reason=body.reason, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), is_active=True)
    db.add(rule); db.flush(); db.refresh(rule); after = _input_rule_payload(rule)
    _record_input_rule_audit(db, tenant_id=x_tenant_id, rule=rule, actor_id=principal.user_id, action="CREATE_INPUT_RULE", before=None, after=after, reason=body.reason)
    db.commit(); db.refresh(rule); return _input_rule_payload(rule)


@router.patch("/input-rules/{rule_id}")
def update_crop_stage_input_rule(rule_id: uuid.UUID, body: CropStageInputRulePatch, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    rule = db.query(CropStageInputRule).filter(CropStageInputRule.id == rule_id, CropStageInputRule.tenant_id == x_tenant_id, CropStageInputRule.is_active == True).first()
    if not rule: raise HTTPException(404, "Input rule not found")
    before = _input_rule_payload(rule); data = body.model_dump(exclude_unset=True, exclude={"reason"})
    for field in ["enabled", "priority", "dosage_unit", "dosage_area_unit", "application_method", "timing_note", "safety_note", "allowed_product_codes"]:
        if field in data: setattr(rule, field, data[field])
    for field in ["dosage_quantity", "min_quantity", "max_quantity"]:
        if field in data: setattr(rule, field, Decimal(data[field]) if data[field] is not None else None)
    if "metadata" in data: rule.metadata_ = data["metadata"] or {}
    rule.reason = body.reason; rule.updated_at = datetime.now(timezone.utc)
    db.flush(); db.refresh(rule); after = _input_rule_payload(rule)
    _record_input_rule_audit(db, tenant_id=x_tenant_id, rule=rule, actor_id=principal.user_id, action="UPDATE_INPUT_RULE", before=before, after=after, reason=body.reason)
    db.commit(); db.refresh(rule); return _input_rule_payload(rule)

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
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
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
    item.catalog_status = "DRAFT"
    db.add(item)
    db.flush()
    db.refresh(item)
    after = input_payload(item)
    _record_input_audit(
        db,
        tenant_id=x_tenant_id,
        item=item,
        actor_id=principal.user_id,
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
    include_unpublished: bool = Query(False),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    admin_principal: Optional[AdminPrincipal] = Depends(optional_admin_viewer),
):
    if (include_unpublished or status) and admin_principal is None:
        raise HTTPException(403, "Admin VIEW permission is required for unpublished input filters")
    query = db.query(AgriculturalInput).join(InputCategory)
    if not include_inactive:
        query = query.filter(AgriculturalInput.is_active == True)
    if status:
        query = query.filter(AgriculturalInput.catalog_status == status.upper())
    elif not include_unpublished:
        query = query.filter(AgriculturalInput.catalog_status == "PUBLISHED")
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
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project_scope = project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    assignments = project_input_assignments(db, tenant_id=x_tenant_id, project_id=project_id)
    assignments_by_code = assignment_map(assignments)
    explicit_allowlist = explicit_allowlist_mode(assignments)

    query = db.query(AgriculturalInput).join(InputCategory).filter(
        AgriculturalInput.is_active == True,
        AgriculturalInput.catalog_status == "PUBLISHED",
    )
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
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
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
    principal: AdminPrincipal = Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    item = db.query(AgriculturalInput).filter(
        AgriculturalInput.code == input_code.upper(),
        AgriculturalInput.is_active == True,
        AgriculturalInput.catalog_status == "PUBLISHED",
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
        actor_id=principal.user_id,
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


@router.get("/inputs/review-queue")
def list_input_review_queue(
    status: str = Query("REVIEW", pattern="^(DRAFT|REVIEW|REJECTED)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """List input catalog records needing review/governance attention."""
    rows = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == status.upper())
        .order_by(AgriculturalInput.submitted_at.desc().nullslast(), AgriculturalInput.updated_at.desc().nullslast(), AgriculturalInput.created_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for item in rows:
        validation = _input_validation_report(db, item)
        latest_audit = (
            db.query(AgriculturalInputAuditEvent)
            .filter(AgriculturalInputAuditEvent.input_id == item.id)
            .order_by(AgriculturalInputAuditEvent.created_at.desc())
            .first()
        )
        payload = input_payload(item)
        payload.update({
            "validation": {
                "can_submit": validation.get("can_submit"),
                "can_publish": validation.get("can_publish"),
                "counts": {
                    "errors": len(validation.get("errors") or []),
                    "warnings": len(validation.get("warnings") or []),
                    "duplicate_candidates": len(validation.get("duplicate_candidates") or []),
                },
            },
            "latest_audit": _input_audit_payload(latest_audit) if latest_audit else None,
        })
        items.append(payload)
    return {
        "schema_version": "input_review_queue.v1",
        "tenant_id": x_tenant_id,
        "status": status.upper(),
        "count": len(items),
        "items": items,
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


def _input_validation_report(db: Session, item: AgriculturalInput) -> dict:
    errors = []
    warnings = []
    if not item.canonical_name or not item.canonical_name.strip():
        errors.append({"field": "canonical_name", "code": "REQUIRED", "message": "Canonical name is required."})
    if not item.unit or not item.unit.strip():
        errors.append({"field": "unit", "code": "REQUIRED", "message": "Unit is required."})
    if not item.applicable_crops:
        errors.append({"field": "applicable_crops", "code": "CROP_SCOPE_REQUIRED", "message": "At least one applicable crop is required before publishing."})
    if not item.composition and item.category and item.category.code in {"FERTILIZER", "FUNGICIDE", "HERBICIDE", "INSECTICIDE", "MICRONUTRIENT"}:
        warnings.append({"field": "composition", "code": "MISSING_COMPOSITION", "message": "Composition is recommended for this input category."})
    if not item.safety_instructions and item.category and item.category.code in {"FUNGICIDE", "HERBICIDE", "INSECTICIDE", "PESTICIDE"}:
        warnings.append({"field": "safety_instructions", "code": "MISSING_SAFETY", "message": "Safety instructions are recommended for crop-protection inputs."})
    def normalized(value: Optional[str]) -> str:
        return "".join(character.lower() for character in (value or "") if character.isalnum())

    item_aliases = {
        normalized(alias.get("name") or alias.get("value"))
        for alias in (item.aliases or []) if isinstance(alias, dict)
    } - {""}
    duplicates = []
    candidates = db.query(AgriculturalInput).filter(
        AgriculturalInput.id != item.id,
        AgriculturalInput.is_active == True,
        AgriculturalInput.category_id == item.category_id,
    ).order_by(AgriculturalInput.code).all()
    for candidate in candidates:
        reasons = []
        if normalized(candidate.canonical_name) == normalized(item.canonical_name):
            reasons.append("CANONICAL_NAME")
        if item.composition and candidate.composition and normalized(candidate.composition) == normalized(item.composition):
            reasons.append("COMPOSITION")
        if item.brand_name and candidate.brand_name and normalized(candidate.brand_name) == normalized(item.brand_name):
            reasons.append("BRAND_NAME")
        candidate_aliases = {
            normalized(alias.get("name") or alias.get("value"))
            for alias in (candidate.aliases or []) if isinstance(alias, dict)
        } - {""}
        if item_aliases & candidate_aliases:
            reasons.append("ALIAS")
        if reasons:
            payload = input_payload(candidate)
            payload["duplicate_match_reasons"] = reasons
            duplicates.append(payload)
        if len(duplicates) >= 20:
            break
    if duplicates:
        warnings.append({"field": "canonical_name", "code": "POSSIBLE_DUPLICATE", "message": f"{len(duplicates)} possible duplicate(s) found in the same category."})
    return {
        "can_submit": len(errors) == 0,
        "can_publish": len(errors) == 0,
        "counts": {"errors": len(errors), "warnings": len(warnings), "duplicates": len(duplicates)},
        "errors": errors,
        "warnings": warnings,
        "duplicate_candidates": duplicates,
    }


@router.get("/inputs/{input_code}/governance")
def get_input_governance(
    input_code: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper()).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    return {"schema_version": "input_governance.v1", "input": input_payload(item), "validation": _input_validation_report(db, item)}


@router.post("/inputs/{input_code}/submit-review")
def submit_input_review(
    input_code: str,
    body: InputReviewRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    report = _input_validation_report(db, item)
    if not report["can_submit"]:
        raise HTTPException(409, {"message": "Input has blocking validation errors.", "validation": report})
    if item.catalog_status not in {"DRAFT", "REJECTED"}:
        raise HTTPException(409, f"Input status is {item.catalog_status}")
    before = input_payload(item)
    item.catalog_status = "REVIEW"
    item.submitted_at = datetime.now(timezone.utc)
    item.review_reason = body.reason
    after = input_payload(item)
    _record_input_audit(db, tenant_id=x_tenant_id, item=item, actor_id=principal.user_id, action="SUBMIT_INPUT_REVIEW", before=before, after=after, reason=body.reason, metadata={"validation": report["counts"]})
    db.commit()
    return {"input": input_payload(item), "validation": report}


@router.post("/inputs/{input_code}/publish")
def publish_input(
    input_code: str,
    body: InputReviewRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    report = _input_validation_report(db, item)
    if not report["can_publish"]:
        raise HTTPException(409, {"message": "Input has blocking validation errors.", "validation": report})
    if item.catalog_status != "REVIEW":
        raise HTTPException(409, "Only inputs in REVIEW can be published")
    before = input_payload(item)
    item.catalog_status = "PUBLISHED"
    item.reviewed_at = datetime.now(timezone.utc)
    item.reviewed_by = principal.user_id
    item.review_reason = body.reason
    after = input_payload(item)
    _record_input_audit(db, tenant_id=x_tenant_id, item=item, actor_id=principal.user_id, action="PUBLISH_INPUT", before=before, after=after, reason=body.reason, metadata={"validation": report["counts"]})
    db.commit()
    return {"input": input_payload(item), "validation": report}


@router.post("/inputs/{input_code}/reject")
def reject_input(
    input_code: str,
    body: InputReviewRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    item = db.query(AgriculturalInput).filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")
    if item.catalog_status != "REVIEW":
        raise HTTPException(409, "Only inputs in REVIEW can be rejected")
    before = input_payload(item)
    item.catalog_status = "REJECTED"
    item.reviewed_at = datetime.now(timezone.utc)
    item.reviewed_by = principal.user_id
    item.review_reason = body.reason
    after = input_payload(item)
    _record_input_audit(db, tenant_id=x_tenant_id, item=item, actor_id=principal.user_id, action="REJECT_INPUT", before=before, after=after, reason=body.reason)
    db.commit()
    return {"input": input_payload(item), "validation": _input_validation_report(db, item)}


@router.post("/inputs/{input_code}/archive")
def archive_input(
    input_code: str,
    body: InputArchiveRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
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
            actor_id=principal.user_id,
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
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
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
            actor_id=principal.user_id,
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
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
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
    if item.catalog_status != "PUBLISHED":
        item.catalog_status = "DRAFT"
        item.submitted_at = None
        item.reviewed_at = None
        item.reviewed_by = None
        item.review_reason = None
    after = input_payload(item)
    if before != after:
        _record_input_audit(
            db,
            tenant_id=x_tenant_id,
            item=item,
            actor_id=principal.user_id,
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
        .filter(
            AgriculturalInput.code == input_code.upper(),
            AgriculturalInput.is_active == True,
            AgriculturalInput.catalog_status == "PUBLISHED",
        )
        .first()
    )
    if not item:
        from fastapi import HTTPException
        raise HTTPException(404, f"Input '{input_code}' not found")
    return input_payload(item)
