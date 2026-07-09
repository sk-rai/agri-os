"""Project-aware agricultural input assignment helpers."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, ProjectInputAssignment


def project_crop_scope(db: Session, *, project_id: Optional[uuid.UUID], tenant_id: str) -> set[str] | None:
    if not project_id:
        return None
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id, Project.is_active == True).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return {str(code).upper() for code in (project.crop_scope or [])} or None


def input_matches_crop_scope(item: AgriculturalInput, crop_scope: set[str] | None, crop_code: Optional[str] = None) -> bool:
    applicable = {str(code).upper() for code in (item.applicable_crops or [])}
    if crop_code:
        crop = crop_code.upper()
        if crop_scope is not None and crop not in crop_scope:
            return False
        return not applicable or crop in applicable
    if not crop_scope:
        return True
    return not applicable or bool(applicable & crop_scope)


def project_input_assignments(db: Session, *, tenant_id: str, project_id: Optional[uuid.UUID]) -> list[ProjectInputAssignment]:
    if not project_id:
        return []
    return db.query(ProjectInputAssignment).filter(
        ProjectInputAssignment.tenant_id == tenant_id,
        ProjectInputAssignment.project_id == project_id,
        ProjectInputAssignment.is_active == True,
    ).all()


def assignment_map(assignments: list[ProjectInputAssignment]) -> dict[str, ProjectInputAssignment]:
    return {row.input_code.upper(): row for row in assignments}


def explicit_allowlist_mode(assignments: list[ProjectInputAssignment]) -> bool:
    return any(row.enabled for row in assignments)


def input_assignment_decision(
    item: AgriculturalInput,
    *,
    project_crop_scope: set[str] | None,
    assignments_by_code: dict[str, ProjectInputAssignment],
    explicit_allowlist: bool,
    crop_code: Optional[str] = None,
) -> dict:
    crop_scope_allowed = input_matches_crop_scope(item, project_crop_scope, crop_code)
    assignment = assignments_by_code.get(item.code.upper())
    if not crop_scope_allowed:
        return {
            "visible": False,
            "assignment_rule": "BLOCKED_BY_CROP_SCOPE",
            "assignment_reason": "Input is not applicable to the project/crop scope.",
            "crop_scope_allowed": False,
            "assignment_scope": "project" if assignment else "implicit_crop_scope",
            "configured_enabled": bool(assignment.enabled) if assignment else None,
            "display_order": assignment.display_order if assignment else None,
            "reason": assignment.reason if assignment else None,
        }
    if assignment:
        if assignment.enabled:
            return {
                "visible": True,
                "assignment_rule": "ANDROID_VISIBLE",
                "assignment_reason": "Input is explicitly enabled for this project.",
                "crop_scope_allowed": True,
                "assignment_scope": "project",
                "configured_enabled": True,
                "display_order": assignment.display_order,
                "reason": assignment.reason,
            }
        return {
            "visible": False,
            "assignment_rule": "DISABLED_BY_PROJECT",
            "assignment_reason": "Input is explicitly disabled for this project.",
            "crop_scope_allowed": True,
            "assignment_scope": "project",
            "configured_enabled": False,
            "display_order": assignment.display_order,
            "reason": assignment.reason,
        }
    if explicit_allowlist:
        return {
            "visible": False,
            "assignment_rule": "NOT_ASSIGNED",
            "assignment_reason": "Project has explicit input assignments and this input is not assigned.",
            "crop_scope_allowed": True,
            "assignment_scope": "none",
            "configured_enabled": None,
            "display_order": None,
            "reason": None,
        }
    return {
        "visible": True,
        "assignment_rule": "IMPLICIT_CROP_SCOPE",
        "assignment_reason": "Input is visible through project crop-scope defaults.",
        "crop_scope_allowed": True,
        "assignment_scope": "implicit_crop_scope",
        "configured_enabled": None,
        "display_order": None,
        "reason": None,
    }


def allowed_input_codes_for_project_crop(
    db: Session,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    crop_code: str,
) -> set[str]:
    crop_scope = project_crop_scope(db, project_id=project_id, tenant_id=tenant_id)
    assignments = project_input_assignments(db, tenant_id=tenant_id, project_id=project_id)
    by_code = assignment_map(assignments)
    allowlist = explicit_allowlist_mode(assignments)
    rows = db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True).all()
    return {
        item.code
        for item in rows
        if input_assignment_decision(
            item,
            project_crop_scope=crop_scope,
            assignments_by_code=by_code,
            explicit_allowlist=allowlist,
            crop_code=crop_code,
        )["visible"]
    }


def assert_catalog_input_allowed_for_project_crop(
    db: Session,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    crop_code: str,
    input_code: Optional[str],
) -> None:
    if not input_code:
        return
    item = db.query(AgriculturalInput).filter(
        AgriculturalInput.code == input_code.upper(),
        AgriculturalInput.is_active == True,
    ).first()
    if not item:
        return
    crop_scope = project_crop_scope(db, project_id=project_id, tenant_id=tenant_id)
    assignments = project_input_assignments(db, tenant_id=tenant_id, project_id=project_id)
    decision = input_assignment_decision(
        item,
        project_crop_scope=crop_scope,
        assignments_by_code=assignment_map(assignments),
        explicit_allowlist=explicit_allowlist_mode(assignments),
        crop_code=crop_code,
    )
    if not decision["visible"]:
        raise HTTPException(
            409,
            {
                "error": "INPUT_NOT_ALLOWED_FOR_PROJECT_CROP",
                "assignment_rule": decision["assignment_rule"],
                "message": decision["assignment_reason"],
                "input_code": input_code.upper(),
                "crop_code": crop_code,
                "project_id": str(project_id) if project_id else None,
                "project_crop_scope": sorted(crop_scope) if crop_scope is not None else None,
            },
        )