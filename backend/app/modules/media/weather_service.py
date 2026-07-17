"""Weather provider adapter service contract and refresh persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import urllib.parse
import urllib.request
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


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, list) and value:
            parsed = _num(value[0])
        else:
            parsed = _num(value)
        if parsed is not None:
            return parsed
    return None


DEFAULT_OPEN_METEO_RISK_THRESHOLDS = {
    "heavy_rain_mm": 20,
    "heavy_rain_probability_percent": 80,
    "fungal_humidity_percent": 80,
    "fungal_rain_probability_percent": 60,
    "heat_stress_temperature_max_c": 38,
    "high_wind_kmph": 40,
}


def _open_meteo_thresholds(config: dict) -> dict:
    thresholds = dict(DEFAULT_OPEN_METEO_RISK_THRESHOLDS)
    configured = config.get("risk_thresholds") or config.get("thresholds") or {}
    for key, value in configured.items():
        parsed = _num(value)
        if parsed is not None:
            thresholds[key] = parsed
    return thresholds


def _open_meteo_condition(*, rainfall_mm: float | None, rainfall_probability: float | None, weather_code: Any, thresholds: dict) -> str:
    code = int(_num(weather_code) or 0)
    if rainfall_mm is not None and rainfall_mm >= thresholds["heavy_rain_mm"]:
        return "HEAVY_RAIN"
    if rainfall_probability is not None and rainfall_probability >= thresholds["heavy_rain_probability_percent"]:
        return "HEAVY_RAIN"
    if rainfall_mm is not None and rainfall_mm > 0:
        return "RAIN"
    if code in {95, 96, 99}:
        return "THUNDERSTORM_WIND"
    if code in {61, 63, 65, 80, 81, 82}:
        return "RAIN"
    return "CLEAR"


def _open_meteo_risk_flags(*, condition_code: str, rainfall_mm: float | None, rainfall_probability: float | None, humidity_percent: float | None, temperature_max_c: float | None, wind_speed_kmph: float | None, thresholds: dict) -> list[str]:
    flags: list[str] = []
    if condition_code == "HEAVY_RAIN" or (rainfall_mm is not None and rainfall_mm >= thresholds["heavy_rain_mm"]) or (rainfall_probability is not None and rainfall_probability >= thresholds["heavy_rain_probability_percent"]):
        flags.append("HEAVY_RAIN_NEXT_24H")
    if (humidity_percent is not None and humidity_percent >= thresholds["fungal_humidity_percent"]) and ((rainfall_probability or 0) >= thresholds["fungal_rain_probability_percent"] or (rainfall_mm or 0) > 0):
        flags.append("FUNGAL_RISK")
    if temperature_max_c is not None and temperature_max_c >= thresholds["heat_stress_temperature_max_c"]:
        flags.append("HEAT_STRESS_NEXT_48H")
    if wind_speed_kmph is not None and wind_speed_kmph >= thresholds["high_wind_kmph"]:
        flags.append("HIGH_WIND_ALERT")
    return flags


def _open_meteo_live_fetch_enabled(config: dict) -> bool:
    mode = str(config.get("mode") or config.get("fetch_mode") or "").strip().lower()
    return bool(config.get("live_fetch_enabled") is True or mode == "live")


def _open_meteo_locations(config: dict) -> list[dict]:
    locations = config.get("locations") or []
    if locations:
        return list(locations)
    return [{
        "location_scope": config.get("location_scope") or "GEOPOINT",
        "location_key": config.get("location_key"),
        "lat": config.get("lat") or config.get("latitude"),
        "lng": config.get("lng") or config.get("longitude"),
    }]


def _fetch_open_meteo_payload(config: dict, location: dict) -> dict:
    lat = location.get("lat") or location.get("latitude") or config.get("lat") or config.get("latitude")
    lng = location.get("lng") or location.get("longitude") or config.get("lng") or config.get("longitude")
    if lat is None or lng is None:
        raise ValueError("Open-Meteo live fetch requires latitude/longitude per location or provider config")

    base_url = str(config.get("base_url") or "https://api.open-meteo.com/v1/forecast")
    params = {
        "latitude": str(lat),
        "longitude": str(lng),
        "timezone": str(config.get("timezone") or "auto"),
        "forecast_days": str(config.get("forecast_days") or 2),
        "current": ",".join(config.get("current_fields") or ["temperature_2m", "relative_humidity_2m", "rain", "weather_code", "wind_speed_10m"]),
        "hourly": ",".join(config.get("hourly_fields") or ["precipitation_probability", "rain", "relative_humidity_2m"]),
        "daily": ",".join(config.get("daily_fields") or ["temperature_2m_max", "temperature_2m_min", "rain_sum", "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max"]),
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    timeout_seconds = int(config.get("timeout_seconds") or 10)
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - configured weather provider URL; persisted raw payload is audited
        payload = json.loads(response.read().decode("utf-8"))
    payload.setdefault("fetched_at", now_utc().isoformat())
    payload.setdefault("request", {"url": url, "lat": str(lat), "lng": str(lng)})
    return payload


def _open_meteo_snapshot_from_payload(*, payload: dict, location: dict, provider: WeatherProviderConfig, thresholds: dict, source: str) -> WeatherSnapshotInput:
    current = payload.get("current") or payload.get("current_weather") or {}
    hourly = payload.get("hourly") or {}
    daily = payload.get("daily") or {}
    fetched_at = payload.get("fetched_at") or current.get("time") or now_utc().isoformat()
    daily_times = daily.get("time") if isinstance(daily.get("time"), list) else []
    valid_to = payload.get("forecast_valid_to") or (daily_times[-1] if daily_times else None)

    rainfall_probability = _first_number(
        current.get("precipitation_probability"),
        hourly.get("precipitation_probability"),
        daily.get("precipitation_probability_max"),
    )
    rainfall_mm = _first_number(current.get("rain"), current.get("precipitation"), hourly.get("rain"), daily.get("rain_sum"), daily.get("precipitation_sum"))
    humidity = _first_number(current.get("relative_humidity_2m"), hourly.get("relative_humidity_2m"))
    temp_min = _first_number(daily.get("temperature_2m_min"), current.get("temperature_2m"))
    temp_max = _first_number(daily.get("temperature_2m_max"), current.get("temperature_2m"))
    wind_speed = _first_number(current.get("wind_speed_10m"), current.get("windspeed"), daily.get("wind_speed_10m_max"))
    condition_code = _open_meteo_condition(rainfall_mm=rainfall_mm, rainfall_probability=rainfall_probability, weather_code=current.get("weather_code") or current.get("weathercode"), thresholds=thresholds)
    risk_flags = _open_meteo_risk_flags(
        condition_code=condition_code,
        rainfall_mm=rainfall_mm,
        rainfall_probability=rainfall_probability,
        humidity_percent=humidity,
        temperature_max_c=temp_max,
        wind_speed_kmph=wind_speed,
        thresholds=thresholds,
    )
    expires_at = (now_utc() + timedelta(hours=provider.refresh_interval_hours)).isoformat()

    return WeatherSnapshotInput(
        location_scope=str(location.get("location_scope") or "GEOPOINT"),
        location_key=location.get("location_key"),
        lat=str(location.get("lat")) if location.get("lat") is not None else None,
        lng=str(location.get("lng")) if location.get("lng") is not None else None,
        fetched_at=fetched_at,
        forecast_valid_from=payload.get("forecast_valid_from") or fetched_at,
        forecast_valid_to=valid_to,
        expires_at=expires_at,
        summary=payload.get("summary") or f"Open-Meteo normalized condition: {condition_code}",
        condition_code=condition_code,
        rainfall_probability_percent=int(rainfall_probability) if rainfall_probability is not None else None,
        rainfall_mm=str(rainfall_mm) if rainfall_mm is not None else None,
        temperature_min_c=str(temp_min) if temp_min is not None else None,
        temperature_max_c=str(temp_max) if temp_max is not None else None,
        humidity_percent=int(humidity) if humidity is not None else None,
        wind_speed_kmph=str(wind_speed) if wind_speed is not None else None,
        risk_flags=risk_flags,
        source_payload=payload,
        metadata={"adapter": "open_meteo", "source": source, "risk_thresholds": thresholds},
    )


def run_open_meteo_adapter(provider: WeatherProviderConfig) -> WeatherAdapterResult:
    config = provider.config or {}
    adapter = str(config.get("adapter") or config.get("provider") or provider.provider_code or "").lower()
    if "open_meteo" not in adapter and "open-meteo" not in adapter:
        return WeatherAdapterResult(status="SKIPPED", message="Provider is not configured for Open-Meteo adapter", metadata={"adapter": "open_meteo", "reason": "adapter_not_selected"})

    sample_payload = config.get("sample_payload") or config.get("mock_payload")
    live_enabled = _open_meteo_live_fetch_enabled(config)
    locations = _open_meteo_locations(config)
    thresholds = _open_meteo_thresholds(config)

    if not sample_payload and not live_enabled:
        return WeatherAdapterResult(status="SKIPPED", message="Open-Meteo adapter requires sample_payload or live_fetch_enabled=true", metadata={"adapter": "open_meteo", "reason": "missing_payload_or_live_fetch"})

    try:
        snapshots: list[WeatherSnapshotInput] = []
        if sample_payload:
            for location in locations:
                snapshots.append(_open_meteo_snapshot_from_payload(payload=sample_payload, location=location, provider=provider, thresholds=thresholds, source="sample_payload"))
            mode = "sample_payload"
        else:
            for location in locations:
                payload = _fetch_open_meteo_payload(config, location)
                snapshots.append(_open_meteo_snapshot_from_payload(payload=payload, location=location, provider=provider, thresholds=thresholds, source="live_fetch"))
            mode = "live_fetch"
    except Exception as exc:
        return WeatherAdapterResult(status="FAILED", message=f"Open-Meteo adapter failed: {exc}", metadata={"adapter": "open_meteo", "mode": "live_fetch" if live_enabled and not sample_payload else "sample_payload", "risk_thresholds": thresholds})

    return WeatherAdapterResult(
        status="SUCCESS",
        message=f"Open-Meteo {mode} normalized into {len(snapshots)} snapshot(s)",
        snapshots=snapshots,
        metadata={"adapter": "open_meteo", "mode": mode, "risk_thresholds": thresholds},
    )

def run_weather_provider_adapter(provider: WeatherProviderConfig) -> WeatherAdapterResult:
    """Run a provider adapter without making external calls yet.

    This is the code-level plug point for future Open-Meteo, IMD, satellite, IoT,
    or internal model adapters. Current behavior records a no-op/manual refresh so
    scheduler wiring can be validated without network dependencies.
    """
    provider_type = (provider.provider_type or "MANUAL").upper()
    config = provider.config or {}
    adapter = str(config.get("adapter") or config.get("provider") or provider.provider_code or "").lower()
    if "open_meteo" in adapter or "open-meteo" in adapter:
        return run_open_meteo_adapter(provider)
    if provider_type == "MANUAL":
        return WeatherAdapterResult(status="SKIPPED", message="Manual weather provider has no automatic adapter", metadata={"adapter": "manual_noop"})
    return WeatherAdapterResult(status="SKIPPED", message=f"No adapter registered for provider_type={provider_type}", metadata={"adapter": "unimplemented"})
