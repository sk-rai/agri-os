"""Helpers for reading versioned crop workflow templates.

The Android contract still expects the legacy lifecycle-template response shape.
These helpers convert normalized workflow-template rows back into that shape.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateStage,
    WorkflowTemplateRecommendation,
    WorkflowTemplateEnablement,
    WorkflowTemplateOverride,
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



def _same_project(left, right) -> bool:
    return str(left) == str(right) if left and right else left is None and right is None


def _recommendation_target_codes(stage_code: str, rec: dict) -> set[str]:
    input_name = (rec.get("input_name") or "").strip()
    activity_type = (rec.get("activity_type") or "").strip().upper()
    codes = {input_name, input_name.lower(), f"{stage_code}|{input_name}", f"{stage_code}|{activity_type}|{input_name}"}
    input_code = rec.get("input_code")
    if input_code:
        codes.add(str(input_code))
        codes.add(f"{stage_code}|{input_code}")
    return {code for code in codes if code}


def scoped_overrides(
    db: Session,
    *,
    template_version_id,
    tenant_id: str = "default",
    project_id=None,
) -> list[WorkflowTemplateOverride]:
    """Return tenant/project overrides, project rows taking precedence by priority."""
    query = db.query(WorkflowTemplateOverride).filter(
        WorkflowTemplateOverride.template_version_id == template_version_id,
        WorkflowTemplateOverride.is_active == True,
        WorkflowTemplateOverride.tenant_id.in_([tenant_id, "default"]),
    )
    if project_id:
        query = query.filter(or_(WorkflowTemplateOverride.project_id == project_id, WorkflowTemplateOverride.project_id.is_(None)))
    else:
        query = query.filter(WorkflowTemplateOverride.project_id.is_(None))
    return query.order_by(
        (WorkflowTemplateOverride.tenant_id == tenant_id).desc(),
        WorkflowTemplateOverride.project_id.isnot(None).desc(),
        WorkflowTemplateOverride.priority,
        WorkflowTemplateOverride.created_at,
    ).all()


def apply_workflow_overrides(stages: list[dict], overrides: list[WorkflowTemplateOverride]) -> list[dict]:
    """Apply renderer-safe template overrides to legacy stage dictionaries."""
    result = deepcopy(stages)
    for override in overrides:
        payload = override.override_payload or {}
        operation = (override.operation or "").upper()
        target_type = (override.target_type or "").upper()
        target_code = override.target_code

        if target_type == "STAGE":
            for stage in result:
                if stage.get("code") != target_code:
                    continue
                if operation == "HIDE":
                    stage["_hidden"] = True
                elif operation == "RENAME":
                    stage["name"] = payload.get("name") or payload.get("label") or stage.get("name")
                elif operation == "CHANGE_DURATION":
                    stage["duration_days"] = int(payload.get("duration_days", stage.get("duration_days") or 0))

        if target_type == "RECOMMENDATION":
            for stage in result:
                stage_code = stage.get("code") or ""
                updated_recs = []
                for rec in stage.get("recommended_activities", []) or []:
                    codes = _recommendation_target_codes(stage_code, rec)
                    if target_code not in codes:
                        updated_recs.append(rec)
                        continue
                    rec_copy = dict(rec)
                    if operation == "HIDE":
                        continue
                    if operation == "RENAME":
                        rec_copy["input_name"] = payload.get("input_name") or payload.get("name") or rec_copy.get("input_name")
                    elif operation == "CHANGE_OFFSET":
                        rec_copy["day_offset"] = int(payload.get("day_offset", rec_copy.get("day_offset") or 0))
                    elif operation == "CHANGE_QUANTITY":
                        rec_copy["typical_quantity"] = payload.get("typical_quantity", rec_copy.get("typical_quantity"))
                    updated_recs.append(rec_copy)
                stage["recommended_activities"] = updated_recs

    return [stage for stage in result if not stage.get("_hidden")]


def workflow_version_to_stage_definitions_for_scope(
    db: Session,
    version_id,
    *,
    tenant_id: str = "default",
    project_id=None,
) -> list[dict]:
    stages = workflow_version_to_stage_definitions(db, version_id)
    overrides = scoped_overrides(db, template_version_id=version_id, tenant_id=tenant_id, project_id=project_id)
    if overrides:
        stages = apply_workflow_overrides(stages, overrides)
    return stages


def list_enabled_workflow_versions(
    db: Session,
    *,
    tenant_id: str = "default",
    project_id=None,
    crop_code: Optional[str] = None,
    season_code: Optional[str] = None,
) -> list[tuple[WorkflowTemplate, WorkflowTemplateVersion, Optional[WorkflowTemplateEnablement]]]:
    """List published workflow versions visible to a tenant/project.

    No enablement rows => implicit default catalog. Any rows at the requested
    scope => explicit allow-list where enabled=false rows are hidden.
    """
    base_enablement_query = db.query(WorkflowTemplateEnablement).filter(
        WorkflowTemplateEnablement.tenant_id == tenant_id,
        WorkflowTemplateEnablement.is_active == True,
    )
    project_enablements = []
    if project_id:
        project_enablements = base_enablement_query.filter(WorkflowTemplateEnablement.project_id == project_id).all()
    tenant_enablements = base_enablement_query.filter(WorkflowTemplateEnablement.project_id.is_(None)).all()
    # Project scope wins; tenant-level rows are the next explicit scope; no rows means implicit defaults.
    enablements = project_enablements or tenant_enablements
    enablement_by_template = {e.template_id: e for e in enablements}

    query = db.query(WorkflowTemplate, WorkflowTemplateVersion).join(
        WorkflowTemplateVersion,
        WorkflowTemplateVersion.template_id == WorkflowTemplate.id,
    ).filter(
        WorkflowTemplate.is_active == True,
        WorkflowTemplateVersion.is_active == True,
        WorkflowTemplateVersion.status == "PUBLISHED",
        WorkflowTemplate.tenant_id.in_([tenant_id, "default"]),
    )
    if crop_code:
        query = query.filter(WorkflowTemplate.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(WorkflowTemplate.season_code == season_code.upper())

    rows = query.order_by(
        WorkflowTemplate.crop_code,
        WorkflowTemplate.season_code,
        WorkflowTemplate.is_default.desc(),
        WorkflowTemplateVersion.published_at.desc().nullslast(),
    ).all()

    visible = []
    explicit_scope = bool(enablements)
    for template, version in rows:
        enablement = enablement_by_template.get(template.id)
        if explicit_scope:
            if not enablement or not enablement.enabled:
                continue
        elif not template.is_default:
            continue
        visible.append((template, version, enablement))

    return sorted(
        visible,
        key=lambda row: (
            row[2].display_order if row[2] else 1000,
            row[0].crop_code,
            row[0].season_code,
            row[0].canonical_name,
        ),
    )
