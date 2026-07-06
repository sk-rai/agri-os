"""Read-only workflow catalog APIs.

These endpoints tell Android/admin clients which published crop workflows are
visible for a tenant/project. Admin write APIs can build on the same tables later.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.master_data.models import AgriculturalInput, Crop
from app.modules.workflow.template_service import (
    list_enabled_workflow_versions,
    workflow_template_metadata,
    scoped_overrides,
    workflow_version_to_stage_definitions_for_scope,
)

router = APIRouter(prefix="/api/v1/workflow-catalog", tags=["workflow-catalog"])


def _label(template, enablement):
    if enablement and enablement.display_label:
        return enablement.display_label
    return {"en": template.canonical_name, "hi": template.canonical_name}


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
        "applied_overrides": [
            {
                "id": str(override.id),
                "target_type": override.target_type,
                "target_code": override.target_code,
                "operation": override.operation,
                "priority": override.priority,
                "payload": override.override_payload or {},
                "reason": override.reason,
            }
            for override in overrides
        ],
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
