"""Master data delta sync endpoint for mobile offline cache.

POST /api/v1/master-data/sync
  Request: { "versions": { "geography": "v1.0", "crops": "v1.0" } }
  Response: { "deltas": [...], "current_versions": {...} }

Mobile clients call this on:
- First launch (versions = {})
- Network restore (versions = last known)
- Background refresh (every 24h if online)

Per governance: offline workflows NEVER fail due to missing master data.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.master_data.models import (
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
    CropCategory,
    Crop,
    CropVariety,
    CropLifecycleTemplate,
    Season,
    SoilType,
    InputCategory,
    AgriculturalInput,
    Manufacturer,
)

router = APIRouter(prefix="/sync", tags=["master-data-sync"])


class SyncRequest(BaseModel):
    """Client sends current cached versions."""
    versions: dict[str, str] = {}  # e.g. {"geography": "v1.0", "crops": "v1.0"}


class SyncDelta(BaseModel):
    """A single change record."""
    entity_type: str
    action: str  # "create" | "update" | "deprecate"
    data: dict


class SyncResponse(BaseModel):
    """Server returns deltas + current versions."""
    current_versions: dict[str, str]
    deltas: list[SyncDelta]
    total_records: dict[str, int]
    sync_timestamp: str


# Current master data versions (bump when data changes)
CURRENT_VERSIONS = {
    "geography": "v1.0",
    "crops": "v1.0",
    "seasons": "v1.0",
    "inputs": "v1.0",
    "soil": "v1.0",
}


@router.post("", response_model=SyncResponse)
def sync_master_data(
    request: SyncRequest,
    db: Session = Depends(get_db),
):
    """Delta sync endpoint for mobile master data cache.

    If client version matches server version → no deltas returned.
    If client version is empty or outdated → full dataset returned.

    For MVP: always returns full dataset (true delta tracking comes later
    with version_history table). This is acceptable because master data
    is relatively small (~4MB compressed) and changes infrequently.
    """
    deltas = []
    client_versions = request.versions

    # Geography sync (only if version mismatch or first sync)
    if client_versions.get("geography") != CURRENT_VERSIONS["geography"]:
        # States
        states = db.query(GeographyState).filter(GeographyState.is_active == True).all()
        for s in states:
            deltas.append(SyncDelta(
                entity_type="geography_state",
                action="create",
                data={"id": str(s.id), "lgd_code": s.lgd_code, "canonical_name": s.canonical_name},
            ))

        # Districts
        districts = db.query(GeographyDistrict).filter(GeographyDistrict.is_active == True).all()
        for d in districts:
            deltas.append(SyncDelta(
                entity_type="geography_district",
                action="create",
                data={"id": str(d.id), "lgd_code": d.lgd_code, "state_id": str(d.state_id), "canonical_name": d.canonical_name},
            ))

        # Blocks
        blocks = db.query(GeographyBlock).filter(GeographyBlock.is_active == True).all()
        for b in blocks:
            deltas.append(SyncDelta(
                entity_type="geography_block",
                action="create",
                data={"id": str(b.id), "lgd_code": b.lgd_code, "district_id": str(b.district_id), "canonical_name": b.canonical_name},
            ))

        # Villages (large — sent as compact records)
        villages = db.query(
            GeographyVillage.id,
            GeographyVillage.lgd_code,
            GeographyVillage.block_id,
            GeographyVillage.canonical_name,
            GeographyVillage.pin_codes,
        ).filter(GeographyVillage.is_active == True).all()
        for v in villages:
            deltas.append(SyncDelta(
                entity_type="geography_village",
                action="create",
                data={
                    "id": str(v.id), "lgd_code": v.lgd_code,
                    "block_id": str(v.block_id), "canonical_name": v.canonical_name,
                    "pin_codes": v.pin_codes or [],
                },
            ))

    # Crops sync
    if client_versions.get("crops") != CURRENT_VERSIONS["crops"]:
        categories = db.query(CropCategory).filter(CropCategory.is_active == True).all()
        for c in categories:
            deltas.append(SyncDelta(
                entity_type="crop_category",
                action="create",
                data={"id": str(c.id), "code": c.code, "canonical_name": c.canonical_name},
            ))

        crops = db.query(Crop).filter(Crop.is_active == True).all()
        for c in crops:
            deltas.append(SyncDelta(
                entity_type="crop",
                action="create",
                data={
                    "id": str(c.id), "code": c.code, "category_id": str(c.category_id),
                    "canonical_name": c.canonical_name, "suitable_seasons": c.suitable_seasons or [],
                    "typical_duration_days": c.typical_duration_days,
                },
            ))

        varieties = db.query(CropVariety).filter(CropVariety.is_active == True).all()
        for v in varieties:
            deltas.append(SyncDelta(
                entity_type="crop_variety",
                action="create",
                data={
                    "id": str(v.id), "code": v.code, "crop_id": str(v.crop_id),
                    "canonical_name": v.canonical_name, "duration_days": v.duration_days,
                },
            ))

        templates = db.query(CropLifecycleTemplate).filter(CropLifecycleTemplate.is_active == True).all()
        for t in templates:
            deltas.append(SyncDelta(
                entity_type="crop_lifecycle_template",
                action="create",
                data={
                    "id": str(t.id), "code": t.code, "crop_id": str(t.crop_id),
                    "season_code": t.season_code, "canonical_name": t.canonical_name,
                    "total_duration_days": t.total_duration_days,
                    "stages": t.stages, "is_default": t.is_default,
                },
            ))

    # Seasons sync
    if client_versions.get("seasons") != CURRENT_VERSIONS["seasons"]:
        seasons = db.query(Season).filter(Season.is_active == True).all()
        for s in seasons:
            deltas.append(SyncDelta(
                entity_type="season",
                action="create",
                data={
                    "id": str(s.id), "code": s.code, "canonical_name": s.canonical_name,
                    "start_month": s.start_month, "end_month": s.end_month,
                },
            ))

    # Build response
    total_records = {
        "geography_states": db.query(GeographyState).count(),
        "geography_districts": db.query(GeographyDistrict).count(),
        "geography_blocks": db.query(GeographyBlock).count(),
        "geography_villages": db.query(GeographyVillage).count(),
        "crops": db.query(Crop).count(),
        "crop_varieties": db.query(CropVariety).count(),
        "lifecycle_templates": db.query(CropLifecycleTemplate).count(),
    }

    return SyncResponse(
        current_versions=CURRENT_VERSIONS,
        deltas=deltas,
        total_records=total_records,
        sync_timestamp=datetime.now(timezone.utc).isoformat(),
    )
