"""Pure soil enrichment provider adapter normalization helpers.

These helpers do not call external APIs. They convert provider payloads
into the backend SoilEnrichmentSnapshot create/persist shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid


def _as_number(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        for key in ('mean', 'Q0.5', 'median', 'value'):
            if key in value:
                return _as_number(value.get(key))
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any, *, fallback: datetime) -> datetime:
    if not value:
        return fallback
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _soilgrids_property(payload: dict[str, Any], key: str) -> Optional[float]:
    properties = payload.get('properties') if isinstance(payload.get('properties'), dict) else payload
    if key in properties:
        return _as_number(properties.get(key))
    layers = payload.get('layers') if isinstance(payload.get('layers'), list) else []
    for layer in layers:
        if not isinstance(layer, dict) or layer.get('name') != key:
            continue
        depths = layer.get('depths') if isinstance(layer.get('depths'), list) else []
        for depth in depths:
            values = depth.get('values') if isinstance(depth, dict) else None
            if isinstance(values, dict):
                return _as_number(values)
    return None


def normalize_soilgrids_properties(
    payload: dict[str, Any],
    *,
    parcel_id: uuid.UUID,
    farmer_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    observed_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Normalize SoilGrids-style properties into a BASELINE snapshot."""
    now = observed_at or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    ph = _soilgrids_property(payload, 'phh2o')
    organic_carbon = _soilgrids_property(payload, 'soc')
    nitrogen = _soilgrids_property(payload, 'nitrogen')
    clay = _soilgrids_property(payload, 'clay')
    sand = _soilgrids_property(payload, 'sand')
    silt = _soilgrids_property(payload, 'silt')

    texture = None
    if clay is not None and clay >= 40:
        texture = 'CLAY'
    elif sand is not None and sand >= 70:
        texture = 'SANDY'
    elif clay is not None or sand is not None or silt is not None:
        texture = 'LOAMY'

    source_payload = payload
    return {
        'parcel_id': parcel_id,
        'farmer_id': farmer_id,
        'project_id': project_id,
        'snapshot_type': 'BASELINE',
        'provider': 'SOILGRIDS',
        'provider_reference': payload.get('provider_reference') or payload.get('id'),
        'status': 'AVAILABLE',
        'observed_at': now,
        'fetched_at': now,
        'expires_at': None,
        'soil_type_code': None,
        'soil_texture': texture,
        'soil_color': None,
        'ph': ph / 10 if ph is not None and ph > 14 else ph,
        'ec': None,
        'organic_carbon_oc': organic_carbon / 10 if organic_carbon is not None and organic_carbon > 100 else organic_carbon,
        'nitrogen_n': nitrogen,
        'phosphorus_p': None,
        'potassium_k': None,
        'sulphur_s': None,
        'zinc_zn': None,
        'iron_fe': None,
        'copper_cu': None,
        'manganese_mn': None,
        'boron_bo': None,
        'surface_soil_moisture': None,
        'root_zone_soil_moisture': None,
        'soil_temperature_c': None,
        'metadata': {
            'schema_version': 'soilgrids_adapter.v1',
            'provider': 'SOILGRIDS',
            'clay': clay,
            'sand': sand,
            'silt': silt,
            'normalization': 'properties_or_layers_first_available_depth',
        },
        'source_payload': source_payload,
    }


def normalize_open_meteo_soil_moisture(
    payload: dict[str, Any],
    *,
    parcel_id: uuid.UUID,
    farmer_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    fetched_at: Optional[datetime] = None,
    refresh_interval_hours: int = 6,
) -> dict[str, Any]:
    """Normalize Open-Meteo soil fields into a MOISTURE snapshot."""
    now = fetched_at or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    hourly = payload.get('hourly') if isinstance(payload.get('hourly'), dict) else {}
    first_time = None
    if isinstance(hourly.get('time'), list) and hourly.get('time'):
        first_time = hourly['time'][0]
    observed = _parse_time(first_time, fallback=now)

    surface = _as_number((hourly.get('soil_moisture_0_to_1cm') or [None])[0] if isinstance(hourly.get('soil_moisture_0_to_1cm'), list) else hourly.get('soil_moisture_0_to_1cm'))
    mid = _as_number((hourly.get('soil_moisture_3_to_9cm') or [None])[0] if isinstance(hourly.get('soil_moisture_3_to_9cm'), list) else hourly.get('soil_moisture_3_to_9cm'))
    root = _as_number((hourly.get('soil_moisture_9_to_27cm') or [None])[0] if isinstance(hourly.get('soil_moisture_9_to_27cm'), list) else hourly.get('soil_moisture_9_to_27cm'))
    temp = _as_number((hourly.get('soil_temperature_0cm') or [None])[0] if isinstance(hourly.get('soil_temperature_0cm'), list) else hourly.get('soil_temperature_0cm'))

    root_zone = root if root is not None else mid
    return {
        'parcel_id': parcel_id,
        'farmer_id': farmer_id,
        'project_id': project_id,
        'snapshot_type': 'MOISTURE',
        'provider': 'OPEN_METEO',
        'provider_reference': payload.get('provider_reference'),
        'status': 'AVAILABLE',
        'observed_at': observed,
        'fetched_at': now,
        'expires_at': now + timedelta(hours=max(1, int(refresh_interval_hours or 6))),
        'soil_type_code': None,
        'soil_texture': None,
        'soil_color': None,
        'ph': None,
        'ec': None,
        'organic_carbon_oc': None,
        'nitrogen_n': None,
        'phosphorus_p': None,
        'potassium_k': None,
        'sulphur_s': None,
        'zinc_zn': None,
        'iron_fe': None,
        'copper_cu': None,
        'manganese_mn': None,
        'boron_bo': None,
        'surface_soil_moisture': surface,
        'root_zone_soil_moisture': root_zone,
        'soil_temperature_c': temp,
        'metadata': {
            'schema_version': 'open_meteo_soil_adapter.v1',
            'provider': 'OPEN_METEO',
            'mid_soil_moisture': mid,
            'latitude': payload.get('latitude'),
            'longitude': payload.get('longitude'),
            'normalization': 'hourly_first_value',
        },
        'source_payload': payload,
    }
