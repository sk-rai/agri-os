"""Project-aware agricultural input assignment helpers."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, ProjectInputAssignment


def ensure_project_input_assignment_table(db: Session) -> None:
    """Create project input assignment table in migration-light MVP environments."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS project_input_assignments (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            project_id UUID NOT NULL REFERENCES projects(id),
            input_id UUID NOT NULL REFERENCES agricultural_inputs(id),
            input_code VARCHAR(50) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            display_order INTEGER NOT NULL DEFAULT 1000,
            reason TEXT,
            effective_from DATE,
            effective_to DATE,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            version VARCHAR(20) DEFAULT 'v1.0',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT uq_project_input_assignment UNIQUE (tenant_id, project_id, input_code)
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_project_input_assignment_project ON project_input_assignments(project_id, enabled)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_project_input_assignment_code ON project_input_assignments(input_code)"))
    db.commit()



def ensure_project_input_assignment_audit_table(db: Session) -> None:
    """Create project input assignment audit table in migration-light MVP environments."""
    ensure_project_input_assignment_table(db)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS project_input_assignment_audit_events (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            project_id UUID NOT NULL REFERENCES projects(id),
            input_code VARCHAR(50) NOT NULL,
            assignment_id UUID REFERENCES project_input_assignments(id),
            actor_id UUID,
            action VARCHAR(50) NOT NULL,
            before_payload JSONB,
            after_payload JSONB,
            reason TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            version VARCHAR(20) DEFAULT 'v1.0',
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_project_input_assignment_audit_project ON project_input_assignment_audit_events(project_id, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_project_input_assignment_audit_input ON project_input_assignment_audit_events(project_id, input_code)"))
    db.commit()

def ensure_agricultural_input_audit_table(db: Session) -> None:
    """Create master input audit table in migration-light MVP environments."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS agricultural_input_audit_events (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            input_id UUID NOT NULL REFERENCES agricultural_inputs(id),
            input_code VARCHAR(50) NOT NULL,
            actor_id UUID,
            action VARCHAR(50) NOT NULL,
            before_payload JSONB,
            after_payload JSONB,
            reason TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            version VARCHAR(20) DEFAULT 'v1.0',
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_agricultural_input_audit_input ON agricultural_input_audit_events(input_code, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_agricultural_input_audit_tenant ON agricultural_input_audit_events(tenant_id, created_at)"))
    db.commit()


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
    ensure_project_input_assignment_table(db)
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