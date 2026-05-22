"""Crop master data API endpoints.

GET /api/v1/master-data/crops/categories
GET /api/v1/master-data/crops?category_id=
GET /api/v1/master-data/crops/{crop_id}/varieties
GET /api/v1/master-data/crops/{crop_id}/lifecycle-templates
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.master_data.models import (
    CropCategory,
    Crop,
    CropVariety,
    CropLifecycleTemplate,
)

router = APIRouter(prefix="/crops", tags=["crops"])


# --- Response Schemas ---

class CropCategoryResponse(BaseModel):
    id: UUID
    code: str
    canonical_name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class CropResponse(BaseModel):
    id: UUID
    code: str
    category_id: UUID
    canonical_name: str
    scientific_name: Optional[str] = None
    typical_duration_days: Optional[int] = None
    suitable_seasons: Optional[list[str]] = None

    class Config:
        from_attributes = True


class CropVarietyResponse(BaseModel):
    id: UUID
    code: str
    crop_id: UUID
    canonical_name: str
    developer: Optional[str] = None
    duration_days: Optional[int] = None
    recommended_states: Optional[list[str]] = None

    class Config:
        from_attributes = True


class LifecycleTemplateResponse(BaseModel):
    id: UUID
    code: str
    crop_id: UUID
    season_code: str
    canonical_name: str
    total_duration_days: Optional[int] = None
    stages: list[dict]
    is_default: bool

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.get("/categories", response_model=list[CropCategoryResponse])
def list_crop_categories(db: Session = Depends(get_db)):
    """List all active crop categories."""
    return (
        db.query(CropCategory)
        .filter(CropCategory.is_active == True)
        .order_by(CropCategory.canonical_name)
        .all()
    )


@router.get("", response_model=list[CropResponse])
def list_crops(
    category_id: Optional[UUID] = Query(None, description="Filter by category"),
    season: Optional[str] = Query(None, description="Filter by season code (KHARIF/RABI/ZAID)"),
    db: Session = Depends(get_db),
):
    """List crops, optionally filtered by category or season."""
    query = db.query(Crop).filter(Crop.is_active == True)
    if category_id:
        query = query.filter(Crop.category_id == category_id)
    if season:
        query = query.filter(Crop.suitable_seasons.contains([season.upper()]))
    return query.order_by(Crop.canonical_name).all()


@router.get("/{crop_id}/varieties", response_model=list[CropVarietyResponse])
def list_varieties(
    crop_id: UUID,
    db: Session = Depends(get_db),
):
    """List varieties for a specific crop."""
    return (
        db.query(CropVariety)
        .filter(
            CropVariety.crop_id == crop_id,
            CropVariety.is_active == True,
        )
        .order_by(CropVariety.canonical_name)
        .all()
    )


@router.get("/{crop_id}/lifecycle-templates", response_model=list[LifecycleTemplateResponse])
def list_lifecycle_templates(
    crop_id: UUID,
    season_code: Optional[str] = Query(None, description="Filter by season"),
    db: Session = Depends(get_db),
):
    """List lifecycle templates for a crop.

    Templates define the configurable stage sequence for a crop+season.
    Never hardcoded — always loaded from this endpoint.
    """
    query = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.crop_id == crop_id,
            CropLifecycleTemplate.is_active == True,
        )
    )
    if season_code:
        query = query.filter(
            CropLifecycleTemplate.season_code == season_code.upper()
        )
    return query.order_by(CropLifecycleTemplate.is_default.desc()).all()
