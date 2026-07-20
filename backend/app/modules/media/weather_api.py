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
from app.modules.media.weather_service import (
    WeatherAdapterResult,
    WeatherSnapshotInput,
    create_weather_snapshot_row,
    parse_datetime,
    persist_weather_provider_refresh,
    run_weather_provider_adapter,
    snapshot_input_from_mapping,
)

class WeatherRefreshWorkerResult(BaseModel):
    schema_version: str = "weather_refresh_worker.v1"
    tenant_id: str
    dry_run: bool = True
    provider_count: int = 0
    due_count: int = 0
    refreshed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    providers: list[dict] = Field(default_factory=list)
    message: str = "Weather refresh worker completed."

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])

PROVIDER_TYPES = {"EXTERNAL_API", "MANUAL", "INTERNAL_MODEL", "SATELLITE", "IOT_STATION"}
LOCATION_SCOPES = {"TENANT", "PROJECT", "FARMER", "PARCEL", "GEOPOINT", "PINCODE", "VILLAGE", "DISTRICT", "STATE", "WEATHER_GRID"}


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


def _provider_due_payload(row: WeatherProviderConfig, now_ts: datetime) -> dict:
    next_refresh_at = row.next_refresh_at
    if next_refresh_at is None and row.last_refresh_at is not None:
        next_refresh_at = row.last_refresh_at + timedelta(hours=row.refresh_interval_hours)
    is_due = bool(row.is_enabled and (next_refresh_at is None or next_refresh_at <= now_ts))
    hours_until_due = None
    if next_refresh_at is not None:
        hours_until_due = round((next_refresh_at - now_ts).total_seconds() / 3600, 2)
    return {
        **_provider_payload(row),
        "is_due": is_due,
        "hours_until_due": hours_until_due,
        "refresh_status": (row.metadata_ or {}).get("last_refresh_status"),
        "refresh_message": (row.metadata_ or {}).get("last_refresh_message"),
    }


class WeatherProviderRefreshRequest(BaseModel):
    status: str = "SUCCESS"
    message: str | None = None
    snapshots: list[WeatherSnapshotCreate] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"SUCCESS", "FAILED", "SKIPPED"}:
            raise ValueError("status must be one of SUCCESS, FAILED, SKIPPED")
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


def _weather_provider_is_due(provider, now: datetime) -> bool:
    if not getattr(provider, "is_enabled", False):
        return False
    next_refresh_at = getattr(provider, "next_refresh_at", None)
    if next_refresh_at is None:
        return True
    if next_refresh_at.tzinfo is None:
        next_refresh_at = next_refresh_at.replace(tzinfo=timezone.utc)
    return next_refresh_at <= now


def _run_due_weather_refresh_worker(
    db: Session,
    *,
    tenant_id: str,
    dry_run: bool = True,
    provider_code: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Execute or preview due backend weather provider refresh work.

    This worker intentionally does not call external weather APIs yet. In dry-run
    "or stub mode it identifies due providers and advances provider refresh metadata, "
    "so scheduler wiring, operations health, and audit behavior can stabilize "
    "before production provider adapters are connected."
    """
    now = datetime.now(timezone.utc)
    query = db.query(WeatherProviderConfig).filter(
        WeatherProviderConfig.tenant_id == tenant_id,
        WeatherProviderConfig.is_enabled == True,
    )
    if provider_code:
        query = query.filter(WeatherProviderConfig.provider_code == provider_code.strip().lower())

    providers = query.order_by(WeatherProviderConfig.provider_code.asc()).limit(limit).all()
    rows = []
    refreshed_count = 0
    failed_count = 0
    skipped_count = 0
    due_count = 0

    for provider in providers:
        is_due = _weather_provider_is_due(provider, now)
        if is_due:
            due_count += 1
        status = "DUE" if is_due else "SKIPPED_NOT_DUE"
        error_code = None
        message = None

        if not is_due:
            skipped_count += 1
        elif dry_run:
            status = "DRY_RUN_DUE"
            skipped_count += 1
        else:
            try:
                interval_hours = int(getattr(provider, "refresh_interval_hours", None) or 6)
                provider.last_refresh_at = now
                provider.next_refresh_at = now + timedelta(hours=interval_hours)
                provider.updated_at = now
                metadata = dict(getattr(provider, "metadata_", None) or {})
                metadata.update({
                    "last_worker_run_at": now.isoformat(),
                    "last_worker_status": "FETCHED_STUB",
                    "last_worker_note": "Provider adapter stub executed; external API fetch not connected yet.",
                })
                provider.metadata_ = metadata
                refreshed_count += 1
                status = "FETCHED_STUB"
                message = "Provider metadata advanced by backend refresh worker stub."
            except Exception as exc:
                failed_count += 1
                status = "FAILED"
                error_code = exc.__class__.__name__
                message = str(exc)

        rows.append({
            "provider_code": provider.provider_code,
            "display_name": provider.display_name,
            "provider_type": provider.provider_type,
            "is_due": is_due,
            "status": status,
            "error_code": error_code,
            "message": message,
            "last_refresh_at": provider.last_refresh_at.isoformat() if provider.last_refresh_at else None,
            "next_refresh_at": provider.next_refresh_at.isoformat() if provider.next_refresh_at else None,
        })

    if not dry_run:
        db.commit()

    return {
        "schema_version": "weather_refresh_worker.v1",
        "tenant_id": tenant_id,
        "dry_run": dry_run,
        "provider_count": len(providers),
        "due_count": due_count,
        "refreshed_count": refreshed_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "providers": rows,
        "message": "Weather refresh worker completed." if not dry_run else "Weather refresh worker dry run completed.",
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


@router.get("/providers/refresh-plan")
def weather_provider_refresh_plan(enabled: Optional[bool] = Query(True), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    now_ts = _now()
    query = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == x_tenant_id)
    if enabled is not None:
        query = query.filter(WeatherProviderConfig.is_enabled == enabled)
    rows = query.order_by(WeatherProviderConfig.next_refresh_at.asc().nullsfirst(), WeatherProviderConfig.provider_code.asc()).all()
    providers = [_provider_due_payload(row, now_ts) for row in rows]
    return {
        "schema_version": "weather_refresh_plan.v1",
        "tenant_id": x_tenant_id,
        "generated_at": _iso(now_ts),
        "filters": {"enabled": enabled},
        "count": len(providers),
        "due_count": sum(1 for row in providers if row["is_due"]),
        "providers": providers,
    }


@router.post("/providers/run-due")
def run_due_weather_provider_adapters(
    limit: int = Query(50, ge=1, le=200),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Run adapters for enabled providers whose next_refresh_at is due.

    This endpoint is the scheduler-safe hook for cron/worker orchestration. It
    only processes provider configs already stored in the backend and records
    adapter status even when a provider skips or fails.
    """
    now_ts = _now()
    due_providers = (
        db.query(WeatherProviderConfig)
        .filter(
            WeatherProviderConfig.tenant_id == x_tenant_id,
            WeatherProviderConfig.is_enabled == True,
            or_(WeatherProviderConfig.next_refresh_at.is_(None), WeatherProviderConfig.next_refresh_at <= now_ts),
        )
        .order_by(WeatherProviderConfig.next_refresh_at.asc().nullsfirst(), WeatherProviderConfig.provider_code.asc())
        .limit(limit)
        .all()
    )
    if dry_run:
        return {
            "schema_version": "weather_provider_due_run.v1",
            "tenant_id": x_tenant_id,
            "generated_at": _iso(now_ts),
            "dry_run": True,
            "due_count": len(due_providers),
            "processed_count": 0,
            "created_snapshot_count": 0,
            "providers": [_provider_due_payload(row, now_ts) for row in due_providers],
        }

    provider_results = []
    total_snapshots = 0
    for provider in due_providers:
        result = run_weather_provider_adapter(provider)
        created_snapshots = persist_weather_provider_refresh(db, provider=provider, result=result, timestamp=now_ts)
        total_snapshots += len(created_snapshots)
        provider_results.append({
            "provider_id": str(provider.id),
            "provider_code": provider.provider_code,
            "status": result.status,
            "message": result.message,
            "created_snapshot_count": len(created_snapshots),
            "snapshots": [_snapshot_payload(row) for row in created_snapshots],
        })
    db.commit()
    for row in due_providers:
        db.refresh(row)

    return {
        "schema_version": "weather_provider_due_run.v1",
        "tenant_id": x_tenant_id,
        "generated_at": _iso(now_ts),
        "dry_run": False,
        "due_count": len(due_providers),
        "processed_count": len(provider_results),
        "created_snapshot_count": total_snapshots,
        "providers": [
            {**provider_results[index], "provider": _provider_due_payload(provider, _now())}
            for index, provider in enumerate(due_providers)
        ],
    }


@router.post("/providers/{provider_id}/refresh")
def record_weather_provider_refresh(provider_id: uuid.UUID, body: WeatherProviderRefreshRequest, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    now_ts = _now()
    provider = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == provider_id, WeatherProviderConfig.tenant_id == x_tenant_id).first()
    if not provider:
        raise HTTPException(404, "Weather provider not found")
    result = WeatherAdapterResult(
        status=body.status,
        message=body.message,
        snapshots=[snapshot_input_from_mapping(snapshot.model_dump()) for snapshot in (body.snapshots or [])],
        metadata=body.metadata or {},
    )
    created_snapshots = persist_weather_provider_refresh(db, provider=provider, result=result, timestamp=now_ts)
    db.commit()
    db.refresh(provider)
    for row in created_snapshots:
        db.refresh(row)
    return {
        "schema_version": "weather_provider_refresh.v1",
        "tenant_id": x_tenant_id,
        "provider": _provider_due_payload(provider, _now()),
        "status": body.status,
        "message": body.message,
        "created_snapshot_count": len(created_snapshots),
        "snapshots": [_snapshot_payload(row) for row in created_snapshots],
    }


@router.post("/providers/{provider_id}/run-adapter")
def run_weather_provider_adapter_endpoint(provider_id: uuid.UUID, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID")):
    now_ts = _now()
    provider = db.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == provider_id, WeatherProviderConfig.tenant_id == x_tenant_id).first()
    if not provider:
        raise HTTPException(404, "Weather provider not found")
    result = run_weather_provider_adapter(provider)
    created_snapshots = persist_weather_provider_refresh(db, provider=provider, result=result, timestamp=now_ts)
    db.commit()
    db.refresh(provider)
    for row in created_snapshots:
        db.refresh(row)
    return {
        "schema_version": "weather_provider_adapter_run.v1",
        "tenant_id": x_tenant_id,
        "provider": _provider_due_payload(provider, _now()),
        "status": result.status,
        "message": result.message,
        "created_snapshot_count": len(created_snapshots),
        "snapshots": [_snapshot_payload(row) for row in created_snapshots],
    }


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
    row = create_weather_snapshot_row(snapshot_input_from_mapping(body.model_dump()), tenant_id=x_tenant_id, provider_id=body.provider_id, timestamp=now_ts)
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





@router.post("/refresh-worker/run-due", response_model=WeatherRefreshWorkerResult)
def run_due_weather_refresh_worker(
    dry_run: bool = Query(True),
    provider_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Run or preview due weather provider refresh work.

    For now this is a backend-only worker stub. It advances provider refresh
    metadata when dry_run=false, but does not call external provider APIs yet.
    """
    return _run_due_weather_refresh_worker(
        db,
        tenant_id=x_tenant_id,
        dry_run=dry_run,
        provider_code=provider_code,
        limit=limit,
    )

@router.get("/operations/health")
def weather_operations_health(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return backend weather-provider operational health for schedulers/admin."""
    now = datetime.now(timezone.utc)
    providers = db.query(WeatherProviderConfig).filter(
        WeatherProviderConfig.tenant_id == x_tenant_id,
    ).all()
    snapshots = db.query(WeatherSnapshot).filter(
        WeatherSnapshot.tenant_id == x_tenant_id,
    ).all()

    provider_rows = []
    enabled_count = 0
    due_count = 0
    overdue_count = 0
    failed_count = 0

    for provider in providers:
        is_enabled = bool(provider.is_enabled)
        if is_enabled:
            enabled_count += 1
        next_refresh_at = provider.next_refresh_at
        due = is_enabled and (next_refresh_at is None or next_refresh_at <= now)
        overdue = False
        if due:
            due_count += 1
            if next_refresh_at is not None:
                overdue = (now - next_refresh_at).total_seconds() > 3600
                if overdue:
                    overdue_count += 1
        last_status = ((provider.metadata_ or {}).get("last_refresh_status") or "").upper()
        failed = last_status in {"FAILED", "ERROR"}
        if failed:
            failed_count += 1
        provider_rows.append({
            "id": str(provider.id),
            "provider_code": provider.provider_code,
            "display_name": provider.display_name,
            "provider_type": provider.provider_type,
            "is_enabled": is_enabled,
            "refresh_interval_hours": provider.refresh_interval_hours,
            "last_refresh_at": provider.last_refresh_at.isoformat() if provider.last_refresh_at else None,
            "next_refresh_at": next_refresh_at.isoformat() if next_refresh_at else None,
            "due": due,
            "overdue": overdue,
            "last_refresh_status": last_status or None,
            "last_refresh_message": (provider.metadata_ or {}).get("last_refresh_message"),
        })

    fresh_snapshot_count = 0
    stale_snapshot_count = 0
    expired_snapshot_count = 0
    for snapshot in snapshots:
        if snapshot.expires_at and snapshot.expires_at <= now:
            expired_snapshot_count += 1
        elif snapshot.observed_at and (now - snapshot.observed_at).total_seconds() > 24 * 3600:
            stale_snapshot_count += 1
        else:
            fresh_snapshot_count += 1

    status = "HEALTHY"
    if enabled_count == 0:
        status = "NO_ENABLED_PROVIDERS"
    elif failed_count > 0:
        status = "DEGRADED"
    elif overdue_count > 0 or fresh_snapshot_count == 0:
        status = "ATTENTION_REQUIRED"

    return {
        "schema_version": "weather_operations_health.v1",
        "tenant_id": x_tenant_id,
        "generated_at": now.isoformat(),
        "status": status,
        "summary": {
            "provider_count": len(providers),
            "enabled_provider_count": enabled_count,
            "due_provider_count": due_count,
            "overdue_provider_count": overdue_count,
            "failed_provider_count": failed_count,
            "snapshot_count": len(snapshots),
            "fresh_snapshot_count": fresh_snapshot_count,
            "stale_snapshot_count": stale_snapshot_count,
            "expired_snapshot_count": expired_snapshot_count,
        },
        "providers": provider_rows,
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
