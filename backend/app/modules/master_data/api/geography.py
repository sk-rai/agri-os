"""Geography cascade API endpoints.

GET /api/v1/master-data/geography/states
GET /api/v1/master-data/geography/districts?state_id=
GET /api/v1/master-data/geography/blocks?district_id=
GET /api/v1/master-data/geography/villages?block_id=  (block-scoped)
GET /api/v1/master-data/geography/villages?district_id=  (district-wide, for offline cache)
GET /api/v1/master-data/geography/villages/search?q=&district_id=  (fuzzy, optionally scoped)
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


class PinCodeVillageResponse(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    block_id: UUID
    block_name: str
    district_id: UUID
    district_name: str
    state_id: UUID
    state_name: str
    pin_codes: Optional[list[str]] = None

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
    block_id: Optional[UUID] = Query(None, description="Filter by block UUID"),
    district_id: Optional[UUID] = Query(None, description="Filter by district UUID (district-wide search)"),
    search: Optional[str] = Query(None, min_length=2, description="Filter by name (ILIKE)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """List villages for a given block or district.

    Supports two modes:
    - block_id: villages in a specific block (original behavior)
    - district_id: ALL villages in a district (for district-wide caching)

    Limit raised to 5000 to support full district download for offline cache.
    Azamgarh has ~14K villages — use pagination for large districts.
    """
    if not block_id and not district_id:
        raise HTTPException(400, "Either block_id or district_id is required")

    query = db.query(GeographyVillage).filter(GeographyVillage.is_active == True)

    if block_id:
        query = query.filter(GeographyVillage.block_id == block_id)
    elif district_id:
        query = query.filter(GeographyVillage.district_id == district_id)

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


@router.get("/villages/by-pin-code", response_model=list[PinCodeVillageResponse])
def villages_by_pin_code(
    pin_code: str = Query(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$", description="Indian 6-digit PIN code"),
    district_id: Optional[UUID] = Query(None, description="Optionally narrow candidates to a selected district"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return candidate villages associated with a PIN code.

    A PIN code can cover multiple villages, so Android should display these
    candidates and let the farmer/agent confirm the correct village. This is
    intended for parcel land-location capture, not as a substitute for optional
    GPS point/polygon capture.
    """
    query = (
        db.query(
            GeographyVillage,
            GeographyBlock.canonical_name.label("block_name"),
            GeographyDistrict.canonical_name.label("district_name"),
            GeographyState.id.label("state_id"),
            GeographyState.canonical_name.label("state_name"),
        )
        .join(GeographyBlock, GeographyBlock.id == GeographyVillage.block_id)
        .join(GeographyDistrict, GeographyDistrict.id == GeographyVillage.district_id)
        .join(GeographyState, GeographyState.id == GeographyDistrict.state_id)
        .filter(
            GeographyVillage.is_active == True,
            GeographyBlock.is_active == True,
            GeographyDistrict.is_active == True,
            GeographyState.is_active == True,
            GeographyVillage.pin_codes.any(pin_code),
        )
    )
    if district_id:
        query = query.filter(GeographyVillage.district_id == district_id)

    rows = (
        query
        .order_by(GeographyDistrict.canonical_name, GeographyBlock.canonical_name, GeographyVillage.canonical_name)
        .limit(limit)
        .all()
    )

    return [
        PinCodeVillageResponse(
            id=row.GeographyVillage.id,
            lgd_code=row.GeographyVillage.lgd_code,
            canonical_name=row.GeographyVillage.canonical_name,
            block_id=row.GeographyVillage.block_id,
            block_name=row.block_name,
            district_id=row.GeographyVillage.district_id,
            district_name=row.district_name,
            state_id=row.state_id,
            state_name=row.state_name,
            pin_codes=row.GeographyVillage.pin_codes,
        )
        for row in rows
    ]


@router.get("/villages/search", response_model=list[VillageSearchResult])
def search_villages(
    q: str = Query(..., min_length=2, description="Fuzzy search query"),
    district_id: Optional[UUID] = Query(None, description="Scope search to a district"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fuzzy search villages by name using pg_trgm.

    Returns results ranked by similarity score.
    Optionally scoped to a district for faster, more relevant results.
    Designed for mobile offline-cache miss scenarios.
    """
    if district_id:
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
                AND v.district_id = :district_id
                AND v.is_active = true
                ORDER BY sim DESC
                LIMIT :limit
            """),
            {"query": q, "limit": limit, "district_id": str(district_id)},
        ).fetchall()
    else:
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
