"""Read-only workflow catalog APIs.

These endpoints tell Android/admin clients which published crop workflows are
visible for a tenant/project. Admin write APIs can build on the same tables later.
"""

from __future__ import annotations

import uuid
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Farmer, Parcel, Project
from app.modules.master_data.models import AgriculturalInput, Crop
from app.modules.master_data.input_assignment_service import assert_catalog_input_allowed_for_project_crop
from app.modules.workflow.models import (
    CropCycle,
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateEnablement,
    WorkflowTemplateOverride,
    WorkflowTemplateRecommendation,
    WorkflowTemplateStage,
    WorkflowTemplateVersion,
)
from app.modules.workflow.template_service import (
    find_published_workflow_template,
    list_enabled_workflow_versions,
    workflow_template_metadata,
    scoped_overrides,
    workflow_version_to_stage_definitions,
    workflow_version_to_stage_definitions_for_scope,
)

router = APIRouter(prefix="/api/v1/workflow-catalog", tags=["workflow-catalog"])


def _actor_uuid(x_actor_id: Optional[str]):
    if not x_actor_id:
        return None
    try:
        return uuid.UUID(str(x_actor_id))
    except ValueError:
        raise HTTPException(400, "X-Actor-ID must be a UUID when supplied")


def _record_workflow_audit_event(
    db: Session,
    *,
    tenant_id: str,
    template_id,
    template_version_id=None,
    actor_id=None,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    target_code: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    reason: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    db.add(WorkflowTemplateAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        template_id=template_id,
        template_version_id=template_version_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_code=target_code,
        before=before,
        after=after,
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
    ))


def _audit_payload(event: WorkflowTemplateAuditEvent) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "workflow_template_id": str(event.template_id),
        "workflow_template_version_id": str(event.template_version_id) if event.template_version_id else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "target_code": event.target_code,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "metadata": event.metadata_ or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _latest_workflow_audit_event(db: Session, *, template_version_id, action: str) -> Optional[WorkflowTemplateAuditEvent]:
    return (
        db.query(WorkflowTemplateAuditEvent)
        .filter(
            WorkflowTemplateAuditEvent.template_version_id == template_version_id,
            WorkflowTemplateAuditEvent.action == action,
        )
        .order_by(WorkflowTemplateAuditEvent.created_at.desc())
        .first()
    )


def _draft_freshness_payload(db: Session, version: WorkflowTemplateVersion, *, validated_at: Optional[datetime] = None) -> dict:
    latest_validation = _latest_workflow_audit_event(db, template_version_id=version.id, action="VALIDATE_DRAFT")
    last_validated_at = validated_at or (latest_validation.created_at if latest_validation else None)
    last_edited_at = version.updated_at or version.created_at
    validation_current = bool(last_validated_at and (not last_edited_at or last_validated_at >= last_edited_at))
    return {
        "draft_updated_at": version.updated_at.isoformat() if version.updated_at else None,
        "draft_created_at": version.created_at.isoformat() if version.created_at else None,
        "last_edited_at": last_edited_at.isoformat() if last_edited_at else None,
        "last_validated_at": last_validated_at.isoformat() if last_validated_at else None,
        "validation_current": validation_current,
        "validation_stale": bool(last_validated_at and last_edited_at and last_validated_at < last_edited_at),
    }


class WorkflowEnablementUpdate(BaseModel):
    enabled: bool
    display_order: Optional[int] = None
    display_label: Optional[dict[str, str]] = None


class WorkflowOverrideCreate(BaseModel):
    template_version_id: uuid.UUID
    target_type: str
    target_code: str
    operation: str
    override_payload: dict = {}
    priority: int = 100
    reason: Optional[str] = None


class WorkflowDraftCloneRequest(BaseModel):
    version_number: Optional[str] = None


class WorkflowDraftPublishRequest(BaseModel):
    archive_previous: bool = True


class WorkflowDraftStageCreate(BaseModel):
    after_stage_code: Optional[str] = None
    stage_code: str
    stage_name: dict[str, str]
    duration_days: int = 1
    description: Optional[dict[str, str]] = None
    farmer_actions: Optional[list[str]] = None
    typical_inputs: Optional[list[str]] = None
    key_observations: Optional[list[str]] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    phase: Optional[str] = None
    stage_type: Optional[str] = None


class WorkflowDraftStageDuplicate(BaseModel):
    after_stage_code: Optional[str] = None
    stage_code: Optional[str] = None
    stage_name: Optional[dict[str, str]] = None


class WorkflowDraftStageReorder(BaseModel):
    stage_codes: list[str]


class WorkflowDraftStageRestore(BaseModel):
    after_stage_code: Optional[str] = None


class WorkflowDraftStageUpdate(BaseModel):
    stage_name: Optional[dict[str, str]] = None
    duration_days: Optional[int] = None
    description: Optional[dict[str, str]] = None
    farmer_actions: Optional[list[str]] = None
    typical_inputs: Optional[list[str]] = None
    key_observations: Optional[list[str]] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    phase: Optional[str] = None
    stage_type: Optional[str] = None


class WorkflowDraftRecommendationUpdate(BaseModel):
    day_offset: Optional[int] = None
    input_source: Optional[str] = None
    activity_type: Optional[str] = None
    input_code: Optional[str] = None
    input_name: Optional[str] = None
    typical_quantity: Optional[str] = None
    typical_cost_per_acre: Optional[float] = None
    is_critical: Optional[bool] = None
    description: Optional[dict[str, str]] = None
    sort_order: Optional[int] = None


class WorkflowDraftRecommendationCreate(BaseModel):
    day_offset: int = 0
    input_source: Optional[str] = None
    activity_type: str
    input_code: Optional[str] = None
    input_name: str
    typical_quantity: Optional[str] = None
    typical_cost_per_acre: Optional[float] = None
    is_critical: bool = False
    description: Optional[dict[str, str]] = None
    sort_order: Optional[int] = None


class WorkflowDraftRecommendationReorder(BaseModel):
    stage_code: str
    recommendation_ids: list[uuid.UUID]


class WorkflowLegacyCycleBackfillRequest(BaseModel):
    dry_run: bool = True
    project_id: Optional[uuid.UUID] = None
    crop_code: Optional[str] = None
    season_code: Optional[str] = None
    limit: int = 200
    reason: Optional[str] = None


def _workflow_pin_candidate(db: Session, cycle: CropCycle, tenant_id: str) -> dict:
    workflow_pair = find_published_workflow_template(
        db,
        crop_code=cycle.crop_code,
        season_code=cycle.season_code,
        tenant_id=tenant_id,
        lifecycle_template_id=cycle.lifecycle_template_id,
    )
    if not workflow_pair:
        return {
            "cycle": cycle,
            "eligible": False,
            "reason": "NO_MATCHING_PUBLISHED_WORKFLOW",
            "workflow_template": None,
            "workflow_version": None,
        }
    template, version = workflow_pair
    return {
        "cycle": cycle,
        "eligible": True,
        "reason": "MATCHED_PUBLISHED_WORKFLOW",
        "workflow_template": template,
        "workflow_version": version,
    }


def _legacy_cycle_pin_row(candidate: dict) -> dict:
    cycle = candidate["cycle"]
    template = candidate.get("workflow_template")
    version = candidate.get("workflow_version")
    return {
        "cycle_id": str(cycle.id),
        "tenant_id": cycle.tenant_id,
        "project_id": str(cycle.project_id) if cycle.project_id else None,
        "farmer_id": str(cycle.farmer_id) if cycle.farmer_id else None,
        "parcel_id": str(cycle.parcel_id) if cycle.parcel_id else None,
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "status": cycle.status,
        "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
        "lifecycle_template_id": str(cycle.lifecycle_template_id) if cycle.lifecycle_template_id else None,
        "workflow_template_id": str(template.id) if template else None,
        "workflow_template_code": template.code if template else None,
        "workflow_template_version_id": str(version.id) if version else None,
        "workflow_template_version": version.version_number if version else None,
        "eligible_for_backfill": candidate["eligible"],
        "reason": candidate["reason"],
    }


def _legacy_cycle_pin_candidates(
    db: Session,
    *,
    tenant_id: str,
    project_id=None,
    crop_code: Optional[str] = None,
    season_code: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    query = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.workflow_template_version_id == None,
        CropCycle.status != "ARCHIVED",
    )
    if project_id:
        query = query.filter(CropCycle.project_id == project_id)
    if crop_code:
        query = query.filter(CropCycle.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(CropCycle.season_code == season_code.upper())
    cycles = query.order_by(CropCycle.updated_at.desc(), CropCycle.created_at.desc()).limit(max(1, min(limit, 1000))).all()
    return [_workflow_pin_candidate(db, cycle, tenant_id) for cycle in cycles]


def _validate_override_payload(target_type: str, operation: str, payload: dict) -> None:
    """Reject incomplete project override payloads before preview rendering."""
    if operation == "HIDE":
        return
    if operation == "ADD_RECOMMENDATION":
        if target_type != "STAGE":
            raise HTTPException(400, "ADD_RECOMMENDATION can only target STAGE")
        try:
            int(payload.get("day_offset"))
        except (TypeError, ValueError):
            raise HTTPException(400, "ADD_RECOMMENDATION requires integer day_offset")
        if not payload.get("activity_type"):
            raise HTTPException(400, "ADD_RECOMMENDATION requires activity_type")
        if not payload.get("input_name"):
            raise HTTPException(400, "ADD_RECOMMENDATION requires input_name")
    elif operation == "RENAME":
        if target_type == "STAGE" and not (payload.get("name") or payload.get("label")):
            raise HTTPException(400, "RENAME stage override requires name or label")
        if target_type == "RECOMMENDATION" and not (payload.get("input_name") or payload.get("name")):
            raise HTTPException(400, "RENAME recommendation override requires input_name or name")
    elif operation == "CHANGE_DURATION":
        if target_type != "STAGE":
            raise HTTPException(400, "CHANGE_DURATION can only target STAGE")
        try:
            duration_days = int(payload.get("duration_days"))
        except (TypeError, ValueError):
            raise HTTPException(400, "CHANGE_DURATION requires integer duration_days")
        if duration_days < 0:
            raise HTTPException(400, "duration_days cannot be negative")
    elif operation == "CHANGE_OFFSET":
        if target_type != "RECOMMENDATION":
            raise HTTPException(400, "CHANGE_OFFSET can only target RECOMMENDATION")
        try:
            int(payload.get("day_offset"))
        except (TypeError, ValueError):
            raise HTTPException(400, "CHANGE_OFFSET requires integer day_offset")
    elif operation == "CHANGE_QUANTITY":
        if target_type != "RECOMMENDATION":
            raise HTTPException(400, "CHANGE_QUANTITY can only target RECOMMENDATION")
        if payload.get("typical_quantity") in (None, ""):
            raise HTTPException(400, "CHANGE_QUANTITY requires typical_quantity")


def _label(template, enablement):
    if enablement and enablement.display_label:
        return enablement.display_label
    return {"en": template.canonical_name, "hi": template.canonical_name}


def _override_payload(override: WorkflowTemplateOverride) -> dict:
    return {
        "id": str(override.id),
        "tenant_id": override.tenant_id,
        "project_id": str(override.project_id) if override.project_id else None,
        "template_version_id": str(override.template_version_id),
        "target_type": override.target_type,
        "target_code": override.target_code,
        "operation": override.operation,
        "priority": override.priority,
        "payload": override.override_payload or {},
        "reason": override.reason,
        "is_active": bool(override.is_active),
        "created_at": override.created_at.isoformat() if override.created_at else None,
        "updated_at": override.updated_at.isoformat() if override.updated_at else None,
    }


WORKFLOW_ACTIVE_CYCLE_STATUSES = {"PLANNED", "ACTIVE", "PARTIALLY_TRACKED"}


def _project_workflow_safe_edit_lifecycle(db: Session, project: Project, tenant_id: str) -> dict:
    farmer_count = db.query(Farmer).filter(
        Farmer.tenant_id == tenant_id,
        Farmer.project_id == project.id,
        Farmer.status != "ARCHIVED",
    ).count()
    parcel_count = db.query(Parcel).filter(
        Parcel.tenant_id == tenant_id,
        Parcel.project_id == project.id,
        Parcel.status != "ARCHIVED",
    ).count()
    crop_cycle_count = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.project_id == project.id,
        CropCycle.status != "ARCHIVED",
    ).count()
    active_crop_cycle_count = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.project_id == project.id,
        CropCycle.status.in_(WORKFLOW_ACTIVE_CYCLE_STATUSES),
    ).count()

    reasons = []
    warnings = []
    if project.status in {"COMPLETED", "ARCHIVED"}:
        reasons.append({
            "code": f"PROJECT_{project.status}",
            "message": f"Project status is {project.status}; workflow configuration edits are locked.",
        })
    elif project.status == "ACTIVE":
        warnings.append({
            "code": "PROJECT_ACTIVE",
            "message": "Project is ACTIVE. Workflow edits are allowed only because no enrolled field data exists yet.",
        })
    if farmer_count > 0:
        reasons.append({"code": "FARMERS_ENROLLED", "message": "Farmers are already enrolled in this project."})
    if parcel_count > 0:
        reasons.append({"code": "PARCELS_REGISTERED", "message": "Land parcels are already linked to this project."})
    if crop_cycle_count > 0:
        reasons.append({"code": "CROP_CYCLES_STARTED", "message": "Crop cycles already exist for this project."})

    can_edit = len(reasons) == 0
    return {
        "schema_version": "workflow_safe_edit_lifecycle.v1",
        "project_id": str(project.id),
        "tenant_id": tenant_id,
        "project_status": project.status,
        "can_edit_project_workflows": can_edit,
        "lock_state": "OPEN" if can_edit else "LOCKED",
        "locked_operations": [] if can_edit else [
            "ENABLE_WORKFLOW",
            "DISABLE_WORKFLOW",
            "UPDATE_WORKFLOW_METADATA",
            "CREATE_PROJECT_OVERRIDE",
            "DELETE_PROJECT_OVERRIDE",
        ],
        "allowed_operations": [
            "ENABLE_WORKFLOW",
            "DISABLE_WORKFLOW",
            "UPDATE_WORKFLOW_METADATA",
            "CREATE_PROJECT_OVERRIDE",
            "DELETE_PROJECT_OVERRIDE",
        ] if can_edit else [
            "VIEW_WORKFLOWS",
            "PREVIEW_WORKFLOWS",
            "CREATE_NEW_DRAFT_VERSION_FOR_FUTURE_USE",
        ],
        "counts": {
            "farmers": farmer_count,
            "parcels": parcel_count,
            "crop_cycles": crop_cycle_count,
            "active_crop_cycles": active_crop_cycle_count,
        },
        "reasons": reasons,
        "warnings": warnings,
        "suggested_action": "Edit this project's workflow configuration before enrollment, or create a new workflow version for future cycles." if not can_edit else None,
    }


def _assert_project_workflow_editable(db: Session, project: Project, tenant_id: str) -> dict:
    lifecycle = _project_workflow_safe_edit_lifecycle(db, project, tenant_id)
    if not lifecycle["can_edit_project_workflows"]:
        raise HTTPException(
            409,
            {
                "message": "Project workflow configuration is locked because field data already exists.",
                "safe_edit_lifecycle": lifecycle,
            },
        )
    return lifecycle


@router.get("/enabled-crop-workflows")
def list_enabled_crop_workflows(
    project_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    include_stages: bool = Query(False),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return crop workflow templates visible for a tenant/project.

    If no enablement rows exist for the requested scope, default published
    system workflows are returned. If enablement rows exist, they act as an
    explicit allow-list.
    """
    rows = list_enabled_workflow_versions(
        db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        crop_code=crop_code,
        season_code=season,
    )
    crop_codes = sorted({template.crop_code for template, _, _ in rows})
    crops_by_code = {
        crop.code: crop
        for crop in db.query(Crop).filter(Crop.code.in_(crop_codes)).all()
    } if crop_codes else {}

    workflows = []
    for template, version, enablement in rows:
        crop = crops_by_code.get(template.crop_code)
        metadata = workflow_template_metadata(template, version)
        item = {
            "workflow_template_id": str(template.id),
            "workflow_template_version_id": str(version.id),
            "workflow_template_code": template.code,
            "version": version.version_number,
            "status": version.status,
            "tenant_id": template.tenant_id,
            "project_id": str(enablement.project_id) if enablement and enablement.project_id else None,
            "enabled": True,
            "enablement_source": "explicit" if enablement else "implicit_default",
            "display_order": enablement.display_order if enablement else None,
            "label": _label(template, enablement),
            "crop_code": template.crop_code,
            "crop_name": crop.canonical_name if crop else template.crop_code,
            "season_code": template.season_code,
            "catalog_selection_key": f"{template.crop_code}:{template.season_code}",
            "catalog_selection_policy": "LATEST_PUBLISHED_PER_CROP_SEASON",
            "propagation_type_code": template.propagation_type_code,
            "total_duration_days": version.total_duration_days,
            "metadata": metadata,
        }
        if include_stages:
            item["stages"] = workflow_version_to_stage_definitions_for_scope(
                db,
                version.id,
                tenant_id=x_tenant_id,
                project_id=project_id,
                crop_code=template.crop_code,
                season_code=template.season_code,
            )
        workflows.append(item)

    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id) if project_id else None,
        "count": len(workflows),
        "workflows": workflows,
    }



def _project_workflow_enablement_summary(db: Session, project_id: uuid.UUID, tenant_id: str) -> dict:
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    version_rows = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplate.is_active == True,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplate.tenant_id.in_([tenant_id, "default"]),
        )
        .order_by(WorkflowTemplate.crop_code, WorkflowTemplate.season_code, WorkflowTemplate.canonical_name)
        .all()
    )
    template_ids = [template.id for template, _ in version_rows]

    if template_ids:
        project_enablements = (
            db.query(WorkflowTemplateEnablement)
            .filter(
                WorkflowTemplateEnablement.tenant_id == tenant_id,
                WorkflowTemplateEnablement.project_id == project_id,
                WorkflowTemplateEnablement.template_id.in_(template_ids),
                WorkflowTemplateEnablement.is_active == True,
            )
            .all()
        )
        tenant_enablements = (
            db.query(WorkflowTemplateEnablement)
            .filter(
                WorkflowTemplateEnablement.tenant_id == tenant_id,
                WorkflowTemplateEnablement.project_id.is_(None),
                WorkflowTemplateEnablement.template_id.in_(template_ids),
                WorkflowTemplateEnablement.is_active == True,
            )
            .all()
        )
    else:
        project_enablements = []
        tenant_enablements = []

    project_enablement_by_template = {row.template_id: row for row in project_enablements}
    tenant_enablement_by_template = {row.template_id: row for row in tenant_enablements}
    explicit_scope = bool(project_enablements) or bool(tenant_enablements)
    project_crop_scope = {str(code).upper() for code in (project.crop_scope or [])}

    lifecycle = _project_workflow_safe_edit_lifecycle(db, project, tenant_id)
    project_cycles = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.project_id == project.id,
        CropCycle.status != "ARCHIVED",
    ).all()
    cycle_counts_by_key = {}
    active_cycle_counts_by_key = {}
    for cycle in project_cycles:
        key = (cycle.crop_code, cycle.season_code)
        cycle_counts_by_key[key] = cycle_counts_by_key.get(key, 0) + 1
        if cycle.status in WORKFLOW_ACTIVE_CYCLE_STATUSES:
            active_cycle_counts_by_key[key] = active_cycle_counts_by_key.get(key, 0) + 1

    crop_codes = sorted({template.crop_code for template, _ in version_rows})
    crops_by_code = {
        crop.code: crop
        for crop in db.query(Crop).filter(Crop.code.in_(crop_codes)).all()
    } if crop_codes else {}

    workflows = []
    for template, version in version_rows:
        enablement = project_enablement_by_template.get(template.id) or tenant_enablement_by_template.get(template.id)
        scope = "project" if template.id in project_enablement_by_template else "tenant" if template.id in tenant_enablement_by_template else "implicit_default"
        crop_allowed = not project_crop_scope or template.crop_code.upper() in project_crop_scope
        configured_enabled = bool(enablement.enabled) if enablement else (not explicit_scope and template.is_default)
        enabled = configured_enabled and crop_allowed
        if not crop_allowed:
            visibility_status = "CROP_SCOPE_BLOCKED"
            assignment_rule = "BLOCKED_BY_PROJECT_CROP_SCOPE"
            assignment_reason = f"Project crop scope does not include {template.crop_code}."
        elif enabled and enablement:
            visibility_status = "ENABLED"
            assignment_rule = "ANDROID_VISIBLE"
            assignment_reason = f"Workflow is enabled by {scope} assignment."
        elif enablement and not enablement.enabled:
            visibility_status = "DISABLED"
            assignment_rule = "DISABLED_BY_PROJECT" if scope == "project" else "DISABLED_BY_TENANT"
            assignment_reason = f"Workflow is explicitly disabled at {scope} scope."
        elif enabled:
            visibility_status = "IMPLICIT_DEFAULT"
            assignment_rule = "ANDROID_VISIBLE"
            assignment_reason = "Workflow is visible through implicit default catalog rules."
        else:
            visibility_status = "NOT_VISIBLE"
            assignment_rule = "NOT_ASSIGNED"
            assignment_reason = "Workflow is not assigned to this project."
        overrides = scoped_overrides(db, template_version_id=version.id, tenant_id=tenant_id, project_id=project_id)
        crop = crops_by_code.get(template.crop_code)
        workflows.append({
            "workflow_template_id": str(template.id),
            "workflow_template_version_id": str(version.id),
            "workflow_template_code": template.code,
            "version": version.version_number,
            "status": version.status,
            "visibility_status": visibility_status,
            "assignment_rule": assignment_rule,
            "assignment_reason": assignment_reason,
            "crop_scope_allowed": crop_allowed,
            "enablement_scope": scope,
            "enabled": enabled,
            "configured_enabled": configured_enabled,
            "display_order": enablement.display_order if enablement else None,
            "label": _label(template, enablement),
            "crop_code": template.crop_code,
            "crop_name": crop.canonical_name if crop else template.crop_code,
            "season_code": template.season_code,
            "propagation_type_code": template.propagation_type_code,
            "total_duration_days": version.total_duration_days,
            "usage_count": cycle_counts_by_key.get((template.crop_code, template.season_code), 0),
            "active_usage_count": active_cycle_counts_by_key.get((template.crop_code, template.season_code), 0),
            "override_count": len(overrides),
            "overrides": [
                {
                    "id": str(override.id),
                    "target_type": override.target_type,
                    "target_code": override.target_code,
                    "operation": override.operation,
                    "priority": override.priority,
                    "reason": override.reason,
                }
                for override in overrides
            ],
        })

    workflows.sort(key=lambda item: (not item["enabled"], item["display_order"] if item["display_order"] is not None else 1000, item["crop_code"], item["season_code"]))
    return {
        "schema_version": "1.0.0",
        "tenant_id": tenant_id,
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "crop_scope": project.crop_scope or [],
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
        },
        "explicit_scope": explicit_scope,
        "safe_edit_lifecycle": lifecycle,
        "counts": {
            "total": len(workflows),
            "enabled": sum(1 for item in workflows if item["enabled"]),
            "disabled": sum(1 for item in workflows if item["visibility_status"] == "DISABLED"),
            "implicit_default": sum(1 for item in workflows if item["visibility_status"] == "IMPLICIT_DEFAULT"),
            "not_visible": sum(1 for item in workflows if item["visibility_status"] == "NOT_VISIBLE"),
            "crop_scope_blocked": sum(1 for item in workflows if item["visibility_status"] == "CROP_SCOPE_BLOCKED"),
            "android_visible": sum(1 for item in workflows if item["assignment_rule"] == "ANDROID_VISIBLE"),
        },
        "workflows": workflows,
    }


def _stage_name(stage: dict) -> str:
    name = stage.get("name")
    if isinstance(name, dict):
        return name.get("en") or next(iter(name.values()), "")
    return str(name or "")


def _preview_warnings(stages: list[dict], known_input_codes: set[str]) -> list[dict]:
    warnings = []
    stage_orders = {}
    stage_codes = set()
    for stage in stages:
        code = stage.get("code")
        order = stage.get("order")
        if code in stage_codes:
            warnings.append({"level": "ERROR", "code": "DUPLICATE_STAGE_CODE", "message": f"Duplicate stage code: {code}", "target": code})
        stage_codes.add(code)
        if order in stage_orders:
            warnings.append({"level": "ERROR", "code": "DUPLICATE_STAGE_ORDER", "message": f"Stage order {order} is reused", "target": code})
        stage_orders[order] = code
        if not stage.get("recommended_activities"):
            warnings.append({"level": "WARN", "code": "STAGE_WITHOUT_RECOMMENDATIONS", "message": f"{code} has no recommendations", "target": code})
        if not _stage_name(stage):
            warnings.append({"level": "WARN", "code": "STAGE_WITHOUT_NAME", "message": f"{code} has no display name", "target": code})

        for idx, rec in enumerate(stage.get("recommended_activities", []) or [], start=1):
            target = f"{code}:recommendation:{idx}"
            input_code = rec.get("input_code")
            metadata = rec.get("metadata") or {}
            input_source = str(metadata.get("input_source") or "").upper()
            if input_source == "CUSTOM":
                if not input_code or not str(input_code).startswith("CUSTOM_"):
                    warnings.append({"level": "ERROR", "code": "INVALID_CUSTOM_INPUT_CODE", "message": "Custom recommendations require a stable CUSTOM_* input code", "target": target})
                else:
                    warnings.append({"level": "INFO", "code": "CUSTOM_INPUT", "message": f"{rec.get('input_name') or input_code} is an approved custom input", "target": target})
            elif not input_code:
                warnings.append({"level": "ERROR", "code": "RECOMMENDATION_WITHOUT_INPUT_CODE", "message": f"{rec.get('input_name') or 'Recommendation'} has no stable input_code", "target": target})
            elif input_code not in known_input_codes:
                warnings.append({"level": "ERROR", "code": "UNKNOWN_INPUT_CODE", "message": f"Input code {input_code} is not in input catalog and is not marked CUSTOM", "target": target})
            if not rec.get("input_name"):
                warnings.append({"level": "ERROR", "code": "RECOMMENDATION_WITHOUT_INPUT_NAME", "message": "Recommendation has no input_name fallback", "target": target})
            if rec.get("typical_quantity") in (None, ""):
                warnings.append({"level": "INFO", "code": "RECOMMENDATION_WITHOUT_QUANTITY", "message": f"{rec.get('input_name') or 'Recommendation'} has no typical quantity", "target": target})
            if rec.get("day_offset") is None:
                warnings.append({"level": "WARN", "code": "RECOMMENDATION_WITHOUT_DAY_OFFSET", "message": f"{rec.get('input_name') or 'Recommendation'} has no day offset", "target": target})
    return warnings


def _workflow_version_usage_counts(db: Session, version_id) -> dict:
    pinned_cycle_count = db.query(CropCycle).filter(
        CropCycle.workflow_template_version_id == version_id,
        CropCycle.status != "ARCHIVED",
    ).count()
    active_pinned_cycle_count = db.query(CropCycle).filter(
        CropCycle.workflow_template_version_id == version_id,
        CropCycle.status.in_(WORKFLOW_ACTIVE_CYCLE_STATUSES),
    ).count()
    return {
        "pinned_cycle_count": pinned_cycle_count,
        "active_pinned_cycle_count": active_pinned_cycle_count,
    }


def _workflow_version_impact_row(db: Session, version: WorkflowTemplateVersion, action: str) -> dict:
    usage = _workflow_version_usage_counts(db, version.id)
    return {
        "workflow_template_version_id": str(version.id),
        "version": version.version_number,
        "status": version.status,
        "action": action,
        "pinned_cycle_count": usage["pinned_cycle_count"],
        "active_pinned_cycle_count": usage["active_pinned_cycle_count"],
        "is_safe_to_archive": True,
        "retention_policy": "ARCHIVED_VERSIONS_REMAIN_RENDERABLE_FOR_PINNED_CYCLES",
        "message": (
            "Version has pinned crop cycles; archive only removes it from new Android catalog selection."
            if usage["pinned_cycle_count"] > 0
            else "No pinned crop cycles use this version."
        ),
    }


def _draft_publish_impact(db: Session, template: WorkflowTemplate, draft_version: WorkflowTemplateVersion, archive_previous: bool) -> dict:
    previous_versions = (
        db.query(WorkflowTemplateVersion)
        .filter(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.id != draft_version.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        )
        .all()
    )
    previous_rows = [
        _workflow_version_impact_row(db, previous, "ARCHIVE_FOR_NEW_CATALOG" if archive_previous else "KEEP_PUBLISHED")
        for previous in previous_versions
    ]
    impacted_pinned_cycle_count = sum(row["pinned_cycle_count"] for row in previous_rows)
    active_impacted_pinned_cycle_count = sum(row["active_pinned_cycle_count"] for row in previous_rows)
    return {
        "schema_version": "workflow_publish_impact.v1",
        "workflow_template_id": str(template.id),
        "draft_version_id": str(draft_version.id),
        "draft_version": draft_version.version_number,
        "archive_previous": archive_previous,
        "impacted_published_versions": previous_rows,
        "counts": {
            "published_versions_impacted": len(previous_rows),
            "pinned_cycles_impacted": impacted_pinned_cycle_count,
            "active_pinned_cycles_impacted": active_impacted_pinned_cycle_count,
        },
        "can_publish": True,
        "blocking_reasons": [],
        "safety_message": (
            "Pinned cycles will remain renderable from their archived workflow versions."
            if impacted_pinned_cycle_count > 0 and archive_previous
            else "No pinned cycles are affected by archiving previous versions."
        ),
    }


def _workflow_preview_payload(
    *,
    template: WorkflowTemplate,
    version: WorkflowTemplateVersion,
    crop: Optional[Crop],
    stages: list[dict],
    overrides: list[WorkflowTemplateOverride],
    warnings: list[dict],
    tenant_id: str,
    project_id=None,
    preview_source: str = "workflow_template",
    enablement_source: str = "implicit_default",
    enablement=None,
    draft_freshness: Optional[dict] = None,
) -> dict:
    total_duration_days = sum(int(stage.get("duration_days") or 0) for stage in stages)
    return {
        "schema_version": "1.0.0",
        "tenant_id": tenant_id,
        "project_id": str(project_id) if project_id else None,
        "preview_source": preview_source,
        "workflow_template_id": str(template.id),
        "workflow_template_version_id": str(version.id),
        "workflow_template_code": template.code,
        "version": version.version_number,
        "status": version.status,
        "enablement_source": enablement_source,
        "label": _label(template, enablement),
        "crop_code": template.crop_code,
        "crop_name": crop.canonical_name if crop else template.crop_code,
        "season_code": template.season_code,
        "propagation_type_code": template.propagation_type_code,
        "total_duration_days": total_duration_days,
        "applied_overrides": [_override_payload(override) for override in overrides],
        "warnings": warnings,
        "version_created_at": version.created_at.isoformat() if version.created_at else None,
        "version_updated_at": version.updated_at.isoformat() if version.updated_at else None,
        "draft_freshness": draft_freshness,
        "android_preview": {
            "crop_code": template.crop_code,
            "crop_name": crop.canonical_name if crop else template.crop_code,
            "season_code": template.season_code,
            "total_duration_days": total_duration_days,
            "propagation_method": template.propagation_type_code,
            "stages": stages,
        },
    }


@router.get("/workflow-preview/{workflow_template_version_id}")
def preview_workflow_template_version(
    workflow_template_version_id: uuid.UUID,
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Preview final Android-facing workflow JSON for a published version.

    The response is read-only and includes applied override metadata plus
    validation warnings useful before enabling edits/publishing in admin.
    """
    rows = list_enabled_workflow_versions(db, tenant_id=x_tenant_id, project_id=project_id)
    selected = next((row for row in rows if str(row[1].id) == str(workflow_template_version_id)), None)
    if selected:
        template, version, enablement = selected
    else:
        row = (
            db.query(WorkflowTemplate, WorkflowTemplateVersion)
            .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
            .filter(
                WorkflowTemplateVersion.id == workflow_template_version_id,
                WorkflowTemplateVersion.status.in_(["PUBLISHED", "ARCHIVED"]),
                WorkflowTemplateVersion.is_active == True,
                WorkflowTemplate.is_active == True,
                WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
            )
            .first()
        )
        if not row:
            raise HTTPException(404, "Workflow template version is not visible for this tenant/project")
        template, version = row
        enablement = None

    crop = db.query(Crop).filter(Crop.code == template.crop_code).first()
    stages = workflow_version_to_stage_definitions_for_scope(
        db,
        version.id,
        tenant_id=x_tenant_id,
        project_id=project_id,
        crop_code=template.crop_code,
        season_code=template.season_code,
    )
    overrides = scoped_overrides(db, template_version_id=version.id, tenant_id=x_tenant_id, project_id=project_id)
    known_input_codes = {row.code for row in db.query(AgriculturalInput.code).filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").all()}
    warnings = _preview_warnings(stages, known_input_codes)

    return _workflow_preview_payload(
        template=template,
        version=version,
        crop=crop,
        stages=stages,
        overrides=overrides,
        warnings=warnings,
        tenant_id=x_tenant_id,
        project_id=project_id,
        preview_source="workflow_template",
        enablement_source="explicit" if enablement else "implicit_default",
        enablement=enablement,
    )


def _get_draft_template_version(db: Session, workflow_template_version_id: uuid.UUID, tenant_id: str):
    row = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplateVersion.id == workflow_template_version_id,
            WorkflowTemplateVersion.status == "DRAFT",
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplate.is_active == True,
            WorkflowTemplate.tenant_id.in_([tenant_id, "default"]),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Draft workflow template version not found")
    return row


def _draft_stage_definitions(db: Session, version_id) -> list[dict]:
    """Render draft stages and attach admin-only row IDs for editing recommendations."""
    stages = workflow_version_to_stage_definitions(db, version_id)
    stage_rows = (
        db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version_id, WorkflowTemplateStage.is_active == True)
        .order_by(WorkflowTemplateStage.stage_order)
        .all()
    )
    stage_rows_by_code = {stage.stage_code: stage for stage in stage_rows}
    for stage in stages:
        stage_row = stage_rows_by_code.get(stage.get("code"))
        if not stage_row:
            continue
        rec_rows = (
            db.query(WorkflowTemplateRecommendation)
            .filter(
                WorkflowTemplateRecommendation.template_stage_id == stage_row.id,
                WorkflowTemplateRecommendation.is_active == True,
            )
            .order_by(
                WorkflowTemplateRecommendation.sort_order,
                WorkflowTemplateRecommendation.day_offset,
            )
            .all()
        )
        for rec, rec_row in zip(stage.get("recommended_activities", []) or [], rec_rows):
            metadata = dict(rec.get("metadata") or {})
            metadata["recommendation_id"] = str(rec_row.id)
            metadata["template_stage_id"] = str(stage_row.id)
            metadata["source"] = metadata.get("source") or "workflow_template_draft"
            rec["metadata"] = metadata
    return stages


def _known_input_codes(db: Session) -> set[str]:
    return {row.code for row in db.query(AgriculturalInput.code).filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").all()}


def _render_draft_preview(db: Session, workflow_template_version_id: uuid.UUID, tenant_id: str) -> dict:
    template, version = _get_draft_template_version(db, workflow_template_version_id, tenant_id)
    crop = db.query(Crop).filter(Crop.code == template.crop_code).first()
    stages = _draft_stage_definitions(db, version.id)
    warnings = _preview_warnings(stages, _known_input_codes(db))
    return _workflow_preview_payload(
        template=template,
        version=version,
        crop=crop,
        stages=stages,
        overrides=[],
        warnings=warnings,
        tenant_id=tenant_id,
        project_id=None,
        preview_source="workflow_template_draft",
        enablement_source="draft_admin_preview",
        enablement=None,
        draft_freshness=_draft_freshness_payload(db, version),
    )


def _render_published_version_preview(db: Session, template: WorkflowTemplate, version: WorkflowTemplateVersion, tenant_id: str) -> dict:
    crop = db.query(Crop).filter(Crop.code == template.crop_code).first()
    stages = workflow_version_to_stage_definitions(db, version.id)
    warnings = _preview_warnings(stages, _known_input_codes(db))
    return _workflow_preview_payload(
        template=template,
        version=version,
        crop=crop,
        stages=stages,
        overrides=[],
        warnings=warnings,
        tenant_id=tenant_id,
        project_id=None,
        preview_source="workflow_template_published",
        enablement_source="draft_publish",
        enablement=None,
    )


def _draft_validation(db: Session, version_id) -> tuple[list[dict], dict]:
    stages = workflow_version_to_stage_definitions(db, version_id)
    issues = _preview_warnings(stages, _known_input_codes(db))
    template = (
        db.query(WorkflowTemplate)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(WorkflowTemplateVersion.id == version_id)
        .first()
    )
    if template:
        catalog_crop_scopes = {
            item.code: {str(crop).upper() for crop in (item.applicable_crops or [])}
            for item in db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").all()
        }
        for stage in stages:
            for index, recommendation in enumerate(stage.get("recommended_activities", []) or [], start=1):
                input_code = recommendation.get("input_code")
                applicable = catalog_crop_scopes.get(input_code)
                if applicable and template.crop_code.upper() not in applicable:
                    issues.append({
                        "level": "ERROR",
                        "code": "INPUT_NOT_APPLICABLE_TO_CROP",
                        "message": f"Input {input_code} is not applicable to {template.crop_code}",
                        "target": f"{stage.get('code')}:recommendation:{index}",
                    })
    if not stages:
        issues.append({"level": "ERROR", "code": "DRAFT_WITHOUT_STAGES", "message": "Draft workflow must have at least one stage", "target": str(version_id)})

    issues_by_level = {"ERROR": [], "WARN": [], "INFO": []}
    for issue in issues:
        level = str(issue.get("level") or "INFO").upper()
        issues_by_level.setdefault(level, []).append(issue)

    recommendation_count = sum(len(stage.get("recommended_activities", []) or []) for stage in stages)
    report = {
        "schema_version": "1.0.0",
        "can_publish": len(issues_by_level.get("ERROR", [])) == 0,
        "counts": {
            "total": len(issues),
            "errors": len(issues_by_level.get("ERROR", [])),
            "warnings": len(issues_by_level.get("WARN", [])),
            "info": len(issues_by_level.get("INFO", [])),
            "stages": len(stages),
            "recommendations": recommendation_count,
        },
        "issues": issues,
        "issues_by_level": issues_by_level,
    }
    return stages, report


@router.get("/draft-preview/{workflow_template_version_id}")
def preview_draft_workflow_template_version(
    workflow_template_version_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Admin-only preview for DRAFT workflow versions.

    Android/public preview remains /workflow-preview and continues to serve only
    published, enabled workflow versions.
    """
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.get("/drafts/{workflow_template_version_id}/validation")
def validate_draft_workflow_template_version(
    workflow_template_version_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    """Return non-mutating validation report for a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    _, report = _draft_validation(db, version.id)
    validated_at = datetime.now(timezone.utc)
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id),
        action="VALIDATE_DRAFT",
        target_type="VERSION",
        target_id=str(version.id),
        after={"can_publish": report["can_publish"], "counts": report["counts"]},
    )
    db.commit()
    return {
        **report,
        "tenant_id": x_tenant_id,
        "workflow_template_id": str(template.id),
        "workflow_template_version_id": str(version.id),
        "workflow_template_code": template.code,
        "version": version.version_number,
        "status": version.status,
        "freshness": _draft_freshness_payload(db, version, validated_at=validated_at),
    }


@router.get("/drafts/{workflow_template_version_id}/deleted-stages")
def list_deleted_draft_workflow_stages(
    workflow_template_version_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """List soft-deleted stages in a DRAFT workflow version for admin restore UX."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    rows = (
        db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.is_active == False)
        .order_by(WorkflowTemplateStage.updated_at.desc(), WorkflowTemplateStage.stage_code.asc())
        .all()
    )
    deleted_stages = []
    for stage in rows:
        rec_count = db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id == stage.id,
        ).count()
        deleted_stages.append({
            "template_stage_id": str(stage.id),
            "stage_code": stage.stage_code,
            "stage_name": deepcopy(stage.stage_name or {}),
            "stage_order": stage.stage_order,
            "duration_days": stage.duration_days,
            "stage_type": stage.stage_type,
            "phase": stage.phase,
            "recommendation_count": rec_count,
            "updated_at": stage.updated_at.isoformat() if stage.updated_at else None,
        })
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "workflow_template_id": str(template.id),
        "workflow_template_version_id": str(version.id),
        "workflow_template_code": template.code,
        "count": len(deleted_stages),
        "deleted_stages": deleted_stages,
    }


@router.patch("/drafts/{workflow_template_version_id}/stages/reorder")
def reorder_draft_workflow_stages(
    workflow_template_version_id: uuid.UUID,
    body: WorkflowDraftStageReorder,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Reorder all active stages inside a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    requested_codes = [_normalize_stage_code(code) for code in (body.stage_codes or [])]
    if not requested_codes:
        raise HTTPException(400, "stage_codes cannot be empty")
    if len(requested_codes) != len(set(requested_codes)):
        raise HTTPException(400, "stage_codes contains duplicate values")

    stages = (
        db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.is_active == True)
        .order_by(WorkflowTemplateStage.stage_order.asc())
        .all()
    )
    stages_by_code = {stage.stage_code: stage for stage in stages}
    existing_codes = set(stages_by_code.keys())
    requested_set = set(requested_codes)
    missing = sorted(existing_codes - requested_set)
    unknown = sorted(requested_set - existing_codes)
    if missing or unknown:
        raise HTTPException(
            400,
            {
                "message": "stage_codes must include every active draft stage exactly once",
                "missing_stage_codes": missing,
                "unknown_stage_codes": unknown,
            },
        )

    before = [_stage_audit_snapshot(stage) for stage in stages]
    now = datetime.now(timezone.utc)
    # Avoid transient conflicts with unique (template_version_id, stage_order).
    offset = 10000
    for index, code in enumerate(requested_codes, start=1):
        stage = stages_by_code[code]
        stage.stage_order = offset + index
        stage.updated_at = now
    db.flush()
    for index, code in enumerate(requested_codes, start=1):
        stage = stages_by_code[code]
        stage.stage_order = index
        stage.updated_at = now
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="REORDER_DRAFT_STAGES",
        target_type="VERSION",
        target_id=str(version.id),
        before={"stages": before},
        after={"stage_codes": requested_codes},
        metadata={"stage_count": len(requested_codes)},
        reason="Reorder draft workflow stages",
    )
    db.commit()
    return preview_draft_workflow_template_version(version.id, db=db, x_tenant_id=x_tenant_id)


@router.patch("/drafts/{workflow_template_version_id}/stages/{stage_code}")
def update_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftStageUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Edit a stage inside a DRAFT workflow version and return updated draft preview."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == version.id,
            WorkflowTemplateStage.stage_code == stage_code,
            WorkflowTemplateStage.is_active == True,
        )
        .first()
    )
    if not stage:
        raise HTTPException(404, "Draft workflow stage not found")

    before = _stage_audit_snapshot(stage)
    changes = body.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No stage changes supplied")
    if "duration_days" in changes:
        if changes["duration_days"] is None:
            raise HTTPException(400, "duration_days cannot be null")
        duration_days = int(changes["duration_days"])
        if duration_days < 0:
            raise HTTPException(400, "duration_days cannot be negative")
        stage.duration_days = duration_days
    if "stage_name" in changes:
        if not changes["stage_name"]:
            raise HTTPException(400, "stage_name cannot be empty")
        stage.stage_name = changes["stage_name"]
    if "description" in changes:
        stage.description = changes["description"]
    if "farmer_actions" in changes:
        stage.farmer_actions = changes["farmer_actions"] or []
    if "typical_inputs" in changes:
        stage.typical_inputs = changes["typical_inputs"] or []
    if "key_observations" in changes:
        stage.key_observations = changes["key_observations"] or []
    if "icon" in changes:
        stage.icon = changes["icon"]
    if "color" in changes:
        stage.color = changes["color"]
    if "phase" in changes:
        stage.phase = changes["phase"]
    if "stage_type" in changes:
        stage.stage_type = changes["stage_type"]

    now = datetime.now(timezone.utc)
    stage.updated_at = now
    version.total_duration_days = sum(
        int(row.duration_days or 0)
        for row in db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.is_active == True)
        .all()
    )
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=principal.user_id,
        action="UPDATE_STAGE",
        target_type="STAGE",
        target_id=str(stage.id),
        target_code=stage.stage_code,
        before=before,
        after=_stage_audit_snapshot(stage),
        metadata={"changed_fields": sorted(changes.keys())},
    )
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


def _get_draft_stage(db: Session, version_id, stage_code: str) -> WorkflowTemplateStage:
    stage = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == version_id,
            WorkflowTemplateStage.stage_code == stage_code,
            WorkflowTemplateStage.is_active == True,
        )
        .first()
    )
    if not stage:
        raise HTTPException(404, "Draft workflow stage not found")
    return stage


def _get_draft_recommendation(db: Session, version_id, recommendation_id: uuid.UUID) -> WorkflowTemplateRecommendation:
    rec = (
        db.query(WorkflowTemplateRecommendation)
        .join(WorkflowTemplateStage, WorkflowTemplateStage.id == WorkflowTemplateRecommendation.template_stage_id)
        .filter(
            WorkflowTemplateStage.template_version_id == version_id,
            WorkflowTemplateStage.is_active == True,
            WorkflowTemplateRecommendation.id == recommendation_id,
            WorkflowTemplateRecommendation.is_active == True,
        )
        .first()
    )
    if not rec:
        raise HTTPException(404, "Draft workflow recommendation not found")
    return rec


def _stage_audit_snapshot(stage: WorkflowTemplateStage) -> dict:
    return {
        "stage_code": stage.stage_code,
        "stage_name": deepcopy(stage.stage_name or {}),
        "stage_order": stage.stage_order,
        "duration_days": stage.duration_days,
        "stage_type": stage.stage_type,
        "phase": stage.phase,
        "description": deepcopy(stage.description),
        "farmer_actions": deepcopy(stage.farmer_actions or []),
        "typical_inputs": deepcopy(stage.typical_inputs or []),
        "key_observations": deepcopy(stage.key_observations or []),
        "icon": stage.icon,
        "color": stage.color,
    }


def _recommendation_audit_snapshot(rec: WorkflowTemplateRecommendation) -> dict:
    return {
        "sort_order": rec.sort_order,
        "day_offset": rec.day_offset,
        "activity_type": rec.activity_type,
        "input_code": rec.input_code,
        "input_name": rec.input_name,
        "typical_quantity": rec.typical_quantity,
        "typical_cost_per_acre": str(rec.typical_cost_per_acre) if rec.typical_cost_per_acre is not None else None,
        "is_critical": bool(rec.is_critical),
        "description": deepcopy(rec.description),
        "input_source": (rec.metadata_ or {}).get("input_source"),
        "is_active": bool(rec.is_active),
    }


def _custom_input_code(input_name: str, requested_code: Optional[str] = None) -> str:
    requested = (requested_code or "").strip().upper()
    if requested.startswith("CUSTOM_"):
        return requested[:50]
    slug = re.sub(r"[^A-Z0-9]+", "_", input_name.upper()).strip("_") or "LOCAL_INPUT"
    return f"CUSTOM_{slug}"[:50]


def _resolve_recommendation_input(
    db: Session,
    template: WorkflowTemplate,
    *,
    input_source: Optional[str],
    input_code: Optional[str],
    input_name: str,
) -> dict:
    source = (input_source or "").strip().upper()
    code = (input_code or "").strip().upper() or None
    catalog_item = db.query(AgriculturalInput).filter(
        AgriculturalInput.code == code,
        AgriculturalInput.is_active == True,
    ).first() if code else None
    if not source:
        if catalog_item:
            source = "CATALOG"
        else:
            raise HTTPException(400, {
                "error": "INPUT_SOURCE_REQUIRED",
                "message": "Choose a catalog input or explicitly mark the recommendation as CUSTOM.",
            })
    if source == "CATALOG":
        if not catalog_item:
            raise HTTPException(409, {
                "error": "UNKNOWN_CATALOG_INPUT",
                "message": f"Input code {code or '-'} is not an active catalog input.",
                "input_code": code,
            })
        applicable = {str(crop).upper() for crop in (catalog_item.applicable_crops or [])}
        if applicable and template.crop_code.upper() not in applicable:
            raise HTTPException(409, {
                "error": "INPUT_NOT_APPLICABLE_TO_CROP",
                "message": f"{catalog_item.code} is not applicable to {template.crop_code}.",
                "input_code": catalog_item.code,
                "crop_code": template.crop_code,
                "applicable_crops": sorted(applicable),
            })
        return {
            "input_code": catalog_item.code,
            "input_name": input_name,
            "metadata": {
                "input_source": "CATALOG",
                "catalog_input_id": str(catalog_item.id),
                "catalog_name": catalog_item.canonical_name,
                "catalog_category_code": catalog_item.category.code if catalog_item.category else None,
                "catalog_unit": catalog_item.unit,
            },
        }
    if source == "CUSTOM":
        return {
            "input_code": _custom_input_code(input_name, code),
            "input_name": input_name,
            "metadata": {"input_source": "CUSTOM", "custom_input": True},
        }
    raise HTTPException(400, {
        "error": "INVALID_INPUT_SOURCE",
        "message": "input_source must be CATALOG or CUSTOM.",
    })


def _apply_recommendation_changes(rec: WorkflowTemplateRecommendation, changes: dict) -> None:
    if "day_offset" in changes:
        if changes["day_offset"] is None:
            raise HTTPException(400, "day_offset cannot be null")
        rec.day_offset = int(changes["day_offset"])
    if "sort_order" in changes:
        if changes["sort_order"] is None:
            raise HTTPException(400, "sort_order cannot be null")
        sort_order = int(changes["sort_order"])
        if sort_order < 0:
            raise HTTPException(400, "sort_order cannot be negative")
        rec.sort_order = sort_order
    if "activity_type" in changes:
        activity_type = (changes["activity_type"] or "").strip().upper()
        if not activity_type:
            raise HTTPException(400, "activity_type cannot be empty")
        rec.activity_type = activity_type
    if "input_name" in changes:
        input_name = (changes["input_name"] or "").strip()
        if not input_name:
            raise HTTPException(400, "input_name cannot be empty")
        rec.input_name = input_name
    if "input_code" in changes:
        rec.input_code = (changes["input_code"] or None)
    if "typical_quantity" in changes:
        rec.typical_quantity = changes["typical_quantity"] or None
    if "typical_cost_per_acre" in changes:
        rec.typical_cost_per_acre = changes["typical_cost_per_acre"]
    if "is_critical" in changes:
        rec.is_critical = bool(changes["is_critical"])
    if "description" in changes:
        rec.description = changes["description"] or None




def _normalize_stage_code(value: str) -> str:
    code = re.sub(r"[^A-Z0-9_]+", "_", (value or "").upper()).strip("_")
    if not code:
        raise HTTPException(400, "stage_code cannot be empty")
    return code[:50]


def _draft_insert_order(db: Session, version_id, after_stage_code: Optional[str]) -> int:
    if after_stage_code:
        after_stage = _get_draft_stage(db, version_id, after_stage_code)
        return int(after_stage.stage_order) + 1
    max_order = (
        db.query(WorkflowTemplateStage.stage_order)
        .filter(WorkflowTemplateStage.template_version_id == version_id, WorkflowTemplateStage.is_active == True)
        .order_by(WorkflowTemplateStage.stage_order.desc())
        .first()
    )
    return int(max_order[0]) + 1 if max_order else 1


def _shift_draft_stage_orders(db: Session, version_id, insert_order: int) -> None:
    rows = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == version_id,
            WorkflowTemplateStage.is_active == True,
            WorkflowTemplateStage.stage_order >= insert_order,
        )
        .order_by(WorkflowTemplateStage.stage_order.desc())
        .all()
    )
    if not rows:
        return
    # The database has a unique (template_version_id, stage_order) constraint.
    # Move rows to a temporary high range first so the final +1 shift never
    # creates transient duplicate orders during flush/commit.
    now = datetime.now(timezone.utc)
    offset = 10000
    for row in rows:
        row.stage_order += offset
        row.updated_at = now
    db.flush()
    for row in rows:
        row.stage_order = row.stage_order - offset + 1
        row.updated_at = now


def _refresh_workflow_total_duration(db: Session, version: WorkflowTemplateVersion) -> None:
    stages = db.query(WorkflowTemplateStage).filter(
        WorkflowTemplateStage.template_version_id == version.id,
        WorkflowTemplateStage.is_active == True,
    ).all()
    version.total_duration_days = sum(int(stage.duration_days or 0) for stage in stages)
    version.updated_at = datetime.now(timezone.utc)


def _renumber_active_draft_stages(db: Session, version_id) -> None:
    stages = (
        db.query(WorkflowTemplateStage)
        .filter(WorkflowTemplateStage.template_version_id == version_id, WorkflowTemplateStage.is_active == True)
        .order_by(WorkflowTemplateStage.stage_order.asc())
        .all()
    )
    if not stages:
        return
    now = datetime.now(timezone.utc)
    offset = 10000
    for index, stage in enumerate(stages, start=1):
        stage.stage_order = offset + index
        stage.updated_at = now
    db.flush()
    for index, stage in enumerate(stages, start=1):
        stage.stage_order = index
        stage.updated_at = now


@router.post("/drafts/{workflow_template_version_id}/stages")
def create_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    body: WorkflowDraftStageCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Create a stage inside a DRAFT workflow version and shift following stages."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage_code = _normalize_stage_code(body.stage_code)
    if db.query(WorkflowTemplateStage).filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.stage_code == stage_code, WorkflowTemplateStage.is_active == True).first():
        raise HTTPException(409, "Stage code already exists in draft")
    if not body.stage_name:
        raise HTTPException(400, "stage_name is required")
    duration_days = int(body.duration_days or 0)
    if duration_days < 0:
        raise HTTPException(400, "duration_days cannot be negative")
    insert_order = _draft_insert_order(db, version.id, body.after_stage_code)
    _shift_draft_stage_orders(db, version.id, insert_order)
    now = datetime.now(timezone.utc)
    stage = WorkflowTemplateStage(
        id=uuid.uuid4(),
        template_version_id=version.id,
        stage_code=stage_code,
        stage_name=body.stage_name,
        stage_order=insert_order,
        duration_days=duration_days,
        stage_type=body.stage_type,
        phase=body.phase,
        description=body.description,
        farmer_actions=body.farmer_actions or [],
        typical_inputs=body.typical_inputs or [],
        key_observations=body.key_observations or [],
        icon=body.icon,
        color=body.color,
        created_at=now,
        updated_at=now,
    )
    db.add(stage)
    _refresh_workflow_total_duration(db, version)
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="CREATE_DRAFT_STAGE",
        target_type="STAGE",
        target_id=str(stage.id),
        target_code=stage.stage_code,
        after=_stage_audit_snapshot(stage),
        reason=f"Create draft stage {stage.stage_code}",
    )
    db.commit()
    return preview_draft_workflow_template_version(version.id, db=db, x_tenant_id=x_tenant_id)


@router.post("/drafts/{workflow_template_version_id}/stages/{stage_code}/duplicate")
def duplicate_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftStageDuplicate = WorkflowDraftStageDuplicate(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Duplicate a DRAFT workflow stage and its active recommendations."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    source_stage = _get_draft_stage(db, version.id, stage_code)
    new_code = _normalize_stage_code(body.stage_code or f"{source_stage.stage_code}_COPY")
    if db.query(WorkflowTemplateStage).filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.stage_code == new_code, WorkflowTemplateStage.is_active == True).first():
        raise HTTPException(409, "Duplicate stage code already exists in draft")
    insert_order = _draft_insert_order(db, version.id, body.after_stage_code or source_stage.stage_code)
    _shift_draft_stage_orders(db, version.id, insert_order)
    now = datetime.now(timezone.utc)
    new_stage = WorkflowTemplateStage(
        id=uuid.uuid4(),
        template_version_id=version.id,
        stage_code=new_code,
        stage_name=body.stage_name or {**(source_stage.stage_name or {}), "en": f"{(source_stage.stage_name or {}).get('en', source_stage.stage_code)} Copy"},
        stage_order=insert_order,
        duration_days=source_stage.duration_days,
        stage_type=source_stage.stage_type,
        phase=source_stage.phase,
        bbch_range=deepcopy(source_stage.bbch_range),
        propagation_step=bool(source_stage.propagation_step),
        description=deepcopy(source_stage.description),
        farmer_actions=deepcopy(source_stage.farmer_actions or []),
        typical_inputs=deepcopy(source_stage.typical_inputs or []),
        key_observations=deepcopy(source_stage.key_observations or []),
        icon=source_stage.icon,
        color=source_stage.color,
        metadata_=deepcopy(source_stage.metadata_ or {}),
        created_at=now,
        updated_at=now,
    )
    db.add(new_stage)
    db.flush()
    source_recs = db.query(WorkflowTemplateRecommendation).filter(WorkflowTemplateRecommendation.template_stage_id == source_stage.id, WorkflowTemplateRecommendation.is_active == True).order_by(WorkflowTemplateRecommendation.sort_order.asc()).all()
    for rec in source_recs:
        db.add(WorkflowTemplateRecommendation(
            id=uuid.uuid4(),
            template_stage_id=new_stage.id,
            sort_order=rec.sort_order,
            day_offset=rec.day_offset,
            activity_type=rec.activity_type,
            input_code=rec.input_code,
            input_name=rec.input_name,
            typical_quantity=rec.typical_quantity,
            typical_cost_per_acre=rec.typical_cost_per_acre,
            is_critical=bool(rec.is_critical),
            description=deepcopy(rec.description),
            metadata_=deepcopy(rec.metadata_ or {}),
            created_at=now,
            updated_at=now,
        ))
    _refresh_workflow_total_duration(db, version)
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="DUPLICATE_DRAFT_STAGE",
        target_type="STAGE",
        target_id=str(new_stage.id),
        target_code=new_stage.stage_code,
        before=_stage_audit_snapshot(source_stage),
        after={**_stage_audit_snapshot(new_stage), "recommendation_count": len(source_recs)},
        reason=f"Duplicate draft stage {source_stage.stage_code} as {new_stage.stage_code}",
    )
    db.commit()
    return preview_draft_workflow_template_version(version.id, db=db, x_tenant_id=x_tenant_id)


@router.post("/drafts/{workflow_template_version_id}/stages/{stage_code}/restore")
def restore_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftStageRestore = WorkflowDraftStageRestore(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Restore a soft-deleted stage in a DRAFT workflow version and reactivate its recommendations."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == version.id,
            WorkflowTemplateStage.stage_code == stage_code,
            WorkflowTemplateStage.is_active == False,
        )
        .first()
    )
    if not stage:
        raise HTTPException(404, "Deleted draft workflow stage not found")
    if db.query(WorkflowTemplateStage).filter(
        WorkflowTemplateStage.template_version_id == version.id,
        WorkflowTemplateStage.stage_code == stage.stage_code,
        WorkflowTemplateStage.is_active == True,
    ).first():
        raise HTTPException(409, "An active stage with this code already exists")

    before = _stage_audit_snapshot(stage)
    insert_order = _draft_insert_order(db, version.id, body.after_stage_code)
    _shift_draft_stage_orders(db, version.id, insert_order)
    now = datetime.now(timezone.utc)
    stage.is_active = True
    stage.stage_order = insert_order
    stage.updated_at = now
    recs = db.query(WorkflowTemplateRecommendation).filter(
        WorkflowTemplateRecommendation.template_stage_id == stage.id,
    ).all()
    for rec in recs:
        rec.is_active = True
        rec.updated_at = now
    _refresh_workflow_total_duration(db, version)
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="RESTORE_DRAFT_STAGE",
        target_type="STAGE",
        target_id=str(stage.id),
        target_code=stage.stage_code,
        before=before,
        after={**_stage_audit_snapshot(stage), "reactivated_recommendation_count": len(recs)},
        metadata={"after_stage_code": body.after_stage_code},
        reason=f"Restore draft stage {stage.stage_code}",
    )
    db.commit()
    return preview_draft_workflow_template_version(version.id, db=db, x_tenant_id=x_tenant_id)


@router.delete("/drafts/{workflow_template_version_id}/stages/{stage_code}")
def delete_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Soft-delete a stage from a DRAFT workflow version and deactivate its recommendations."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    active_stage_count = db.query(WorkflowTemplateStage).filter(
        WorkflowTemplateStage.template_version_id == version.id,
        WorkflowTemplateStage.is_active == True,
    ).count()
    if active_stage_count <= 1:
        raise HTTPException(400, "Draft workflow must keep at least one active stage")
    stage = _get_draft_stage(db, version.id, stage_code)
    before = _stage_audit_snapshot(stage)
    recs = db.query(WorkflowTemplateRecommendation).filter(
        WorkflowTemplateRecommendation.template_stage_id == stage.id,
        WorkflowTemplateRecommendation.is_active == True,
    ).all()
    now = datetime.now(timezone.utc)
    for rec in recs:
        rec.is_active = False
        rec.updated_at = now
    stage.is_active = False
    # Inactive stages still participate in the unique stage_order constraint,
    # so move the deleted stage out of the active order range before renumbering.
    stage.stage_order = 90000 + int(stage.stage_order or 0)
    stage.updated_at = now
    db.flush()
    _renumber_active_draft_stages(db, version.id)
    _refresh_workflow_total_duration(db, version)
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="DELETE_DRAFT_STAGE",
        target_type="STAGE",
        target_id=str(stage.id),
        target_code=stage.stage_code,
        before=before,
        after={"stage_code": stage.stage_code, "is_active": False, "deactivated_recommendation_count": len(recs)},
        metadata={"remaining_stage_count": active_stage_count - 1},
        reason=f"Delete draft stage {stage.stage_code}",
    )
    db.commit()
    return preview_draft_workflow_template_version(version.id, db=db, x_tenant_id=x_tenant_id)


@router.post("/drafts/{workflow_template_version_id}/stages/{stage_code}/recommendations")
def create_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftRecommendationCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Add a recommendation to a stage inside a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage = _get_draft_stage(db, version.id, stage_code)
    activity_type = (body.activity_type or "").strip().upper()
    input_name = (body.input_name or "").strip()
    if not activity_type:
        raise HTTPException(400, "activity_type cannot be empty")
    if not input_name:
        raise HTTPException(400, "input_name cannot be empty")
    if body.sort_order is not None and body.sort_order < 0:
        raise HTTPException(400, "sort_order cannot be negative")
    resolved_input = _resolve_recommendation_input(
        db,
        template,
        input_source=body.input_source,
        input_code=body.input_code,
        input_name=input_name,
    )

    max_sort_order = (
        db.query(WorkflowTemplateRecommendation.sort_order)
        .filter(
            WorkflowTemplateRecommendation.template_stage_id == stage.id,
            WorkflowTemplateRecommendation.is_active == True,
        )
        .order_by(WorkflowTemplateRecommendation.sort_order.desc())
        .first()
    )
    sort_order = body.sort_order if body.sort_order is not None else ((max_sort_order[0] if max_sort_order else 0) + 1)
    now = datetime.now(timezone.utc)
    new_rec = WorkflowTemplateRecommendation(
        id=uuid.uuid4(),
        template_stage_id=stage.id,
        sort_order=sort_order,
        day_offset=int(body.day_offset or 0),
        activity_type=activity_type,
        input_code=resolved_input["input_code"],
        input_name=resolved_input["input_name"],
        typical_quantity=body.typical_quantity or None,
        typical_cost_per_acre=body.typical_cost_per_acre,
        is_critical=bool(body.is_critical),
        description=body.description or None,
        metadata_={"source": "draft_admin", **resolved_input["metadata"]},
        created_at=now,
        updated_at=now,
    )
    db.add(new_rec)
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=principal.user_id,
        action="CREATE_RECOMMENDATION",
        target_type="RECOMMENDATION",
        target_id=str(new_rec.id),
        target_code=f"{stage.stage_code}|{new_rec.input_code or new_rec.input_name}",
        after=_recommendation_audit_snapshot(new_rec),
        metadata={"stage_code": stage.stage_code},
    )
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.patch("/drafts/{workflow_template_version_id}/recommendations/reorder")
def reorder_draft_workflow_recommendations(
    workflow_template_version_id: uuid.UUID,
    body: WorkflowDraftRecommendationReorder,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Reorder all active recommendations for one stage in a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage = _get_draft_stage(db, version.id, body.stage_code)
    requested_ids = list(body.recommendation_ids or [])
    if not requested_ids:
        raise HTTPException(400, "recommendation_ids cannot be empty")
    requested_id_strings = [str(rec_id) for rec_id in requested_ids]
    if len(requested_id_strings) != len(set(requested_id_strings)):
        raise HTTPException(400, "recommendation_ids contains duplicate values")

    recs = (
        db.query(WorkflowTemplateRecommendation)
        .filter(
            WorkflowTemplateRecommendation.template_stage_id == stage.id,
            WorkflowTemplateRecommendation.is_active == True,
        )
        .order_by(WorkflowTemplateRecommendation.sort_order.asc())
        .all()
    )
    recs_by_id = {str(rec.id): rec for rec in recs}
    existing_ids = set(recs_by_id.keys())
    requested_set = set(requested_id_strings)
    missing = sorted(existing_ids - requested_set)
    unknown = sorted(requested_set - existing_ids)
    if missing or unknown:
        raise HTTPException(
            400,
            {
                "message": "recommendation_ids must include every active recommendation for the stage exactly once",
                "missing_recommendation_ids": missing,
                "unknown_recommendation_ids": unknown,
            },
        )

    before = [_recommendation_audit_snapshot(rec) for rec in recs]
    now = datetime.now(timezone.utc)
    for index, rec_id in enumerate(requested_id_strings, start=1):
        rec = recs_by_id[rec_id]
        rec.sort_order = index
        rec.updated_at = now
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=_actor_uuid(x_actor_id) or principal.user_id,
        action="REORDER_DRAFT_RECOMMENDATIONS",
        target_type="STAGE",
        target_id=str(stage.id),
        target_code=stage.stage_code,
        before={"recommendations": before},
        after={"stage_code": stage.stage_code, "recommendation_ids": requested_id_strings},
        metadata={"recommendation_count": len(requested_id_strings)},
        reason=f"Reorder draft recommendations for {stage.stage_code}",
    )
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.patch("/drafts/{workflow_template_version_id}/recommendations/{recommendation_id}")
def update_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    body: WorkflowDraftRecommendationUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Edit a recommendation inside a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    rec = _get_draft_recommendation(db, version.id, recommendation_id)
    before = _recommendation_audit_snapshot(rec)
    changes = body.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No recommendation changes supplied")
    requested_source = changes.pop("input_source", None)
    if requested_source is not None or "input_code" in changes or "input_name" in changes:
        resolved_input = _resolve_recommendation_input(
            db,
            template,
            input_source=requested_source or (rec.metadata_ or {}).get("input_source"),
            input_code=changes.get("input_code", rec.input_code),
            input_name=(changes.get("input_name", rec.input_name) or "").strip(),
        )
        changes["input_code"] = resolved_input["input_code"]
        changes["input_name"] = resolved_input["input_name"]
        rec.metadata_ = {**(rec.metadata_ or {}), **resolved_input["metadata"]}
    _apply_recommendation_changes(rec, changes)
    now = datetime.now(timezone.utc)
    rec.updated_at = now
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=principal.user_id,
        action="UPDATE_RECOMMENDATION",
        target_type="RECOMMENDATION",
        target_id=str(rec.id),
        target_code=rec.input_code or rec.input_name,
        before=before,
        after=_recommendation_audit_snapshot(rec),
        metadata={"changed_fields": sorted(changes.keys())},
    )
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.delete("/drafts/{workflow_template_version_id}/recommendations/{recommendation_id}")
def delete_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Soft-delete a recommendation from a DRAFT workflow version."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    rec = _get_draft_recommendation(db, version.id, recommendation_id)
    before = _recommendation_audit_snapshot(rec)
    now = datetime.now(timezone.utc)
    rec.is_active = False
    rec.updated_at = now
    version.updated_at = now
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=principal.user_id,
        action="DELETE_RECOMMENDATION",
        target_type="RECOMMENDATION",
        target_id=str(rec.id),
        target_code=rec.input_code or rec.input_name,
        before=before,
        after=_recommendation_audit_snapshot(rec),
    )
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.get("/drafts/{workflow_template_version_id}/publish-impact")
def get_draft_publish_impact(
    workflow_template_version_id: uuid.UUID,
    archive_previous: bool = Query(True),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Preview which existing published versions/cycles would be affected by publishing this draft."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    return _draft_publish_impact(db, template, version, archive_previous)


@router.post("/drafts/{workflow_template_version_id}/publish")
def publish_draft_workflow_template_version(
    workflow_template_version_id: uuid.UUID,
    body: WorkflowDraftPublishRequest = WorkflowDraftPublishRequest(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    """Publish a validated DRAFT workflow version and make it Android-visible."""
    template, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stages, validation = _draft_validation(db, version.id)
    if not validation["can_publish"]:
        raise HTTPException(400, {"message": "Draft workflow has blocking validation errors", "validation": validation})
    now = datetime.now(timezone.utc)
    publish_impact = _draft_publish_impact(db, template, version, body.archive_previous)

    if body.archive_previous:
        previous_versions = (
            db.query(WorkflowTemplateVersion)
            .filter(
                WorkflowTemplateVersion.template_id == template.id,
                WorkflowTemplateVersion.id != version.id,
                WorkflowTemplateVersion.status == "PUBLISHED",
                WorkflowTemplateVersion.is_active == True,
            )
            .all()
        )
        impact_by_version = {row["workflow_template_version_id"]: row for row in publish_impact["impacted_published_versions"]}
        for previous in previous_versions:
            impact = impact_by_version.get(str(previous.id), {})
            previous.status = "ARCHIVED"
            previous.effective_to = now.date()
            previous.updated_at = now
            previous_metadata = dict(previous.metadata_ or {})
            previous_metadata["archived_by_publish"] = True
            previous_metadata["archived_at"] = now.isoformat()
            previous_metadata["archived_for_new_catalog_only"] = True
            previous_metadata["pinned_cycle_count_at_archive"] = impact.get("pinned_cycle_count", 0)
            previous_metadata["active_pinned_cycle_count_at_archive"] = impact.get("active_pinned_cycle_count", 0)
            previous.metadata_ = previous_metadata

    published_by = principal.user_id
    before = {"status": version.status, "published_at": version.published_at.isoformat() if version.published_at else None}

    version.status = "PUBLISHED"
    version.published_at = now
    version.published_by = published_by
    version.total_duration_days = sum(int(stage.get("duration_days") or 0) for stage in stages)
    version.updated_at = now
    metadata = dict(version.metadata_ or {})
    metadata["published_from_draft"] = True
    metadata["published_at"] = now.isoformat()
    version.metadata_ = metadata
    _record_workflow_audit_event(
        db,
        tenant_id=x_tenant_id,
        template_id=template.id,
        template_version_id=version.id,
        actor_id=published_by,
        action="PUBLISH_DRAFT",
        target_type="VERSION",
        target_id=str(version.id),
        before=before,
        after={
            "status": "PUBLISHED",
            "published_at": now.isoformat(),
            "archive_previous": body.archive_previous,
            "publish_impact": publish_impact,
        },
        metadata={"validation_counts": validation["counts"], "publish_impact": publish_impact},
    )
    db.commit()
    db.refresh(version)
    payload = _render_published_version_preview(db, template, version, x_tenant_id)
    payload["warnings"] = validation["issues"]
    payload["validation"] = validation
    payload["publish_impact"] = publish_impact
    return payload


def _next_draft_version_number(db: Session, template_id: uuid.UUID, source_version: str, requested: Optional[str]) -> str:
    if requested:
        candidate = requested
    else:
        candidate = f"{source_version}-draft"
    existing = {
        row.version_number
        for row in db.query(WorkflowTemplateVersion.version_number)
        .filter(WorkflowTemplateVersion.template_id == template_id)
        .all()
    }
    if candidate not in existing:
        return candidate
    base = candidate
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _version_row_for_template(
    db: Session,
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    tenant_id: str,
    allowed_statuses: set[str],
    not_found_message: str,
):
    row = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplate.id == template_id,
            WorkflowTemplateVersion.id == version_id,
            WorkflowTemplateVersion.template_id == template_id,
            WorkflowTemplate.is_active == True,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status.in_(allowed_statuses),
            WorkflowTemplate.tenant_id.in_([tenant_id, "default"]),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, not_found_message)
    return row


def _copy_workflow_version_to_draft(
    db: Session,
    template: WorkflowTemplate,
    source_version: WorkflowTemplateVersion,
    requested_version_number: Optional[str],
    *,
    tenant_id: str,
    actor_id=None,
    action: str = "CLONE_DRAFT",
) -> dict:
    now = datetime.now(timezone.utc)
    draft_version_id = uuid.uuid4()
    draft_version_number = _next_draft_version_number(db, template.id, source_version.version_number, requested_version_number)
    draft_metadata = deepcopy(source_version.metadata_ or {})
    draft_metadata.update({
        "source_version_id": str(source_version.id),
        "source_version_number": source_version.version_number,
        "cloned_from_status": source_version.status,
    })
    draft_version = WorkflowTemplateVersion(
        id=draft_version_id,
        template_id=template.id,
        version_number=draft_version_number,
        status="DRAFT",
        effective_from=source_version.effective_from,
        effective_to=source_version.effective_to,
        total_duration_days=source_version.total_duration_days,
        schema_version=source_version.schema_version,
        metadata_=draft_metadata,
        published_at=None,
        published_by=None,
        created_at=now,
        updated_at=now,
    )
    db.add(draft_version)
    db.flush()

    source_stages = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == source_version.id,
            WorkflowTemplateStage.is_active == True,
        )
        .order_by(WorkflowTemplateStage.stage_order)
        .all()
    )
    stage_id_map = {}
    for stage in source_stages:
        new_stage_id = uuid.uuid4()
        stage_id_map[stage.id] = new_stage_id
        db.add(WorkflowTemplateStage(
            id=new_stage_id,
            template_version_id=draft_version_id,
            stage_code=stage.stage_code,
            stage_name=deepcopy(stage.stage_name or {}),
            stage_order=stage.stage_order,
            duration_days=stage.duration_days,
            stage_type=stage.stage_type,
            phase=stage.phase,
            bbch_range=deepcopy(stage.bbch_range),
            propagation_step=stage.propagation_step,
            description=deepcopy(stage.description),
            farmer_actions=deepcopy(stage.farmer_actions or []),
            typical_inputs=deepcopy(stage.typical_inputs or []),
            key_observations=deepcopy(stage.key_observations or []),
            icon=stage.icon,
            color=stage.color,
            metadata_=deepcopy(stage.metadata_ or {}),
            created_at=now,
            updated_at=now,
        ))

    db.flush()

    source_recommendations = []
    if source_stages:
        source_recommendations = (
            db.query(WorkflowTemplateRecommendation)
            .filter(
                WorkflowTemplateRecommendation.template_stage_id.in_([stage.id for stage in source_stages]),
                WorkflowTemplateRecommendation.is_active == True,
            )
            .order_by(
                WorkflowTemplateRecommendation.template_stage_id,
                WorkflowTemplateRecommendation.sort_order,
                WorkflowTemplateRecommendation.day_offset,
            )
            .all()
        )
        for rec in source_recommendations:
            db.add(WorkflowTemplateRecommendation(
                id=uuid.uuid4(),
                template_stage_id=stage_id_map[rec.template_stage_id],
                sort_order=rec.sort_order,
                day_offset=rec.day_offset,
                activity_type=rec.activity_type,
                input_code=rec.input_code,
                input_name=rec.input_name,
                typical_quantity=rec.typical_quantity,
                typical_cost_per_acre=rec.typical_cost_per_acre,
                is_critical=rec.is_critical,
                description=deepcopy(rec.description),
                metadata_=deepcopy(rec.metadata_ or {}),
                created_at=now,
                updated_at=now,
            ))

    _record_workflow_audit_event(
        db,
        tenant_id=tenant_id,
        template_id=template.id,
        template_version_id=draft_version_id,
        actor_id=actor_id,
        action=action,
        target_type="VERSION",
        target_id=str(draft_version_id),
        before={"source_version_id": str(source_version.id), "source_status": source_version.status},
        after={"draft_version_id": str(draft_version_id), "version": draft_version_number, "status": "DRAFT"},
        metadata={"stage_count": len(source_stages), "recommendation_count": len(source_recommendations)},
    )
    db.commit()
    return {
        "schema_version": "1.0.0",
        "workflow_template_id": str(template.id),
        "source_version_id": str(source_version.id),
        "draft_version_id": str(draft_version_id),
        "version": draft_version_number,
        "status": "DRAFT",
        "stage_count": len(source_stages),
        "recommendation_count": len(source_recommendations),
    }


def _workflow_version_summary(
    db: Session,
    template: WorkflowTemplate,
    version: WorkflowTemplateVersion,
    current_published_version_id,
) -> dict:
    stage_count = db.query(WorkflowTemplateStage).filter(
        WorkflowTemplateStage.template_version_id == version.id,
        WorkflowTemplateStage.is_active == True,
    ).count()
    stage_ids = [
        row.id
        for row in db.query(WorkflowTemplateStage.id)
        .filter(WorkflowTemplateStage.template_version_id == version.id, WorkflowTemplateStage.is_active == True)
        .all()
    ]
    recommendation_count = 0
    if stage_ids:
        recommendation_count = db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_(stage_ids),
            WorkflowTemplateRecommendation.is_active == True,
        ).count()
    usage = _workflow_version_usage_counts(db, version.id)
    pinned_cycle_count = usage["pinned_cycle_count"]
    active_pinned_cycle_count = usage["active_pinned_cycle_count"]
    return {
        "workflow_template_id": str(template.id),
        "workflow_template_version_id": str(version.id),
        "workflow_template_code": template.code,
        "version": version.version_number,
        "status": version.status,
        "is_current_published": bool(current_published_version_id and version.id == current_published_version_id),
        "effective_from": version.effective_from.isoformat() if version.effective_from else None,
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "published_by": str(version.published_by) if version.published_by else None,
        "total_duration_days": version.total_duration_days,
        "stage_count": stage_count,
        "recommendation_count": recommendation_count,
        "pinned_cycle_count": pinned_cycle_count,
        "active_pinned_cycle_count": active_pinned_cycle_count,
        "usage_count": pinned_cycle_count,
        "active_usage_count": active_pinned_cycle_count,
        "is_read_only_for_existing_cycles": pinned_cycle_count > 0,
        "schema_version": version.schema_version,
        "metadata": version.metadata_ or {},
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "updated_at": version.updated_at.isoformat() if version.updated_at else None,
    }


@router.get("/legacy-cycle-pins")
def list_legacy_cycle_pin_candidates(
    project_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season_code: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Report legacy crop cycles that are not pinned to a workflow version yet."""
    candidates = _legacy_cycle_pin_candidates(
        db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        crop_code=crop_code,
        season_code=season_code,
        limit=limit,
    )
    rows = [_legacy_cycle_pin_row(candidate) for candidate in candidates]
    eligible_count = sum(1 for row in rows if row["eligible_for_backfill"])
    by_reason = {}
    for row in rows:
        by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
    return {
        "schema_version": "workflow_legacy_cycle_pins.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "crop_code": crop_code.upper() if crop_code else None,
            "season_code": season_code.upper() if season_code else None,
            "limit": limit,
        },
        "counts": {
            "total": len(rows),
            "eligible": eligible_count,
            "blocked": len(rows) - eligible_count,
            "by_reason": by_reason,
        },
        "cycles": rows,
    }


@router.post("/legacy-cycle-pins/backfill")
def backfill_legacy_cycle_pins(
    body: WorkflowLegacyCycleBackfillRequest = WorkflowLegacyCycleBackfillRequest(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    """Pin eligible legacy crop cycles to their matching published workflow version."""
    candidates = _legacy_cycle_pin_candidates(
        db,
        tenant_id=x_tenant_id,
        project_id=body.project_id,
        crop_code=body.crop_code,
        season_code=body.season_code,
        limit=body.limit,
    )
    rows = [_legacy_cycle_pin_row(candidate) for candidate in candidates]
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    pinned_by_version = {}
    if not body.dry_run:
        now = datetime.now(timezone.utc)
        for candidate in eligible:
            cycle = candidate["cycle"]
            version = candidate["workflow_version"]
            cycle.workflow_template_version_id = version.id
            cycle.updated_at = now
            key = (candidate["workflow_template"].id, version.id, candidate["workflow_template"].code, version.version_number)
            pinned_by_version[key] = pinned_by_version.get(key, 0) + 1
        actor_id = principal.user_id
        for (template_id, version_id, template_code, version_number), count in pinned_by_version.items():
            _record_workflow_audit_event(
                db,
                tenant_id=x_tenant_id,
                template_id=template_id,
                template_version_id=version_id,
                actor_id=actor_id,
                action="LEGACY_CYCLE_PIN_BACKFILL",
                target_type="CROP_CYCLE",
                target_id=None,
                target_code=template_code,
                before={"workflow_template_version_id": None},
                after={"workflow_template_version_id": str(version_id), "version": version_number, "cycle_count": count},
                reason=body.reason or "Backfill legacy crop cycles to matching published workflow version",
                metadata={"cycle_count": count, "dry_run": False},
            )
        db.commit()
    return {
        "schema_version": "workflow_legacy_cycle_backfill.v1",
        "tenant_id": x_tenant_id,
        "dry_run": body.dry_run,
        "requested_limit": body.limit,
        "counts": {
            "scanned": len(rows),
            "eligible": len(eligible),
            "pinned": 0 if body.dry_run else len(eligible),
            "blocked": len(rows) - len(eligible),
        },
        "cycles": rows,
    }


@router.get("/templates/{template_id}/versions")
def list_workflow_template_versions(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return version history for a workflow template, including DRAFT/PUBLISHED/ARCHIVED rows."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.is_active == True,
        WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
    ).first()
    if not template:
        raise HTTPException(404, "Workflow template not found")

    versions = db.query(WorkflowTemplateVersion).filter(
        WorkflowTemplateVersion.template_id == template.id,
        WorkflowTemplateVersion.is_active == True,
    ).order_by(
        WorkflowTemplateVersion.published_at.desc().nullslast(),
        WorkflowTemplateVersion.created_at.desc(),
    ).all()
    current_published = (
        db.query(WorkflowTemplateVersion)
        .filter(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        )
        .order_by(WorkflowTemplateVersion.published_at.desc().nullslast(), WorkflowTemplateVersion.created_at.desc())
        .first()
    )
    items = [_workflow_version_summary(db, template, version, current_published.id if current_published else None) for version in versions]
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "workflow_template_id": str(template.id),
        "workflow_template_code": template.code,
        "label": {"en": template.canonical_name, "hi": template.canonical_name},
        "crop_code": template.crop_code,
        "season_code": template.season_code,
        "propagation_type_code": template.propagation_type_code,
        "current_published_version_id": str(current_published.id) if current_published else None,
        "counts": {
            "total": len(items),
            "draft": sum(1 for item in items if item["status"] == "DRAFT"),
            "published": sum(1 for item in items if item["status"] == "PUBLISHED"),
            "archived": sum(1 for item in items if item["status"] == "ARCHIVED"),
        },
        "versions": items,
    }


@router.get("/templates/{template_id}/audit")
def list_workflow_template_audit_events(
    template_id: uuid.UUID,
    version_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return workflow template audit trail for admin governance."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.is_active == True,
        WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
    ).first()
    if not template:
        raise HTTPException(404, "Workflow template not found")

    db.commit()
    query = db.query(WorkflowTemplateAuditEvent).filter(
        WorkflowTemplateAuditEvent.tenant_id == x_tenant_id,
        WorkflowTemplateAuditEvent.template_id == template.id,
    )
    if version_id:
        query = query.filter(WorkflowTemplateAuditEvent.template_version_id == version_id)
    if action:
        query = query.filter(WorkflowTemplateAuditEvent.action == action.upper())
    if actor_id:
        query = query.filter(WorkflowTemplateAuditEvent.actor_id == actor_id)

    events = query.order_by(WorkflowTemplateAuditEvent.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "workflow_template_id": str(template.id),
        "workflow_template_code": template.code,
        "count": len(events),
        "events": [_audit_payload(event) for event in events],
    }


@router.post("/templates/{template_id}/versions/{version_id}/restore-draft")
def restore_workflow_template_version_to_draft(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    body: WorkflowDraftCloneRequest = WorkflowDraftCloneRequest(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    """Restore a published/archived workflow version into a new editable draft."""
    template, source_version = _version_row_for_template(
        db,
        template_id,
        version_id,
        x_tenant_id,
        {"PUBLISHED", "ARCHIVED"},
        "Published or archived workflow template version not found",
    )
    return _copy_workflow_version_to_draft(
        db, template, source_version, body.version_number, tenant_id=x_tenant_id, actor_id=principal.user_id, action="RESTORE_DRAFT"
    )


@router.post("/templates/{template_id}/versions/{version_id}/clone-draft")
def clone_workflow_template_version_to_draft(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    body: WorkflowDraftCloneRequest = WorkflowDraftCloneRequest(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Clone a published workflow version into an editable draft version."""
    template, source_version = _version_row_for_template(
        db,
        template_id,
        version_id,
        x_tenant_id,
        {"PUBLISHED"},
        "Published workflow template version not found",
    )
    return _copy_workflow_version_to_draft(
        db, template, source_version, body.version_number, tenant_id=x_tenant_id, actor_id=principal.user_id, action="CLONE_DRAFT"
    )


@router.get("/projects/{project_id}/workflow-overrides")
def list_project_workflow_overrides(
    project_id: uuid.UUID,
    template_version_id: Optional[uuid.UUID] = Query(None),
    include_inactive: bool = Query(True),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return project workflow override history, including archived rows by default."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    query = db.query(WorkflowTemplateOverride).filter(
        WorkflowTemplateOverride.project_id == project_id,
        WorkflowTemplateOverride.tenant_id == x_tenant_id,
    )
    if template_version_id:
        query = query.filter(WorkflowTemplateOverride.template_version_id == template_version_id)
    if not include_inactive:
        query = query.filter(WorkflowTemplateOverride.is_active == True)

    overrides = query.order_by(
        WorkflowTemplateOverride.is_active.desc(),
        WorkflowTemplateOverride.updated_at.desc(),
        WorkflowTemplateOverride.created_at.desc(),
    ).all()
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "template_version_id": str(template_version_id) if template_version_id else None,
        "include_inactive": include_inactive,
        "counts": {
            "total": len(overrides),
            "active": sum(1 for override in overrides if override.is_active),
            "inactive": sum(1 for override in overrides if not override.is_active),
        },
        "overrides": [_override_payload(override) for override in overrides],
    }


@router.get("/projects/{project_id}/workflow-enablements")
def get_project_workflow_enablements(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Return read-only workflow visibility status for a project."""
    return _project_workflow_enablement_summary(db, project_id, x_tenant_id)


@router.put("/projects/{project_id}/workflow-enablements/{workflow_template_id}")
def upsert_project_workflow_enablement(
    project_id: uuid.UUID,
    workflow_template_id: uuid.UUID,
    body: WorkflowEnablementUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    """Create/update a project-level workflow enablement row.

    This is the first safe admin write: it controls project visibility only and
    does not edit workflow template content.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _assert_project_workflow_editable(db, project, x_tenant_id)

    template = (
        db.query(WorkflowTemplate)
        .filter(
            WorkflowTemplate.id == workflow_template_id,
            WorkflowTemplate.is_active == True,
            WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
        )
        .first()
    )
    if not template:
        raise HTTPException(404, "Workflow template not found")
    project_crop_scope = {str(code).upper() for code in (project.crop_scope or [])}
    if body.enabled and project_crop_scope and template.crop_code.upper() not in project_crop_scope:
        raise HTTPException(
            409,
            {
                "message": "Workflow cannot be enabled because the project crop scope does not include this crop.",
                "assignment_rule": "BLOCKED_BY_PROJECT_CROP_SCOPE",
                "crop_code": template.crop_code,
                "project_crop_scope": sorted(project_crop_scope),
            },
        )

    enablement = (
        db.query(WorkflowTemplateEnablement)
        .filter(
            WorkflowTemplateEnablement.tenant_id == x_tenant_id,
            WorkflowTemplateEnablement.project_id == project_id,
            WorkflowTemplateEnablement.template_id == workflow_template_id,
        )
        .first()
    )
    if not enablement:
        enablement = WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            project_id=project_id,
            template_id=workflow_template_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(enablement)

    enablement.enabled = body.enabled
    enablement.display_order = body.display_order if body.display_order is not None else (enablement.display_order or 0)
    if body.display_label is not None:
        enablement.display_label = body.display_label
    enablement.is_active = True
    enablement.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _project_workflow_enablement_summary(db, project_id, x_tenant_id)




@router.post("/projects/{project_id}/workflow-overrides")
def create_project_workflow_override(
    project_id: uuid.UUID,
    body: WorkflowOverrideCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    """Create a project-level workflow override and return updated preview.

    This customizes project rendering without mutating the base workflow template.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _assert_project_workflow_editable(db, project, x_tenant_id)

    version_row = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplateVersion.id == body.template_version_id,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplate.is_active == True,
            WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
        )
        .first()
    )
    if not version_row:
        raise HTTPException(404, "Workflow template version not found")

    target_type = body.target_type.upper()
    operation = body.operation.upper()
    if target_type not in ("STAGE", "RECOMMENDATION"):
        raise HTTPException(400, "target_type must be STAGE or RECOMMENDATION")
    if operation not in ("HIDE", "RENAME", "CHANGE_DURATION", "CHANGE_OFFSET", "CHANGE_QUANTITY", "ADD_RECOMMENDATION"):
        raise HTTPException(400, "Unsupported override operation")
    override_payload = deepcopy(body.override_payload or {})
    _validate_override_payload(target_type, operation, override_payload)
    template, _ = version_row
    if operation == "ADD_RECOMMENDATION":
        input_name = str(override_payload.get("input_name") or "").strip()
        resolved_input = _resolve_recommendation_input(
            db,
            template,
            input_source=override_payload.get("input_source"),
            input_code=override_payload.get("input_code"),
            input_name=input_name,
        )
        if resolved_input["metadata"]["input_source"] == "CATALOG":
            assert_catalog_input_allowed_for_project_crop(
                db,
                tenant_id=x_tenant_id,
                project_id=project_id,
                crop_code=template.crop_code,
                input_code=resolved_input["input_code"],
            )
        override_payload["input_code"] = resolved_input["input_code"]
        override_payload["input_name"] = resolved_input["input_name"]
        override_payload["metadata"] = {
            **(override_payload.get("metadata") or {}),
            **resolved_input["metadata"],
        }

    override = WorkflowTemplateOverride(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=project_id,
        template_version_id=body.template_version_id,
        target_type=target_type,
        target_code=body.target_code,
        operation=operation,
        override_payload=override_payload,
        priority=body.priority,
        reason=body.reason,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(override)
    db.commit()
    return preview_workflow_template_version(body.template_version_id, project_id, db, x_tenant_id)


@router.delete("/projects/{project_id}/workflow-overrides/{override_id}")
def delete_project_workflow_override(
    project_id: uuid.UUID,
    override_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(
        require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)
    ),
):
    """Archive a project-level override and return updated preview."""
    override = (
        db.query(WorkflowTemplateOverride)
        .filter(
            WorkflowTemplateOverride.id == override_id,
            WorkflowTemplateOverride.project_id == project_id,
            WorkflowTemplateOverride.tenant_id == x_tenant_id,
            WorkflowTemplateOverride.is_active == True,
        )
        .first()
    )
    if not override:
        raise HTTPException(404, "Workflow override not found")
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _assert_project_workflow_editable(db, project, x_tenant_id)

    version_id = override.template_version_id
    override.is_active = False
    override.updated_at = datetime.now(timezone.utc)
    db.commit()
    return preview_workflow_template_version(version_id, project_id, db, x_tenant_id)
