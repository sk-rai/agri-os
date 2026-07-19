"""SoilGrids provider adapter.

Backend-only adapter for ISRIC SoilGrids baseline soil properties. The REST
service is treated as best-effort/beta; production ingestion can later switch to
WCS/WebDAV/GEE while preserving the normalized snapshot contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

SOILGRIDS_PROVIDER = "SOILGRIDS"
SOILGRIDS_DATASET = "soilgrids.v2.0"
DEFAULT_SOILGRIDS_DEPTH_LAYER = "0-5cm"


@dataclass(frozen=True)
class SoilGridsCoordinate:
    latitude: float
    longitude: float
    source: str


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_parcel_soilgrids_coordinate(db: Session, parcel) -> SoilGridsCoordinate:
    """Resolve the best available coordinate for provider lookup.

    Priority:
    1. parcel centroid columns from pin-drop/GPS/satellite capture;
    2. PostGIS centroid of parcel polygon;
    3. location_scope explicit centroid fallback.
    """
    lat = _as_float(getattr(parcel, "centroid_lat", None))
    lng = _as_float(getattr(parcel, "centroid_lng", None))
    if lat is not None and lng is not None:
        return SoilGridsCoordinate(latitude=lat, longitude=lng, source="PARCEL_CENTROID")

    try:
        row = db.execute(
            text("""
                SELECT ST_Y(ST_Centroid(geometry)) AS lat, ST_X(ST_Centroid(geometry)) AS lng
                FROM parcels
                WHERE id=:id AND tenant_id=:tenant_id AND geometry IS NOT NULL
            """),
            {"id": str(parcel.id), "tenant_id": parcel.tenant_id},
        ).fetchone()
    except Exception:
        row = None
    if row and row.lat is not None and row.lng is not None:
        return SoilGridsCoordinate(latitude=float(row.lat), longitude=float(row.lng), source="PARCEL_GEOMETRY_CENTROID")

    scope = getattr(parcel, "location_scope", None) or {}
    for key in ("centroid", "fallback_centroid", "provider_centroid"):
        value = scope.get(key)
        if isinstance(value, dict):
            lat = _as_float(value.get("lat") or value.get("latitude"))
            lng = _as_float(value.get("lng") or value.get("lon") or value.get("longitude"))
            if lat is not None and lng is not None:
                return SoilGridsCoordinate(latitude=lat, longitude=lng, source=f"LOCATION_SCOPE_{key.upper()}")

    raise ValueError("Parcel needs centroid/GPS geometry/location_scope centroid before SoilGrids lookup")


def fetch_soilgrids_payload(latitude: float, longitude: float, *, depth_layer: str = DEFAULT_SOILGRIDS_DEPTH_LAYER) -> dict[str, Any]:
    """Fetch a SoilGrids REST payload. Best-effort: caller decides when to enable."""
    params = {
        "lat": latitude,
        "lon": longitude,
        "property": ["phh2o", "soc", "nitrogen", "clay", "silt", "sand", "bdod", "cec"],
        "depth": depth_layer,
        "value": ["Q0.5", "mean"],
    }
    with httpx.Client(timeout=settings.SOILGRIDS_TIMEOUT_SECONDS) as client:
        response = client.get(settings.SOILGRIDS_BASE_URL, params=params)
        response.raise_for_status()
        return response.json()


def _property_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    properties = payload.get("properties") if isinstance(payload, dict) else None
    if isinstance(properties, dict):
        layers = properties.get("layers")
        if isinstance(layers, list):
            return [row for row in layers if isinstance(row, dict)]
        if any(isinstance(value, dict) for value in properties.values()):
            return [{"name": key, "depths": value} for key, value in properties.items() if isinstance(value, dict)]
    layers = payload.get("layers") if isinstance(payload, dict) else None
    if isinstance(layers, list):
        return [row for row in layers if isinstance(row, dict)]
    return []


def _depth_values(block: dict[str, Any], depth_layer: str) -> dict[str, Any]:
    depths = block.get("depths")
    if isinstance(depths, list):
        for depth in depths:
            if not isinstance(depth, dict):
                continue
            label = str(depth.get("label") or depth.get("range") or depth.get("depth") or "")
            if label == depth_layer or label.replace(" ", "") == depth_layer:
                values = depth.get("values")
                return values if isinstance(values, dict) else depth
        if depths:
            values = depths[0].get("values") if isinstance(depths[0], dict) else None
            return values if isinstance(values, dict) else (depths[0] if isinstance(depths[0], dict) else {})
    if isinstance(depths, dict):
        values = depths.get(depth_layer) or depths.get(depth_layer.replace("cm", "")) or next(iter(depths.values()), {})
        return values if isinstance(values, dict) else {}
    direct = block.get(depth_layer)
    return direct if isinstance(direct, dict) else {}


def _median(values: dict[str, Any]) -> Optional[float]:
    for key in ("Q0.5", "mean", "median", "value"):
        if key in values:
            return _as_float(values.get(key))
    return None


def _scale_soilgrids_value(property_name: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if property_name == "phh2o":
        return round(value / 10, 2) if value > 14 else round(value, 2)
    if property_name in {"clay", "silt", "sand"}:
        return round(value / 10, 2) if value > 100 else round(value, 2)
    if property_name == "soc":
        return round(value / 10, 4) if value > 100 else round(value, 4)
    if property_name == "nitrogen":
        return round(value / 100, 4) if value > 10 else round(value, 4)
    return round(value, 4)


def normalize_soilgrids_payload(payload: dict[str, Any], *, latitude: float, longitude: float, depth_layer: str = DEFAULT_SOILGRIDS_DEPTH_LAYER, coordinate_source: str = "UNKNOWN") -> dict[str, Any]:
    """Normalize SoilGrids-like provider payload into SoilEnrichmentSnapshot fields."""
    raw_values: dict[str, Any] = {}
    normalized_values: dict[str, Any] = {}
    mapped: dict[str, Optional[float]] = {
        "ph": None,
        "organic_carbon": None,
        "nitrogen": None,
        "clay_percent": None,
        "silt_percent": None,
        "sand_percent": None,
        "bulk_density": None,
        "cec": None,
    }
    name_map = {
        "phh2o": "ph",
        "soc": "organic_carbon",
        "nitrogen": "nitrogen",
        "clay": "clay_percent",
        "silt": "silt_percent",
        "sand": "sand_percent",
        "bdod": "bulk_density",
        "cec": "cec",
    }

    for block in _property_blocks(payload):
        name = str(block.get("name") or block.get("property") or "").lower()
        if not name:
            continue
        values = _depth_values(block, depth_layer)
        raw = _median(values)
        raw_values[name] = {"depth_layer": depth_layer, "median": raw, "values": values}
        target = name_map.get(name)
        if target:
            mapped[target] = _scale_soilgrids_value(name, raw)

    if not raw_values and isinstance(payload.get("normalized_values"), dict):
        normalized_values.update(payload["normalized_values"])

    normalized_values.update({"soilgrids_raw_values": raw_values, "coordinate_source": coordinate_source})

    return {
        "provider": SOILGRIDS_PROVIDER,
        "provider_dataset": str(payload.get("provider_dataset") or payload.get("dataset") or SOILGRIDS_DATASET),
        "snapshot_type": "BASELINE",
        "status": "AVAILABLE",
        "latitude": latitude,
        "longitude": longitude,
        "depth_layer": depth_layer,
        "resolution_meters": int(payload.get("resolution_meters") or 250),
        "confidence": str(payload.get("confidence") or "MODELLED"),
        "observed_at": datetime.now(timezone.utc),
        "fetched_at": datetime.now(timezone.utc),
        "ph": mapped["ph"],
        "organic_carbon": mapped["organic_carbon"],
        "nitrogen": mapped["nitrogen"],
        "clay_percent": mapped["clay_percent"],
        "silt_percent": mapped["silt_percent"],
        "sand_percent": mapped["sand_percent"],
        "bulk_density": mapped["bulk_density"],
        "cec": mapped["cec"],
        "normalized_values": normalized_values,
        "raw_payload": payload,
        "metadata": {
            "provider_family": "OPEN_SOURCE_BASELINE",
            "adapter": "soilgrids_service.v1",
            "coordinate_source": coordinate_source,
            "beta_rest_api": True,
        },
    }
