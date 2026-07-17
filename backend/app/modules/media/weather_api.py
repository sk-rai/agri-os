"""Backend-owned weather provider config and snapshot APIs."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.media.api import _iso
from app.modules.media.models import WeatherProviderConfig, WeatherSnapshot

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])

PROVIDER_TYPES = {"EXTERNAL_API", "MANUAL", "INTERNAL_MODEL", "SATELLITE", "IOT_STATION"}
LOCATION_SCOPES = {"TENANT", "PROJECT", "FARMER", "PARCEL", "GEOPOINT", "PINCODE", "VILLAGE", "DISTRICT", "STATE", "WEATHER_GRID"}


def _parse_dt(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _now():
    return datetime.now(timezone.utc)


class WeatherProviderCreate(BaseModel):
    id: uuid.UUID | None = None
    provider_code: str = Field(..., min_length=1, max_length=80)
    display_name: str = Field(..., min_length=1, max_length=160)
    provider_type: str = "EXTERNAL_API"
    refresh_interval_hours: int = Field(6, ge=1, le=168)
    is_enabled: bool = True
    config: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in PROVIDER_TYPES:
            raise ValueError(f"provider_type must be one of {sorted(PROVIDER_TYPES)}")
        return normalized


class WeatherSnapshotCreate(BaseModel):
    id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    farmer_id: uuid.UUID | None = None
    parcel_id: uuid.UUID | None = None
    location_scope: str = "GEOPOINT"
    location_key: str | None = None
    lat: str | None = None
    lng: str | None = None
    fetched_at: str | None = None
    observed_at: str | None = None
    forecast_valid_from: str | None = None
    forecast_valid_to: str | None = None
    expires_at: str | None = None
    summary: str | None = None
    condition_code: str | None = None
    rainfall_probability_percent: int | None = Field(None, ge=0, le=100)
    rainfall_mm: str | None = None
    temperature_min_c: str | None = None
    temperature_max_c: str | None = None
    humidity_percent: int | None = Field(None, ge=0, le=100)
    wind_speed_kmph: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    source_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator("location_scope")
    @classmethod
    def validate_location_scope(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in LOCATION_SCOPES:
            raise ValueError(f"location_scope must be one of {sorted(LOCATION_SCOPES)}")
        return normalized


def _provider_payload(row: WeatherProviderConfig) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "provider_code": row.provider_code,
        "display_name": row.display_name,
        "provider_type": row.provider_type,
        "refresh_interval_hours": row.refresh_interval_hours,
        "is_enabled": row.is_enabled,
        "last_refresh_at": _iso(row.last_refresh_at),
        "next_refresh_at": _iso(row.next_refresh_at),
        "config": row.config or {},
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _snapshot_payload(row: WeatherSnapshot) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": row.tenant_id,
        "provider_id": str(row.provider_id) if row.provider_id else None,
        "project_id": str(row.project_id) if row.project_id else None,
        "farmer_id": str(row.farmer_id) if row.farmer_id else None,
        "parcel_id": str(row.parcel_id) if row.parcel_id else None,
        "location_scope": row.location_scope,
        "location_key": row.location_key,
        "lat": row.lat,
        "lng": row.lng,
        "fetched_at": _iso(row.fetched_at),
        "observed_at": _iso(row.observed_at),
        "forecast_valid_from": _iso(row.forecast_valid_from),
        "forecast_valid_to": _iso(row.forecast_valid_to),
        "expires_at": _iso(row.expires_at),
        "summary": row.summary,
        "condition_code": row.condition_code,
        "rainfall_probability_percent": row.rainfall_probability_percent,
        "rainfall_mm": row.rainfall_mm,
        "temperature_min_c": row.temperature_min_c,
        "temperature_max_c": row.temperature_max_c,
        "humidity_percent": row.humidity_percent,
        "wind_speed_kmph": row.wind_speed_kmph,
        "risk_flags": row.risk_flags or [],
        "source_payload": row.source_payload or {},
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.post("/providers", status_code=201)
def create_weather_provider(body: WeatherProviderCreate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    now_ts = _now()
    existing = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == x_tenant_id, WeatherProviderConfig.provider_code == body.provider_code).first()
    row = existing or WeatherProviderConfig(id=body.id or uuid.uuid4(), tenant_id=x_tenant_id, provider_code=body.provider_code, created_at=now_ts)
    row.display_name = body.display_name
    row.provider_type = body.provider_type
    row.refresh_interval_hours = body.refresh_interval_hours
    row.is_enabled = body.is_enabled
    row.config = body.config or {}
    row.metadata_ = body.metadata or {}
    row.next_refresh_at = now_ts + timedelta(hours=row.refresh_interval_hours)
    row.updated_at = now_ts
    db.add(row)
    db.commit()
    db.refresh(row)
    return _provider_payload(row)


@router.get("/providers")
def list_weather_providers(enabled: Optional[bool] = Query(None), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    query = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == x_tenant_id)
    if enabled is not None:
        query = query.filter(WeatherProviderConfig.is_enabled == enabled)
    rows = query.order_by(WeatherProviderConfig.provider_code.asc()).all()
    return {"schema_version": "weather_providers.v1", "tenant_id": x_tenant_id, "count": len(rows), "providers": [_provider_payload(row) for row in rows]}


@router.post("/snapshots", status_code=201)
def create_weather_snapshot(body: WeatherSnapshotCreate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    now_ts = _now()
    if body.provider_id:
        provider = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == body.provider_id, WeatherProviderConfig.tenant_id == x_tenant_id).first()
        if not provider:
            raise HTTPException(404, "Weather provider not found")
        provider.last_refresh_at = now_ts
        provider.next_refresh_at = now_ts + timedelta(hours=provider.refresh_interval_hours)
        provider.updated_at = now_ts
    fetched_at = _parse_dt(body.fetched_at) or now_ts
    row = WeatherSnapshot(
        id=body.id or uuid.uuid4(),
        tenant_id=x_tenant_id,
        provider_id=body.provider_id,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        location_scope=body.location_scope,
        location_key=body.location_key,
        lat=body.lat,
        lng=body.lng,
        fetched_at=fetched_at,
        observed_at=_parse_dt(body.observed_at),
        forecast_valid_from=_parse_dt(body.forecast_valid_from),
        forecast_valid_to=_parse_dt(body.forecast_valid_to),
        expires_at=_parse_dt(body.expires_at),
        summary=body.summary,
        condition_code=body.condition_code.upper() if body.condition_code else None,
        rainfall_probability_percent=body.rainfall_probability_percent,
        rainfall_mm=body.rainfall_mm,
        temperature_min_c=body.temperature_min_c,
        temperature_max_c=body.temperature_max_c,
        humidity_percent=body.humidity_percent,
        wind_speed_kmph=body.wind_speed_kmph,
        risk_flags=[str(flag).upper() for flag in (body.risk_flags or [])],
        source_payload=body.source_payload or {},
        metadata_=body.metadata or {},
        created_at=now_ts,
        updated_at=now_ts,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _snapshot_payload(row)


def _snapshot_query(db: Session, tenant_id: str):
    return db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id)


@router.get("/snapshots")
def list_weather_snapshots(
    provider_id: Optional[uuid.UUID] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    location_scope: Optional[str] = Query(None),
    location_key: Optional[str] = Query(None),
    include_expired: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = _snapshot_query(db, x_tenant_id)
    if provider_id:
        query = query.filter(WeatherSnapshot.provider_id == provider_id)
    if project_id:
        query = query.filter(WeatherSnapshot.project_id == project_id)
    if farmer_id:
        query = query.filter(WeatherSnapshot.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(WeatherSnapshot.parcel_id == parcel_id)
    if location_scope:
        query = query.filter(WeatherSnapshot.location_scope == location_scope.upper())
    if location_key:
        query = query.filter(WeatherSnapshot.location_key == location_key)
    if not include_expired:
        now_ts = _now()
        query = query.filter(or_(WeatherSnapshot.expires_at.is_(None), WeatherSnapshot.expires_at > now_ts))
    rows = query.order_by(WeatherSnapshot.fetched_at.desc(), WeatherSnapshot.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "weather_snapshots.v1",
        "tenant_id": x_tenant_id,
        "filters": {"provider_id": str(provider_id) if provider_id else None, "project_id": str(project_id) if project_id else None, "farmer_id": str(farmer_id) if farmer_id else None, "parcel_id": str(parcel_id) if parcel_id else None, "location_scope": location_scope.upper() if location_scope else None, "location_key": location_key, "include_expired": include_expired, "limit": limit},
        "count": len(rows),
        "snapshots": [_snapshot_payload(row) for row in rows],
    }


@router.get("/snapshots/latest")
def latest_weather_snapshot(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    location_scope: Optional[str] = Query(None),
    location_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    query = _snapshot_query(db, x_tenant_id)
    if project_id:
        query = query.filter(WeatherSnapshot.project_id == project_id)
    if farmer_id:
        query = query.filter(WeatherSnapshot.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(WeatherSnapshot.parcel_id == parcel_id)
    if location_scope:
        query = query.filter(WeatherSnapshot.location_scope == location_scope.upper())
    if location_key:
        query = query.filter(WeatherSnapshot.location_key == location_key)
    now_ts = _now()
    row = query.filter(or_(WeatherSnapshot.expires_at.is_(None), WeatherSnapshot.expires_at > now_ts)).order_by(WeatherSnapshot.fetched_at.desc(), WeatherSnapshot.created_at.desc()).first()
    if not row:
        raise HTTPException(404, "Weather snapshot not found")
    return _snapshot_payload(row)
