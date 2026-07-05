"""Read-only workflow catalog APIs.

These endpoints tell Android/admin clients which published crop workflows are
visible for a tenant/project. Admin write APIs can build on the same tables later.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.master_data.models import Crop
from app.modules.workflow.template_service import (
    list_enabled_workflow_versions,
    workflow_template_metadata,
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
