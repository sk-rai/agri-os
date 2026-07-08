"""Read-only agricultural input catalog APIs."""

from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import AgriculturalInput, InputCategory

router = APIRouter(prefix="/api/v1/input-catalog", tags=["input-catalog"])


def category_payload(category: InputCategory) -> dict:
    return {
        "id": str(category.id),
        "code": category.code,
        "canonical_name": category.canonical_name,
        "description": category.description,
        "aliases": category.aliases or [],
    }


def _project_crop_scope(db: Session, project_id, tenant_id: str) -> set[str] | None:
    if not project_id:
        return None
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id, Project.is_active == True).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return {str(code).upper() for code in (project.crop_scope or [])} or None


def _input_matches_crop_scope(item: AgriculturalInput, crop_scope: set[str] | None) -> bool:
    if not crop_scope:
        return True
    applicable = {str(code).upper() for code in (item.applicable_crops or [])}
    return not applicable or bool(applicable & crop_scope)


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
    project_scope = _project_crop_scope(db, project_id, x_tenant_id)
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
    if project_scope is not None:
        inputs = [item for item in inputs if _input_matches_crop_scope(item, project_scope)]
    return {
        "schema_version": "1.0.0",
        "project_id": str(project_id) if project_id else None,
        "project_crop_scope": sorted(project_scope) if project_scope is not None else None,
        "filter_policy": "PROJECT_CROP_SCOPE" if project_scope is not None else "GLOBAL_CATALOG",
        "count": len(inputs),
        "inputs": [input_payload(item) for item in inputs],
    }


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
