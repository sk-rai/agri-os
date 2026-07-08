"""Read-only agricultural input catalog APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, InputCategory, ProjectInputAssignment
from app.modules.master_data.input_assignment_service import (
    assignment_map,
    ensure_project_input_assignment_table,
    explicit_allowlist_mode,
    input_assignment_decision,
    project_crop_scope,
    project_input_assignments,
)

router = APIRouter(prefix="/api/v1/input-catalog", tags=["input-catalog"])


class ProjectInputAssignmentUpdate(BaseModel):
    enabled: bool
    display_order: Optional[int] = None
    reason: Optional[str] = None
    metadata: Optional[dict] = None


def category_payload(category: InputCategory) -> dict:
    return {
        "id": str(category.id),
        "code": category.code,
        "canonical_name": category.canonical_name,
        "description": category.description,
        "aliases": category.aliases or [],
    }


def input_payload(item: AgriculturalInput) -> dict:
    return {
        "id": str(item.id),
        "code": item.code,
        "category_code": item.category.code if item.category else None,
        "category_name": item.category.canonical_name if item.category else None,
        "canonical_name": item.canonical_name,
        "brand_name": item.brand_name,
        "composition": item.composition,
        "unit": item.unit,
        "standard_weight": str(item.standard_weight) if item.standard_weight is not None else None,
        "applicable_crops": item.applicable_crops or [],
        "application_method": item.application_method,
        "safety_instructions": item.safety_instructions,
        "aliases": item.aliases or [],
    }


@router.get("/categories")
def list_input_categories(db: Session = Depends(get_db)):
    categories = (
        db.query(InputCategory)
        .filter(InputCategory.is_active == True)
        .order_by(InputCategory.code)
        .all()
    )
    return {
        "schema_version": "1.0.0",
        "count": len(categories),
        "categories": [category_payload(category) for category in categories],
    }


@router.get("/inputs")
def list_inputs(
    category: Optional[str] = Query(None),
    crop_code: Optional[str] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    q: Optional[str] = Query(None, description="Case-insensitive search over code/name/composition"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = db.query(AgriculturalInput).join(InputCategory).filter(AgriculturalInput.is_active == True)
    if category:
        query = query.filter(InputCategory.code == category.upper())
    project_scope = project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    assignments = project_input_assignments(db, tenant_id=x_tenant_id, project_id=project_id)
    assignments_by_code = assignment_map(assignments)
    explicit_allowlist = explicit_allowlist_mode(assignments)
    if crop_code:
        crop = crop_code.upper()
        if project_scope is not None and crop not in project_scope:
            return {
                "schema_version": "1.0.0",
                "project_id": str(project_id) if project_id else None,
                "project_crop_scope": sorted(project_scope),
                "filter_policy": "PROJECT_CROP_SCOPE",
                "count": 0,
                "inputs": [],
            }
        # PostgreSQL ARRAY contains a single crop code.
        query = query.filter(AgriculturalInput.applicable_crops.contains([crop]))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AgriculturalInput.code.ilike(pattern)
            | AgriculturalInput.canonical_name.ilike(pattern)
            | AgriculturalInput.composition.ilike(pattern)
        )
    inputs = query.order_by(InputCategory.code, AgriculturalInput.canonical_name).all()
    if project_id:
        inputs = [
            item for item in inputs
            if input_assignment_decision(
                item,
                project_crop_scope=project_scope,
                assignments_by_code=assignments_by_code,
                explicit_allowlist=explicit_allowlist,
                crop_code=crop_code,
            )["visible"]
        ]
    return {
        "schema_version": "1.0.0",
        "project_id": str(project_id) if project_id else None,
        "project_crop_scope": sorted(project_scope) if project_scope is not None else None,
        "filter_policy": "PROJECT_ASSIGNMENT" if project_id else "GLOBAL_CATALOG",
        "explicit_assignment_scope": explicit_allowlist if project_id else False,
        "count": len(inputs),
        "inputs": [input_payload(item) for item in inputs],
    }


def _input_assignment_payload(item: AgriculturalInput, decision: dict) -> dict:
    payload = input_payload(item)
    payload.update({
        "visible": decision["visible"],
        "assignment_rule": decision["assignment_rule"],
        "assignment_reason": decision["assignment_reason"],
        "crop_scope_allowed": decision["crop_scope_allowed"],
        "assignment_scope": decision["assignment_scope"],
        "configured_enabled": decision["configured_enabled"],
        "display_order": decision["display_order"],
        "reason": decision["reason"],
    })
    return payload


@router.get("/projects/{project_id}/input-assignments")
def get_project_input_assignments(
    project_id: uuid.UUID,
    category: Optional[str] = Query(None),
    crop_code: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    ensure_project_input_assignment_table(db)
    project_scope = project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    assignments = project_input_assignments(db, tenant_id=x_tenant_id, project_id=project_id)
    assignments_by_code = assignment_map(assignments)
    explicit_allowlist = explicit_allowlist_mode(assignments)

    query = db.query(AgriculturalInput).join(InputCategory).filter(AgriculturalInput.is_active == True)
    if category:
        query = query.filter(InputCategory.code == category.upper())
    if crop_code:
        query = query.filter(AgriculturalInput.applicable_crops.contains([crop_code.upper()]))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AgriculturalInput.code.ilike(pattern)
            | AgriculturalInput.canonical_name.ilike(pattern)
            | AgriculturalInput.composition.ilike(pattern)
        )
    inputs = query.order_by(InputCategory.code, AgriculturalInput.canonical_name).all()
    rows = [
        _input_assignment_payload(
            item,
            input_assignment_decision(
                item,
                project_crop_scope=project_scope,
                assignments_by_code=assignments_by_code,
                explicit_allowlist=explicit_allowlist,
                crop_code=crop_code,
            ),
        )
        for item in inputs
    ]
    return {
        "schema_version": "1.0.0",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "project_crop_scope": sorted(project_scope) if project_scope is not None else None,
        "explicit_assignment_scope": explicit_allowlist,
        "counts": {
            "total": len(rows),
            "android_visible": sum(1 for row in rows if row["visible"]),
            "disabled_by_project": sum(1 for row in rows if row["assignment_rule"] == "DISABLED_BY_PROJECT"),
            "not_assigned": sum(1 for row in rows if row["assignment_rule"] == "NOT_ASSIGNED"),
            "blocked_by_crop_scope": sum(1 for row in rows if row["assignment_rule"] == "BLOCKED_BY_CROP_SCOPE"),
            "implicit_crop_scope": sum(1 for row in rows if row["assignment_rule"] == "IMPLICIT_CROP_SCOPE"),
        },
        "inputs": rows,
    }


@router.put("/projects/{project_id}/input-assignments/{input_code}")
def upsert_project_input_assignment(
    project_id: uuid.UUID,
    input_code: str,
    body: ProjectInputAssignmentUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    ensure_project_input_assignment_table(db)
    project_crop_scope(db, project_id=project_id, tenant_id=x_tenant_id)
    item = db.query(AgriculturalInput).filter(
        AgriculturalInput.code == input_code.upper(),
        AgriculturalInput.is_active == True,
    ).first()
    if not item:
        raise HTTPException(404, f"Input '{input_code}' not found")

    assignment = db.query(ProjectInputAssignment).filter(
        ProjectInputAssignment.tenant_id == x_tenant_id,
        ProjectInputAssignment.project_id == project_id,
        ProjectInputAssignment.input_code == item.code,
    ).first()
    if not assignment:
        assignment = ProjectInputAssignment(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            project_id=project_id,
            input_id=item.id,
            input_code=item.code,
            created_at=datetime.now(timezone.utc),
        )
        db.add(assignment)
    assignment.input_id = item.id
    assignment.enabled = body.enabled
    assignment.display_order = body.display_order if body.display_order is not None else (assignment.display_order or 1000)
    assignment.reason = body.reason
    if body.metadata is not None:
        assignment.metadata_ = body.metadata
    assignment.is_active = True
    assignment.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_project_input_assignments(project_id=project_id, category=None, crop_code=None, q=None, db=db, x_tenant_id=x_tenant_id)


@router.get("/inputs/{input_code}")
def get_input(input_code: str, db: Session = Depends(get_db)):
    item = (
        db.query(AgriculturalInput)
        .filter(AgriculturalInput.code == input_code.upper(), AgriculturalInput.is_active == True)
        .first()
    )
    if not item:
        from fastapi import HTTPException
        raise HTTPException(404, f"Input '{input_code}' not found")
    return input_payload(item)
