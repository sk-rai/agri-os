"""Helpers for reading versioned crop workflow templates.

The Android contract still expects the legacy lifecycle-template response shape.
These helpers convert normalized workflow-template rows back into that shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateStage,
    WorkflowTemplateRecommendation,
)


def _json_name(value) -> dict:
    if isinstance(value, dict):
        return value
    return {"en": str(value or ""), "hi": str(value or "")}


def _cost(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def find_published_workflow_template(
    db: Session,
    *,
    crop_code: str,
    season_code: Optional[str] = None,
    tenant_id: str = "default",
    lifecycle_template_id=None,
) -> Optional[tuple[WorkflowTemplate, WorkflowTemplateVersion]]:
    """Return the active published workflow version for a crop/season.

    Tenant-specific templates win over default templates. If a cycle references a
    legacy lifecycle_template_id, use it to find the bridged workflow template.
    """
    query = (
        db.query(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .filter(
            WorkflowTemplate.is_active == True,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplate.crop_code == crop_code.upper(),
            WorkflowTemplate.tenant_id.in_([tenant_id, "default"]),
        )
    )
    if season_code:
        query = query.filter(WorkflowTemplate.season_code == season_code.upper())
    if lifecycle_template_id:
        query = query.filter(WorkflowTemplate.lifecycle_template_id == lifecycle_template_id)

    return (
        query.order_by(
            (WorkflowTemplate.tenant_id == tenant_id).desc(),
            WorkflowTemplate.is_default.desc(),
            WorkflowTemplateVersion.published_at.desc().nullslast(),
            WorkflowTemplateVersion.created_at.desc(),
        )
        .first()
    )


def workflow_version_to_stage_definitions(
    db: Session,
    version_id,
) -> list[dict]:
    """Convert normalized stage/recommendation rows to legacy stage dicts."""
    stages = (
        db.query(WorkflowTemplateStage)
        .filter(
            WorkflowTemplateStage.template_version_id == version_id,
            WorkflowTemplateStage.is_active == True,
        )
        .order_by(WorkflowTemplateStage.stage_order)
        .all()
    )
    if not stages:
        return []

    recommendations = (
        db.query(WorkflowTemplateRecommendation)
        .filter(
            WorkflowTemplateRecommendation.template_stage_id.in_([s.id for s in stages]),
            WorkflowTemplateRecommendation.is_active == True,
        )
        .order_by(
            WorkflowTemplateRecommendation.template_stage_id,
            WorkflowTemplateRecommendation.sort_order,
            WorkflowTemplateRecommendation.day_offset,
        )
        .all()
    )
    recs_by_stage = {}
    for rec in recommendations:
        recs_by_stage.setdefault(rec.template_stage_id, []).append({
            "day_offset": rec.day_offset or 0,
            "activity_type": rec.activity_type,
            "input_code": rec.input_code,
            "input_name": rec.input_name,
            "typical_quantity": rec.typical_quantity,
            "typical_cost_per_acre": _cost(rec.typical_cost_per_acre),
            "is_critical": bool(rec.is_critical),
            "description": rec.description,
            "metadata": rec.metadata_ or {},
        })

    result = []
    for stage in stages:
        result.append({
            "code": stage.stage_code,
            "name": _json_name(stage.stage_name),
            "order": stage.stage_order,
            "duration_days": stage.duration_days or 0,
            "stage_type": stage.stage_type,
            "phase": stage.phase,
            "bbch_range": stage.bbch_range,
            "propagation_step": bool(stage.propagation_step),
            "description": stage.description,
            "farmer_actions": stage.farmer_actions or [],
            "typical_inputs": stage.typical_inputs or [],
            "key_observations": stage.key_observations or [],
            "recommended_activities": recs_by_stage.get(stage.id, []),
            "icon": stage.icon,
            "color": stage.color,
            "metadata": stage.metadata_ or {},
        })
    return result


def workflow_template_metadata(template: WorkflowTemplate, version: WorkflowTemplateVersion) -> dict:
    metadata = {}
    if template.metadata_:
        metadata.update(template.metadata_)
    if version.metadata_:
        metadata.update(version.metadata_)
    metadata.setdefault("source", "workflow_template")
    metadata.setdefault("workflow_template_id", str(template.id))
    metadata.setdefault("workflow_template_version_id", str(version.id))
    metadata.setdefault("workflow_template_version", version.version_number)
    metadata.setdefault("propagation_method", template.propagation_type_code)
    return metadata
