"""Weather provider adapter service contract and refresh persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.media.models import WeatherProviderConfig, WeatherSnapshot


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_location_scope(value: str | None) -> str:
    return (value or "GEOPOINT").upper()


def normalize_condition_code(value: str | None) -> str | None:
    return value.upper() if value else None


def normalize_risk_flags(values: list[str] | None) -> list[str]:
    return [str(flag).upper() for flag in (values or []) if str(flag).strip()]


@dataclass
class WeatherSnapshotInput:
    id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    farmer_id: uuid.UUID | None = None
    parcel_id: uuid.UUID | None = None
    location_scope: str = "GEOPOINT"
    location_key: str | None = None
    lat: str | None = None
    lng: str | None = None
    fetched_at: str | datetime | None = None
    observed_at: str | datetime | None = None
    forecast_valid_from: str | datetime | None = None
    forecast_valid_to: str | datetime | None = None
    expires_at: str | datetime | None = None
    summary: str | None = None
    condition_code: str | None = None
    rainfall_probability_percent: int | None = None
    rainfall_mm: str | None = None
    temperature_min_c: str | None = None
    temperature_max_c: str | None = None
    humidity_percent: int | None = None
    wind_speed_kmph: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    source_payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class WeatherAdapterResult:
    status: str = "SUCCESS"
    message: str | None = None
    snapshots: list[WeatherSnapshotInput] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def snapshot_input_from_mapping(data: dict) -> WeatherSnapshotInput:
    return WeatherSnapshotInput(
        id=data.get("id"),
        provider_id=data.get("provider_id"),
        project_id=data.get("project_id"),
        farmer_id=data.get("farmer_id"),
        parcel_id=data.get("parcel_id"),
        location_scope=data.get("location_scope") or "GEOPOINT",
        location_key=data.get("location_key"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        fetched_at=data.get("fetched_at"),
        observed_at=data.get("observed_at"),
        forecast_valid_from=data.get("forecast_valid_from"),
        forecast_valid_to=data.get("forecast_valid_to"),
        expires_at=data.get("expires_at"),
        summary=data.get("summary"),
        condition_code=data.get("condition_code"),
        rainfall_probability_percent=data.get("rainfall_probability_percent"),
        rainfall_mm=data.get("rainfall_mm"),
        temperature_min_c=data.get("temperature_min_c"),
        temperature_max_c=data.get("temperature_max_c"),
        humidity_percent=data.get("humidity_percent"),
        wind_speed_kmph=data.get("wind_speed_kmph"),
        risk_flags=list(data.get("risk_flags") or []),
        source_payload=dict(data.get("source_payload") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def create_weather_snapshot_row(body: WeatherSnapshotInput, *, tenant_id: str, provider_id: uuid.UUID | None, timestamp: datetime) -> WeatherSnapshot:
    fetched_at = parse_datetime(body.fetched_at) or timestamp
    return WeatherSnapshot(
        id=body.id or uuid.uuid4(),
        tenant_id=tenant_id,
        provider_id=body.provider_id or provider_id,
        project_id=body.project_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        location_scope=normalize_location_scope(body.location_scope),
        location_key=body.location_key,
        lat=body.lat,
        lng=body.lng,
        fetched_at=fetched_at,
        observed_at=parse_datetime(body.observed_at),
        forecast_valid_from=parse_datetime(body.forecast_valid_from),
        forecast_valid_to=parse_datetime(body.forecast_valid_to),
        expires_at=parse_datetime(body.expires_at),
        summary=body.summary,
        condition_code=normalize_condition_code(body.condition_code),
        rainfall_probability_percent=body.rainfall_probability_percent,
        rainfall_mm=body.rainfall_mm,
        temperature_min_c=body.temperature_min_c,
        temperature_max_c=body.temperature_max_c,
        humidity_percent=body.humidity_percent,
        wind_speed_kmph=body.wind_speed_kmph,
        risk_flags=normalize_risk_flags(body.risk_flags),
        source_payload=body.source_payload or {},
        metadata_=body.metadata or {},
        created_at=timestamp,
        updated_at=timestamp,
    )


def persist_weather_provider_refresh(db: Session, *, provider: WeatherProviderConfig, result: WeatherAdapterResult, timestamp: datetime | None = None) -> list[WeatherSnapshot]:
    now_ts = timestamp or now_utc()
    status = (result.status or "SUCCESS").upper()
    metadata = dict(provider.metadata_ or {})
    metadata.update(result.metadata or {})
    metadata["last_refresh_status"] = status
    metadata["last_refresh_message"] = result.message
    metadata["last_refresh_snapshot_count"] = len(result.snapshots or [])
    metadata["last_refresh_recorded_at"] = now_ts.isoformat()
    provider.metadata_ = metadata
    provider.last_refresh_at = now_ts
    provider.next_refresh_at = now_ts + timedelta(hours=provider.refresh_interval_hours)
    provider.updated_at = now_ts

    created: list[WeatherSnapshot] = []
    if status == "SUCCESS":
        for snapshot in result.snapshots or []:
            row = create_weather_snapshot_row(snapshot, tenant_id=provider.tenant_id, provider_id=provider.id, timestamp=now_ts)
            db.add(row)
            created.append(row)
    db.add(provider)
    return created


def run_weather_provider_adapter(provider: WeatherProviderConfig) -> WeatherAdapterResult:
    """Run a provider adapter without making external calls yet.

    This is the code-level plug point for future Open-Meteo, IMD, satellite, IoT,
    or internal model adapters. Current behavior records a no-op/manual refresh so
    scheduler wiring can be validated without network dependencies.
    """
    provider_type = (provider.provider_type or "MANUAL").upper()
    if provider_type == "MANUAL":
        return WeatherAdapterResult(status="SKIPPED", message="Manual weather provider has no automatic adapter", metadata={"adapter": "manual_noop"})
    return WeatherAdapterResult(status="SKIPPED", message=f"No adapter registered for provider_type={provider_type}", metadata={"adapter": "unimplemented"})
