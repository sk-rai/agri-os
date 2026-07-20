"""Pure weather provider adapter normalization helpers.

These helpers do not make network calls. They convert provider-specific
payloads into the backend WeatherSnapshot create/persist shape so external
API integration can be tested separately from HTTP and scheduler concerns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid


def _parse_time(value: Any, *, fallback: datetime) -> datetime:
    if not value:
        return fallback
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text + 'T00:00:00+00:00')
        except ValueError:
            return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first(values: Any) -> Any:
    if isinstance(values, list) and values:
        return values[0]
    return None


def _as_number(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _condition_from_wmo(code: Any) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError):
        return 'UNKNOWN'
    if value in {0}:
        return 'CLEAR'
    if value in {1, 2, 3}:
        return 'CLOUDY'
    if value in {45, 48}:
        return 'FOG'
    if value in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
        return 'RAIN'
    if value in {71, 73, 75, 77, 85, 86}:
        return 'SNOW'
    if value in {95, 96, 99}:
        return 'STORM'
    return 'UNKNOWN'


def _risk_flags(*, rainfall_mm: Optional[float], rainfall_probability_percent: Optional[float], humidity_percent: Optional[float], temperature_max_c: Optional[float], temperature_min_c: Optional[float], wind_speed_kmph: Optional[float]) -> list[str]:
    flags: list[str] = []
    if rainfall_mm is not None and rainfall_mm >= 25:
        flags.append('HEAVY_RAIN_RISK')
    if rainfall_probability_percent is not None and rainfall_probability_percent >= 70:
        flags.append('RAIN_LIKELY')
    if (humidity_percent is not None and humidity_percent >= 80) and (rainfall_probability_percent is not None and rainfall_probability_percent >= 50):
        flags.append('FUNGAL_RISK')
    if temperature_max_c is not None and temperature_max_c >= 38:
        flags.append('HEAT_STRESS_RISK')
    if temperature_min_c is not None and temperature_min_c <= 5:
        flags.append('COLD_STRESS_RISK')
    if wind_speed_kmph is not None and wind_speed_kmph >= 35:
        flags.append('WIND_RISK')
    return flags


def normalize_open_meteo_forecast(
    payload: dict[str, Any],
    *,
    provider_id: uuid.UUID,
    location_scope: str,
    location_key: str,
    fetched_at: Optional[datetime] = None,
    refresh_interval_hours: int = 6,
    project_id: Optional[uuid.UUID] = None,
    farmer_id: Optional[uuid.UUID] = None,
    parcel_id: Optional[uuid.UUID] = None,
) -> dict[str, Any]:
    """Normalize an Open-Meteo-style forecast response into WeatherSnapshot fields."""
    now = fetched_at or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    daily = payload.get('daily') if isinstance(payload.get('daily'), dict) else {}
    hourly = payload.get('hourly') if isinstance(payload.get('hourly'), dict) else {}

    forecast_start = _parse_time(_first(daily.get('time')) or _first(hourly.get('time')), fallback=now)
    forecast_end = forecast_start + timedelta(days=1)

    rainfall_probability = _as_number(_first(daily.get('precipitation_probability_max')))
    if rainfall_probability is None:
        rainfall_probability = _as_number(_first(hourly.get('precipitation_probability')))

    rainfall_mm = _as_number(_first(daily.get('precipitation_sum')))
    if rainfall_mm is None:
        rainfall_mm = _as_number(_first(hourly.get('precipitation')))

    temperature_min = _as_number(_first(daily.get('temperature_2m_min')))
    temperature_max = _as_number(_first(daily.get('temperature_2m_max')))
    if temperature_min is None:
        temperature_min = _as_number(_first(hourly.get('temperature_2m')))
    if temperature_max is None:
        temperature_max = _as_number(_first(hourly.get('temperature_2m')))

    humidity = _as_number(_first(hourly.get('relative_humidity_2m')))
    wind = _as_number(_first(daily.get('wind_speed_10m_max')))
    if wind is None:
        wind = _as_number(_first(hourly.get('wind_speed_10m')))

    weather_code = _first(daily.get('weather_code'))
    if weather_code is None:
        weather_code = _first(hourly.get('weather_code'))
    condition = _condition_from_wmo(weather_code)

    flags = _risk_flags(
        rainfall_mm=rainfall_mm,
        rainfall_probability_percent=rainfall_probability,
        humidity_percent=humidity,
        temperature_max_c=temperature_max,
        temperature_min_c=temperature_min,
        wind_speed_kmph=wind,
    )

    summary_bits = [condition.replace('_', ' ').title()]
    if rainfall_probability is not None:
        summary_bits.append(f'rain {rainfall_probability:g}%')
    if temperature_min is not None and temperature_max is not None:
        summary_bits.append(f'{temperature_min:g}-{temperature_max:g}C')

    return {
        'provider_id': provider_id,
        'project_id': project_id,
        'farmer_id': farmer_id,
        'parcel_id': parcel_id,
        'location_scope': location_scope,
        'location_key': location_key,
        'lat': _as_number(payload.get('latitude')),
        'lng': _as_number(payload.get('longitude')),
        'fetched_at': now,
        'observed_at': None,
        'forecast_valid_from': forecast_start,
        'forecast_valid_to': forecast_end,
        'expires_at': now + timedelta(hours=max(1, int(refresh_interval_hours or 6))),
        'summary': ', '.join(summary_bits),
        'condition_code': condition,
        'rainfall_probability_percent': rainfall_probability,
        'rainfall_mm': rainfall_mm,
        'temperature_min_c': temperature_min,
        'temperature_max_c': temperature_max,
        'humidity_percent': humidity,
        'wind_speed_kmph': wind,
        'risk_flags': flags,
        'source_payload': payload,
        'metadata': {
            'schema_version': 'open_meteo_weather_adapter.v1',
            'provider': 'OPEN_METEO',
            'weather_code': weather_code,
            'timezone': payload.get('timezone'),
            'normalization': 'daily_first_hourly_fallback',
        },
    }
