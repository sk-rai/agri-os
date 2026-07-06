"""Read-only workflow catalog APIs.

These endpoints tell Android/admin clients which published crop workflows are
visible for a tenant/project. Admin write APIs can build on the same tables later.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, Crop
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateEnablement, WorkflowTemplateOverride, WorkflowTemplateVersion
from app.modules.workflow.template_service import (
    list_enabled_workflow_versions,
    workflow_template_metadata,
    scoped_overrides,
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

    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id) if project_id else None,
        "preview_source": "workflow_template",
        "workflow_template_id": str(template.id),
        "workflow_template_version_id": str(version.id),
        "workflow_template_code": template.code,
        "version": version.version_number,
        "status": version.status,
        "enablement_source": "explicit" if enablement else "implicit_default",
        "label": _label(template, enablement),
        "crop_code": template.crop_code,
        "crop_name": crop.canonical_name if crop else template.crop_code,
        "season_code": template.season_code,
        "propagation_type_code": template.propagation_type_code,
        "total_duration_days": sum(int(stage.get("duration_days") or 0) for stage in stages),
        "applied_overrides": [_override_payload(override) for override in overrides],
        "warnings": warnings,
        "android_preview": {
            "crop_code": template.crop_code,
            "crop_name": crop.canonical_name if crop else template.crop_code,
            "season_code": template.season_code,
            "total_duration_days": sum(int(stage.get("duration_days") or 0) for stage in stages),
            "propagation_method": template.propagation_type_code,
            "stages": stages,
        },
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
