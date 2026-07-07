"""Read-only workflow catalog APIs.

These endpoints tell Android/admin clients which published crop workflows are
visible for a tenant/project. Admin write APIs can build on the same tables later.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, Crop
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateEnablement,
    WorkflowTemplateOverride,
    WorkflowTemplateRecommendation,
    WorkflowTemplateStage,
    WorkflowTemplateVersion,
)
from app.modules.workflow.template_service import (
    list_enabled_workflow_versions,
    workflow_template_metadata,
    scoped_overrides,
    workflow_version_to_stage_definitions,
    workflow_version_to_stage_definitions_for_scope,
)

router = APIRouter(prefix="/api/v1/workflow-catalog", tags=["workflow-catalog"])


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
    activity_type: str
    input_code: Optional[str] = None
    input_name: str
    typical_quantity: Optional[str] = None
    typical_cost_per_acre: Optional[float] = None
    is_critical: bool = False
    description: Optional[dict[str, str]] = None
    sort_order: Optional[int] = None


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

    crop_codes = sorted({template.crop_code for template, _ in version_rows})
    crops_by_code = {
        crop.code: crop
        for crop in db.query(Crop).filter(Crop.code.in_(crop_codes)).all()
    } if crop_codes else {}

    workflows = []
    for template, version in version_rows:
        enablement = project_enablement_by_template.get(template.id) or tenant_enablement_by_template.get(template.id)
        scope = "project" if template.id in project_enablement_by_template else "tenant" if template.id in tenant_enablement_by_template else "implicit_default"
        enabled = bool(enablement.enabled) if enablement else (not explicit_scope and template.is_default)
        visibility_status = "ENABLED" if enabled and enablement else "DISABLED" if enablement and not enablement.enabled else "IMPLICIT_DEFAULT" if enabled else "NOT_VISIBLE"
        overrides = scoped_overrides(db, template_version_id=version.id, tenant_id=tenant_id, project_id=project_id)
        crop = crops_by_code.get(template.crop_code)
        workflows.append({
            "workflow_template_id": str(template.id),
            "workflow_template_version_id": str(version.id),
            "workflow_template_code": template.code,
            "version": version.version_number,
            "status": version.status,
            "visibility_status": visibility_status,
            "enablement_scope": scope,
            "enabled": enabled,
            "display_order": enablement.display_order if enablement else None,
            "label": _label(template, enablement),
            "crop_code": template.crop_code,
            "crop_name": crop.canonical_name if crop else template.crop_code,
            "season_code": template.season_code,
            "propagation_type_code": template.propagation_type_code,
            "total_duration_days": version.total_duration_days,
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
        "counts": {
            "total": len(workflows),
            "enabled": sum(1 for item in workflows if item["enabled"]),
            "disabled": sum(1 for item in workflows if item["visibility_status"] == "DISABLED"),
            "implicit_default": sum(1 for item in workflows if item["visibility_status"] == "IMPLICIT_DEFAULT"),
            "not_visible": sum(1 for item in workflows if item["visibility_status"] == "NOT_VISIBLE"),
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
            if not input_code:
                warnings.append({"level": "WARN", "code": "RECOMMENDATION_WITHOUT_INPUT_CODE", "message": f"{rec.get('input_name') or 'Recommendation'} has no input_code", "target": target})
            elif input_code not in known_input_codes:
                warnings.append({"level": "WARN", "code": "UNKNOWN_INPUT_CODE", "message": f"Input code {input_code} is not in input catalog", "target": target})
            if not rec.get("input_name"):
                warnings.append({"level": "ERROR", "code": "RECOMMENDATION_WITHOUT_INPUT_NAME", "message": "Recommendation has no input_name fallback", "target": target})
            if rec.get("typical_quantity") in (None, ""):
                warnings.append({"level": "INFO", "code": "RECOMMENDATION_WITHOUT_QUANTITY", "message": f"{rec.get('input_name') or 'Recommendation'} has no typical quantity", "target": target})
            if rec.get("day_offset") is None:
                warnings.append({"level": "WARN", "code": "RECOMMENDATION_WITHOUT_DAY_OFFSET", "message": f"{rec.get('input_name') or 'Recommendation'} has no day offset", "target": target})
    return warnings


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
    if not selected:
        raise HTTPException(404, "Workflow template version is not visible for this tenant/project")

    template, version, enablement = selected
    crop = db.query(Crop).filter(Crop.code == template.crop_code).first()
    stages = workflow_version_to_stage_definitions_for_scope(
        db,
        version.id,
        tenant_id=x_tenant_id,
        project_id=project_id,
    )
    overrides = scoped_overrides(db, template_version_id=version.id, tenant_id=x_tenant_id, project_id=project_id)
    known_input_codes = {row.code for row in db.query(AgriculturalInput.code).filter(AgriculturalInput.is_active == True).all()}
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


def _render_draft_preview(db: Session, workflow_template_version_id: uuid.UUID, tenant_id: str) -> dict:
    template, version = _get_draft_template_version(db, workflow_template_version_id, tenant_id)
    crop = db.query(Crop).filter(Crop.code == template.crop_code).first()
    stages = _draft_stage_definitions(db, version.id)
    known_input_codes = {row.code for row in db.query(AgriculturalInput.code).filter(AgriculturalInput.is_active == True).all()}
    warnings = _preview_warnings(stages, known_input_codes)
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
    )


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


@router.patch("/drafts/{workflow_template_version_id}/stages/{stage_code}")
def update_draft_workflow_stage(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftStageUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Edit a stage inside a DRAFT workflow version and return updated draft preview."""
    _, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
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


@router.post("/drafts/{workflow_template_version_id}/stages/{stage_code}/recommendations")
def create_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    stage_code: str,
    body: WorkflowDraftRecommendationCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Add a recommendation to a stage inside a DRAFT workflow version."""
    _, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    stage = _get_draft_stage(db, version.id, stage_code)
    activity_type = (body.activity_type or "").strip().upper()
    input_name = (body.input_name or "").strip()
    if not activity_type:
        raise HTTPException(400, "activity_type cannot be empty")
    if not input_name:
        raise HTTPException(400, "input_name cannot be empty")
    if body.sort_order is not None and body.sort_order < 0:
        raise HTTPException(400, "sort_order cannot be negative")

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
    db.add(WorkflowTemplateRecommendation(
        id=uuid.uuid4(),
        template_stage_id=stage.id,
        sort_order=sort_order,
        day_offset=int(body.day_offset or 0),
        activity_type=activity_type,
        input_code=body.input_code or None,
        input_name=input_name,
        typical_quantity=body.typical_quantity or None,
        typical_cost_per_acre=body.typical_cost_per_acre,
        is_critical=bool(body.is_critical),
        description=body.description or None,
        metadata_={"source": "draft_admin"},
        created_at=now,
        updated_at=now,
    ))
    version.updated_at = now
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.patch("/drafts/{workflow_template_version_id}/recommendations/{recommendation_id}")
def update_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    body: WorkflowDraftRecommendationUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Edit a recommendation inside a DRAFT workflow version."""
    _, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    rec = _get_draft_recommendation(db, version.id, recommendation_id)
    changes = body.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No recommendation changes supplied")
    _apply_recommendation_changes(rec, changes)
    now = datetime.now(timezone.utc)
    rec.updated_at = now
    version.updated_at = now
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


@router.delete("/drafts/{workflow_template_version_id}/recommendations/{recommendation_id}")
def delete_draft_workflow_recommendation(
    workflow_template_version_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Soft-delete a recommendation from a DRAFT workflow version."""
    _, version = _get_draft_template_version(db, workflow_template_version_id, x_tenant_id)
    rec = _get_draft_recommendation(db, version.id, recommendation_id)
    now = datetime.now(timezone.utc)
    rec.is_active = False
    rec.updated_at = now
    version.updated_at = now
    db.commit()
    return _render_draft_preview(db, workflow_template_version_id, x_tenant_id)


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


@router.post("/templates/{template_id}/versions/{version_id}/clone-draft")
def clone_workflow_template_version_to_draft(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    body: WorkflowDraftCloneRequest = WorkflowDraftCloneRequest(),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Clone a published workflow version into an editable draft version."""
    row = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplate.id == template_id,
            WorkflowTemplateVersion.id == version_id,
            WorkflowTemplateVersion.template_id == template_id,
            WorkflowTemplate.is_active == True,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplate.tenant_id.in_([x_tenant_id, "default"]),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Published workflow template version not found")

    template, source_version = row
    now = datetime.now(timezone.utc)
    draft_version_id = uuid.uuid4()
    draft_version_number = _next_draft_version_number(db, template.id, source_version.version_number, body.version_number)
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
):
    """Create/update a project-level workflow enablement row.

    This is the first safe admin write: it controls project visibility only and
    does not edit workflow template content.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

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
):
    """Create a project-level workflow override and return updated preview.

    This customizes project rendering without mutating the base workflow template.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

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
    _validate_override_payload(target_type, operation, body.override_payload or {})

    override = WorkflowTemplateOverride(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=project_id,
        template_version_id=body.template_version_id,
        target_type=target_type,
        target_code=body.target_code,
        operation=operation,
        override_payload=body.override_payload or {},
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

    version_id = override.template_version_id
    override.is_active = False
    override.updated_at = datetime.now(timezone.utc)
    db.commit()
    return preview_workflow_template_version(version_id, project_id, db, x_tenant_id)
