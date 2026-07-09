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

from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, CropStageInputRule
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



def _decimal_text(value):
    return str(value) if value is not None else None


def _input_rule_payload(rule: CropStageInputRule) -> dict:
    item = rule.input
    return {
        "id": str(rule.id),
        "rule_scope": "PROJECT" if rule.project_id else "GLOBAL",
        "project_id": str(rule.project_id) if rule.project_id else None,
        "crop_code": rule.crop_code,
        "season_code": rule.season_code,
        "stage_code": rule.stage_code,
        "activity_type": rule.activity_type,
        "input_code": rule.input_code,
        "input_name": item.canonical_name if item else rule.input_code,
        "input_category_code": item.category.code if item and item.category else None,
        "enabled": bool(rule.enabled),
        "priority": rule.priority,
        "dosage": {
            "quantity": _decimal_text(rule.dosage_quantity),
            "unit": rule.dosage_unit,
            "area_unit": rule.dosage_area_unit,
            "min_quantity": _decimal_text(rule.min_quantity),
            "max_quantity": _decimal_text(rule.max_quantity),
        },
        "application_method": rule.application_method,
        "timing_note": rule.timing_note,
        "safety_note": rule.safety_note,
        "allowed_product_codes": rule.allowed_product_codes or [],
        "metadata": rule.metadata_ or {},
    }


def _best_input_rule_map(
    db: Session,
    stages: list[dict],
    *,
    crop_code: str,
    season_code: Optional[str] = None,
    tenant_id: str = "default",
    project_id=None,
) -> dict[tuple[str, str, str], CropStageInputRule]:
    stage_codes = {str(stage.get("code") or "").upper() for stage in stages if stage.get("code")}
    recs = [rec for stage in stages for rec in (stage.get("recommended_activities", []) or [])]
    input_codes = {str(rec.get("input_code") or "").upper() for rec in recs if rec.get("input_code")}
    activity_types = {str(rec.get("activity_type") or "").upper() for rec in recs if rec.get("activity_type")}
    if not stage_codes or not input_codes or not activity_types:
        return {}

    query = db.query(CropStageInputRule).join(AgriculturalInput).filter(
        CropStageInputRule.tenant_id == tenant_id,
        CropStageInputRule.is_active == True,
        CropStageInputRule.enabled == True,
        CropStageInputRule.crop_code == crop_code.upper(),
        CropStageInputRule.stage_code.in_(stage_codes),
        CropStageInputRule.activity_type.in_(activity_types),
        CropStageInputRule.input_code.in_(input_codes),
        AgriculturalInput.is_active == True,
        AgriculturalInput.catalog_status == "PUBLISHED",
    )
    if project_id:
        query = query.filter(or_(CropStageInputRule.project_id == project_id, CropStageInputRule.project_id.is_(None)))
    else:
        query = query.filter(CropStageInputRule.project_id.is_(None))
    if season_code:
        query = query.filter(or_(CropStageInputRule.season_code == season_code.upper(), CropStageInputRule.season_code.is_(None)))
    else:
        query = query.filter(CropStageInputRule.season_code.is_(None))

    def rank(rule: CropStageInputRule):
        project_rank = 0 if project_id and rule.project_id and str(rule.project_id) == str(project_id) else 1
        season_rank = 0 if season_code and rule.season_code == season_code.upper() else 1
        return (project_rank, season_rank, rule.priority or 1000, str(rule.updated_at or ""))

    best: dict[tuple[str, str, str], CropStageInputRule] = {}
    for rule in sorted(query.all(), key=rank):
        key = (rule.stage_code, rule.activity_type, rule.input_code)
        best.setdefault(key, rule)
    return best


def enrich_stage_definitions_with_input_rules(
    db: Session,
    stages: list[dict],
    *,
    crop_code: Optional[str],
    season_code: Optional[str] = None,
    tenant_id: str = "default",
    project_id=None,
) -> list[dict]:
    """Attach optional dosage/compatibility guidance to recommendations.

    Existing Android fields are preserved. New clients can read input_rule and
    recommended_dosage; older clients safely ignore the extra keys.
    """
    if not crop_code or not stages:
        return stages
    result = deepcopy(stages)
    rules = _best_input_rule_map(db, result, crop_code=crop_code, season_code=season_code, tenant_id=tenant_id, project_id=project_id)
    if not rules:
        return result
    for stage in result:
        stage_code = str(stage.get("code") or "").upper()
        enriched_recs = []
        for rec in stage.get("recommended_activities", []) or []:
            rec_copy = dict(rec)
            input_code = str(rec_copy.get("input_code") or "").upper()
            activity_type = str(rec_copy.get("activity_type") or "").upper()
            rule = rules.get((stage_code, activity_type, input_code))
            if rule:
                payload = _input_rule_payload(rule)
                rec_copy["input_rule"] = payload
                rec_copy["recommended_dosage"] = payload["dosage"]
                rec_copy["allowed_product_codes"] = payload["allowed_product_codes"]
                rec_copy["rule_application_method"] = payload["application_method"]
                rec_copy["rule_timing_note"] = payload["timing_note"]
                rec_copy["rule_safety_note"] = payload["safety_note"]
                metadata = dict(rec_copy.get("metadata") or {})
                metadata["input_rule_id"] = payload["id"]
                metadata["input_rule_scope"] = payload["rule_scope"]
                rec_copy["metadata"] = metadata
            enriched_recs.append(rec_copy)
        stage["recommended_activities"] = enriched_recs
    return result

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
                elif operation == "ADD_RECOMMENDATION":
                    new_rec = {
                        "day_offset": int(payload.get("day_offset", 0)),
                        "activity_type": str(payload.get("activity_type") or "OTHER").upper(),
                        "input_code": payload.get("input_code"),
                        "input_name": payload.get("input_name"),
                        "typical_quantity": payload.get("typical_quantity"),
                        "typical_cost_per_acre": _cost(payload.get("typical_cost_per_acre")),
                        "is_critical": bool(payload.get("is_critical", False)),
                        "description": payload.get("description") or {},
                        "metadata": {
                            **(payload.get("metadata") or {}),
                            "source": "project_override",
                            "override_id": str(override.id),
                        },
                    }
                    stage.setdefault("recommended_activities", []).append(new_rec)
                    stage["recommended_activities"] = sorted(
                        stage.get("recommended_activities", []),
                        key=lambda rec: (int(rec.get("day_offset") or 0), str(rec.get("input_name") or "")),
                    )

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
    crop_code: Optional[str] = None,
    season_code: Optional[str] = None,
) -> list[dict]:
    stages = workflow_version_to_stage_definitions(db, version_id)
    overrides = scoped_overrides(db, template_version_id=version_id, tenant_id=tenant_id, project_id=project_id)
    if overrides:
        stages = apply_workflow_overrides(stages, overrides)
    return enrich_stage_definitions_with_input_rules(
        db,
        stages,
        crop_code=crop_code,
        season_code=season_code,
        tenant_id=tenant_id,
        project_id=project_id,
    )


def _is_newer_workflow_catalog_row(
    candidate: tuple[WorkflowTemplate, WorkflowTemplateVersion, Optional[WorkflowTemplateEnablement]],
    existing: tuple[WorkflowTemplate, WorkflowTemplateVersion, Optional[WorkflowTemplateEnablement]],
) -> bool:
    """Pick the Android-visible version when a crop/season slot has multiple candidates."""
    candidate_template, candidate_version, _ = candidate
    existing_template, existing_version, _ = existing
    candidate_key = (
        str(candidate_version.published_at or ""),
        str(candidate_version.created_at or ""),
        bool(candidate_template.is_default),
        str(candidate_version.id),
    )
    existing_key = (
        str(existing_version.published_at or ""),
        str(existing_version.created_at or ""),
        bool(existing_template.is_default),
        str(existing_version.id),
    )
    return candidate_key > existing_key


def list_enabled_workflow_versions(
    db: Session,
    *,
    tenant_id: str = "default",
    project_id=None,
    crop_code: Optional[str] = None,
    season_code: Optional[str] = None,
) -> list[tuple[WorkflowTemplate, WorkflowTemplateVersion, Optional[WorkflowTemplateEnablement]]]:
    """List the single Android-visible published workflow per crop/season for a tenant/project.

    No enablement rows => implicit default catalog. Any rows at the requested
    scope => explicit allow-list where enabled=false rows are hidden.

    If multiple published workflow versions/templates claim the same crop/season
    catalog slot, Android should receive only the newest published candidate.
    Older published or archived versions remain accessible through admin history
    and explicit preview-by-version APIs.
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
    project_crop_scope = None
    if project_id:
        project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
        if project and project.crop_scope:
            project_crop_scope = {str(code).upper() for code in project.crop_scope}

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
        WorkflowTemplate.id,
        WorkflowTemplateVersion.published_at.desc().nullslast(),
        WorkflowTemplateVersion.created_at.desc(),
    ).all()

    visible_candidates = []
    seen_template_ids = set()
    explicit_scope = bool(enablements)
    for template, version in rows:
        if template.id in seen_template_ids:
            continue
        enablement = enablement_by_template.get(template.id)
        if explicit_scope:
            if not enablement or not enablement.enabled:
                continue
        elif not template.is_default:
            continue
        if project_crop_scope is not None and template.crop_code.upper() not in project_crop_scope:
            continue
        visible_candidates.append((template, version, enablement))
        seen_template_ids.add(template.id)

    visible_by_catalog_key = {}
    for row in visible_candidates:
        template, _, _ = row
        catalog_key = (template.crop_code, template.season_code)
        existing = visible_by_catalog_key.get(catalog_key)
        if not existing or _is_newer_workflow_catalog_row(row, existing):
            visible_by_catalog_key[catalog_key] = row

    visible = list(visible_by_catalog_key.values())
    return sorted(
        visible,
        key=lambda row: (
            row[2].display_order if row[2] else 1000,
            row[0].crop_code,
            row[0].season_code,
            row[0].canonical_name,
        ),
    )
