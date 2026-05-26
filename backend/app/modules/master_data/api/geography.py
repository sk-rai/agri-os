"""Geography cascade API endpoints.

GET /api/v1/master-data/geography/states
GET /api/v1/master-data/geography/districts?state_id=
GET /api/v1/master-data/geography/blocks?district_id=
GET /api/v1/master-data/geography/villages?block_id=&search=
GET /api/v1/master-data/geography/villages/search?q=&limit=

All endpoints support:
- Pagination (offset/limit)
- Tenant isolation (via middleware)
- Fuzzy search on village names (pg_trgm)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.master_data.models import (
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
)

router = APIRouter(prefix="/geography", tags=["geography"])


# --- Response Schemas ---

class StateResponse(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    census_name: Optional[str] = None

    class Config:
        from_attributes = True


class DistrictResponse(BaseModel):
    id: UUID
    lgd_code: str
    state_id: UUID
    canonical_name: str
    census_name: Optional[str] = None

    class Config:
        from_attributes = True


class BlockResponse(BaseModel):
    id: UUID
    lgd_code: str
    district_id: UUID
    canonical_name: str

    class Config:
        from_attributes = True


class VillageResponse(BaseModel):
    id: UUID
    lgd_code: str
    block_id: UUID
    district_id: UUID
    canonical_name: str
    census_name: Optional[str] = None
    pin_codes: Optional[list[str]] = None

    class Config:
        from_attributes = True


class VillageSearchResult(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    block_name: str
    district_name: str
    pin_codes: Optional[list[str]] = None
    similarity: float

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: list
    total: int
    offset: int
    limit: int


# --- Endpoints ---

@router.get("/states", response_model=list[StateResponse])
def list_states(
    db: Session = Depends(get_db),
):
    """List all active states."""
    return (
        db.query(GeographyState)
        .filter(GeographyState.is_active == True)
        .order_by(GeographyState.canonical_name)
        .all()
    )


@router.get("/districts", response_model=list[DistrictResponse])
def list_districts(
    state_id: UUID = Query(..., description="Filter by state UUID"),
    db: Session = Depends(get_db),
):
    """List districts for a given state."""
    return (
        db.query(GeographyDistrict)
        .filter(
            GeographyDistrict.state_id == state_id,
            GeographyDistrict.is_active == True,
        )
        .order_by(GeographyDistrict.canonical_name)
        .all()
    )


@router.get("/blocks", response_model=list[BlockResponse])
def list_blocks(
    district_id: UUID = Query(..., description="Filter by district UUID"),
    db: Session = Depends(get_db),
):
    """List blocks/sub-districts for a given district."""
    return (
        db.query(GeographyBlock)
        .filter(
            GeographyBlock.district_id == district_id,
            GeographyBlock.is_active == True,
        )
        .order_by(GeographyBlock.canonical_name)
        .all()
    )


@router.get("/villages", response_model=list[VillageResponse])
def list_villages(
    block_id: UUID = Query(..., description="Filter by block UUID"),
    search: Optional[str] = Query(None, min_length=2, description="Filter by name (ILIKE)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List villages for a given block, with optional name filter."""
    query = (
        db.query(GeographyVillage)
        .filter(
            GeographyVillage.block_id == block_id,
            GeographyVillage.is_active == True,
        )
    )
    if search:
        query = query.filter(
            GeographyVillage.canonical_name.ilike(f"%{search}%")
        )
    return (
        query
        .order_by(GeographyVillage.canonical_name)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/villages/search", response_model=list[VillageSearchResult])
def search_villages(
    q: str = Query(..., min_length=2, description="Fuzzy search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Fuzzy search villages by name using pg_trgm.

    Returns results ranked by similarity score.
    Designed for mobile offline-cache miss scenarios where
    the user types a partial/misspelled village name.
    """
    results = db.execute(
        text("""
            SELECT
                v.id,
                v.lgd_code,
                v.canonical_name,
                v.pin_codes,
                b.canonical_name as block_name,
                d.canonical_name as district_name,
                similarity(v.canonical_name, :query) as sim
            FROM geography_villages v
            JOIN geography_blocks b ON b.id = v.block_id
            JOIN geography_districts d ON d.id = v.district_id
            WHERE v.canonical_name % :query
            AND v.is_active = true
            ORDER BY sim DESC
            LIMIT :limit
        """),
        {"query": q, "limit": limit},
    ).fetchall()

    return [
        VillageSearchResult(
            id=r.id,
            lgd_code=r.lgd_code,
            canonical_name=r.canonical_name,
            block_name=r.block_name,
            district_name=r.district_name,
            pin_codes=r.pin_codes,
            similarity=round(r.sim, 3),
        )
        for r in results
    ]
