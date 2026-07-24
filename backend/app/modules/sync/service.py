"""Sync engine service: batch processing, conflict detection, audit chain.

Pipeline: Idempotency → Dependency → Conflict Detection → Commit → Audit

Per governance:
- ADR-006: Retry capped at 10, then dead_letter
- ADR-007: Conflict routing by type
- ADR-009: Audit chain with hash chaining
- Sync Engine Contract §3-7: Retry formula, dependency filtering, idempotency
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.modules.sync.models import (
    SyncProcessedEvent,
    SyncConflict,
    AuditChainEntry,
)
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project
from app.modules.master_data.digipin import ALGORITHM_VERSION as DIGIPIN_ALGORITHM_VERSION, generate_location_digipin
from app.modules.media.models import FieldEventReport, MediaAsset, MediaAttachment, QueryMessage, QueryThread, QueryThreadAudit

def _uuid_or_none(value) -> Optional[uuid.UUID]:
    if not value:
        return None
    return uuid.UUID(str(value))


def _decimal_or_none(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _first_payload_value(payload: dict, *keys: str):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _uuid_string_list_or_empty(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list of UUID values")
    return [str(uuid.UUID(str(item))) for item in value if item]



def _safe_location_digipin(latitude, longitude) -> dict | None:
    if latitude is None or longitude is None:
        return None
    try:
        return generate_location_digipin(latitude, longitude)
    except ValueError:
        return None


def _apply_farmer_home_digipin(farmer: Farmer) -> None:
    payload = _safe_location_digipin(farmer.enrollment_gps_lat, farmer.enrollment_gps_lng)
    if payload:
        farmer.home_digipin = payload["digipin"]
        farmer.home_digipin_algorithm_version = payload.get("algorithm_version") or DIGIPIN_ALGORITHM_VERSION
        farmer.home_digipin_generated_at = datetime.now(timezone.utc)
    else:
        farmer.home_digipin = None
        farmer.home_digipin_algorithm_version = None
        farmer.home_digipin_generated_at = None


def _apply_parcel_centroid_digipin(parcel: Parcel) -> None:
    payload = _safe_location_digipin(parcel.centroid_lat, parcel.centroid_lng)
    if payload:
        parcel.centroid_digipin = payload["digipin"]
        parcel.centroid_digipin_algorithm_version = payload.get("algorithm_version") or DIGIPIN_ALGORITHM_VERSION
        parcel.centroid_digipin_generated_at = datetime.now(timezone.utc)
    else:
        parcel.centroid_digipin = None
        parcel.centroid_digipin_algorithm_version = None
        parcel.centroid_digipin_generated_at = None


def _materialize_farmer_event(db: Session, tenant_id: str, actor_id: str, event: SyncEvent) -> None:
    """Upsert accepted mobile farmer sync events into the operational table.

    The Android/local entity_id is intentionally preserved as farmers.id so
    dependent parcel/crop-cycle payloads can refer to the same identifier.
    """
    if event.operation == "DELETE":
        if event.entity_id:
            farmer = db.query(Farmer).filter(
                Farmer.id == uuid.UUID(event.entity_id),
                Farmer.tenant_id == tenant_id,
            ).first()
            if farmer:
                farmer.status = "INACTIVE"
                farmer.is_active = False
                farmer.updated_at = datetime.now(timezone.utc)
        return

    payload = event.payload or {}
    farmer_id = _uuid_or_none(event.entity_id or payload.get("id") or payload.get("farmer_id"))
    if not farmer_id:
        raise ValueError("farmer sync event requires entity_id or payload.id")

    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == tenant_id).first()
    if not farmer:
        mobile_number = _first_payload_value(payload, "mobile_number", "mobileNumber", "phone") or "+919999999999"
        if mobile_number and not str(mobile_number).startswith("+91") and len(str(mobile_number)) == 10:
            mobile_number = f"+91{mobile_number}"

        farmer = (
            db.query(Farmer)
            .filter(Farmer.tenant_id == tenant_id, Farmer.mobile_number == mobile_number)
            .order_by(Farmer.updated_at.desc(), Farmer.created_at.desc())
            .first()
        )

    if not farmer:
        farmer = Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            mobile_number=mobile_number,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(farmer)

    field_map = {
        "project_id": ("project_id", "projectId"),
        "user_id": ("user_id", "userId"),
        "mobile_number": ("mobile_number", "mobileNumber", "phone"),
        "village_id": ("village_id", "villageId"),
        "village_name_manual": ("village_name_manual", "villageNameManual", "village_name", "villageName"),
        "primary_crop_code": ("primary_crop_code", "primaryCropCode"),
        "crops_by_season": ("crops_by_season", "cropsBySeason"),
        "display_name": ("display_name", "displayName", "name"),
        "father_name": ("father_name", "fatherName"),
        "age": ("age",),
        "gender": ("gender",),
        "aadhaar_number": ("aadhaar_number", "aadhaarNumber"),
        "total_land_area": ("total_land_area", "totalLandArea"),
        "total_land_unit": ("total_land_unit", "totalLandUnit"),
        "language_preference": ("language_preference", "languagePreference"),
        "enrollment_gps_lat": ("enrollment_gps_lat", "enrollmentGpsLat", "latitude"),
        "enrollment_gps_lng": ("enrollment_gps_lng", "enrollmentGpsLng", "longitude"),
        "status": ("status",),
    }
    uuid_fields = {"project_id", "user_id", "village_id"}
    decimal_fields = {"total_land_area", "enrollment_gps_lat", "enrollment_gps_lng"}
    for attr, keys in field_map.items():
        value = _first_payload_value(payload, *keys)
        if value is None:
            continue
        if attr in uuid_fields:
            value = _uuid_or_none(value)
        elif attr in decimal_fields:
            value = _decimal_or_none(value)
        setattr(farmer, attr, value)

    _apply_farmer_home_digipin(farmer)
    farmer.enrolled_by = _uuid_or_none(payload.get("enrolled_by") or payload.get("enrolledBy")) or _uuid_or_none(actor_id)
    farmer.updated_at = datetime.now(timezone.utc)


def _materialize_parcel_event(db: Session, tenant_id: str, event: SyncEvent) -> None:
    """Upsert accepted mobile parcel sync events into the operational table."""
    payload = event.payload or {}
    parcel_id = _uuid_or_none(event.entity_id or payload.get("id") or payload.get("parcel_id"))

    if event.operation == "DELETE":
        if parcel_id:
            parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == tenant_id).first()
            if parcel:
                parcel.status = "INACTIVE"
                parcel.is_active = False
                parcel.updated_at = datetime.now(timezone.utc)
        return

    if not parcel_id:
        raise ValueError("parcel sync event requires entity_id or payload.id")

    farmer_id = _uuid_or_none(_first_payload_value(payload, "farmer_id", "farmerId"))
    if not farmer_id:
        raise ValueError("parcel sync event requires farmer_id/farmerId")

    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == tenant_id).first()
    if not parcel:
        parcel = Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            reported_area=_decimal_or_none(_first_payload_value(payload, "reported_area", "reportedArea", "area")) or Decimal("0"),
            reported_area_unit=_first_payload_value(payload, "reported_area_unit", "reportedAreaUnit", "unit") or "BIGHA",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(parcel)

    parcel.farmer_id = farmer_id
    field_map = {
        "project_id": ("project_id", "projectId"),
        "village_id": ("village_id", "villageId"),
        "village_name_manual": ("village_name_manual", "villageNameManual", "village_name", "villageName"),
        "reported_area": ("reported_area", "reportedArea", "area"),
        "reported_area_unit": ("reported_area_unit", "reportedAreaUnit", "unit"),
        "current_crop_code": ("current_crop_code", "currentCropCode"),
        "soil_type_code": ("soil_type_code", "soilTypeCode"),
        "geometry_source": ("geometry_source", "geometrySource"),
        "centroid_lat": ("centroid_lat", "centroidLat", "latitude"),
        "centroid_lng": ("centroid_lng", "centroidLng", "longitude"),
        "computed_area_hectares": ("computed_area_hectares", "computedAreaHectares"),
        "geometry_accuracy_meters": ("geometry_accuracy_meters", "geometryAccuracyMeters"),
        "local_name": ("local_name", "localName"),
        "survey_number": ("survey_number", "surveyNumber"),
        "ownership_type": ("ownership_type", "ownershipType"),
        "annual_rent": ("annual_rent", "annualRent"),
        "annual_rent_currency": ("annual_rent_currency", "annualRentCurrency"),
        "share_percentage": ("share_percentage", "sharePercentage"),
        "sharecrop_percentage": ("sharecrop_percentage", "sharecropPercentage"),
        "irrigation_source": ("irrigation_source", "irrigationSource"),
        "crops_by_season": ("crops_by_season", "cropsBySeason"),
        "status": ("status",),
    }
    uuid_fields = {"project_id", "village_id"}
    decimal_fields = {
        "reported_area", "centroid_lat", "centroid_lng",
        "computed_area_hectares", "geometry_accuracy_meters", "annual_rent",
    }
    int_fields = {"share_percentage", "sharecrop_percentage"}
    for attr, keys in field_map.items():
        value = _first_payload_value(payload, *keys)
        if value is None:
            continue
        if attr in uuid_fields:
            value = _uuid_or_none(value)
        elif attr in decimal_fields:
            value = _decimal_or_none(value)
        elif attr in int_fields:
            value = int(value)
        setattr(parcel, attr, value)

    _apply_parcel_centroid_digipin(parcel)
    parcel.updated_at = datetime.now(timezone.utc)


def _validate_lng_lat(point: list, label: str) -> tuple[float, float]:
    if not isinstance(point, list) or len(point) < 2:
        raise ValueError(f"{label} must be [longitude, latitude]")
    lng = float(point[0])
    lat = float(point[1])
    if not -180 <= lng <= 180:
        raise ValueError(f"{label} longitude out of range")
    if not -90 <= lat <= 90:
        raise ValueError(f"{label} latitude out of range")
    return lng, lat


def _normalize_parcel_geojson(geojson: Optional[dict], geometry_source: str) -> tuple[Optional[dict], Optional[Decimal], Optional[Decimal]]:
    if not geojson:
        return None, None, None

    geometry_type = geojson.get("type")
    coordinates = geojson.get("coordinates")

    if geometry_type == "Point":
        lng, lat = _validate_lng_lat(coordinates, "Point")
        if geometry_source not in ("PIN_DROP", "GPS_WALK", "MANUAL_DRAW", "SATELLITE"):
            raise ValueError("Point GeoJSON requires a GPS geometry_source")
        return {"type": "Point", "coordinates": [lng, lat]}, Decimal(str(lat)), Decimal(str(lng))

    if geometry_type == "Polygon":
        if geometry_source not in ("GPS_WALK", "MANUAL_DRAW", "SATELLITE"):
            raise ValueError("Polygon GeoJSON requires GPS_WALK, MANUAL_DRAW, or SATELLITE geometry_source")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise ValueError("Polygon coordinates must contain at least one linear ring")

        normalized_rings = []
        for ring_index, ring in enumerate(coordinates):
            if not isinstance(ring, list):
                raise ValueError(f"Polygon ring {ring_index} must be a list")
            normalized_ring = []
            for point_index, point in enumerate(ring):
                lng, lat = _validate_lng_lat(point, f"Polygon ring {ring_index} point {point_index}")
                normalized_ring.append([lng, lat])
            if len(normalized_ring) < 3:
                raise ValueError(f"Polygon ring {ring_index} must have at least 3 distinct points")
            if normalized_ring[0] != normalized_ring[-1]:
                normalized_ring.append(normalized_ring[0])
            if len(normalized_ring) < 4:
                raise ValueError(f"Polygon ring {ring_index} must have at least 4 coordinates including closure")
            normalized_rings.append(normalized_ring)
        return {"type": "Polygon", "coordinates": normalized_rings}, None, None

    raise ValueError("GeoJSON type must be Point or Polygon")


def _polygon_centroid_area(db: Session, normalized_geojson: dict) -> tuple[Decimal, Decimal, Decimal]:
    row = db.execute(
        text(
            """
            SELECT
                ST_Y(ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326))) AS lat,
                ST_X(ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326))) AS lng,
                ST_Area(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)::geography) / 10000.0 AS area_hectares
            """
        ),
        {"geojson": json.dumps(normalized_geojson)},
    ).fetchone()
    if not row:
        raise ValueError("Could not compute polygon centroid/area")
    return Decimal(str(row.lat)), Decimal(str(row.lng)), Decimal(str(row.area_hectares))


def _materialize_parcel_geometry_event(db: Session, tenant_id: str, actor_id: str, event: SyncEvent) -> None:
    """Apply offline geometry updates from Android sync.

    Supports entity_type PARCEL_GEOMETRY. entity_id is the parcel_id; payload may
    also include parcel_id/parcelId. PIN_DROP is centroid-only for MVP. GPS_WALK
    stores a PostGIS polygon and computes centroid + area.
    """
    if event.operation == "DELETE":
        raise ValueError("PARCEL_GEOMETRY DELETE is not supported")

    payload = event.payload or {}
    parcel_id = _uuid_or_none(event.entity_id or _first_payload_value(payload, "parcel_id", "parcelId"))
    if not parcel_id:
        raise ValueError("PARCEL_GEOMETRY requires entity_id or parcel_id")

    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == tenant_id).first()
    if not parcel:
        raise ValueError(f"Parcel {parcel_id} not found for geometry sync")

    geometry_source = _first_payload_value(payload, "geometry_source", "geometrySource") or parcel.geometry_source or "NONE"
    geometry_source = str(geometry_source).upper()
    if geometry_source not in ("NONE", "PIN_DROP", "GPS_WALK", "MANUAL_DRAW", "SATELLITE"):
        raise ValueError(f"Unsupported geometry_source {geometry_source}")

    geojson = _first_payload_value(payload, "geojson", "geoJson", "geometry")
    normalized_geojson, point_lat, point_lng = _normalize_parcel_geojson(geojson, geometry_source)

    centroid_lat = point_lat or _decimal_or_none(_first_payload_value(payload, "centroid_lat", "centroidLat", "latitude"))
    centroid_lng = point_lng or _decimal_or_none(_first_payload_value(payload, "centroid_lng", "centroidLng", "longitude"))
    accuracy_meters = _decimal_or_none(_first_payload_value(payload, "accuracy_meters", "accuracyMeters", "geometry_accuracy_meters", "geometryAccuracyMeters"))

    if geometry_source == "PIN_DROP" and normalized_geojson is None and (centroid_lat is None or centroid_lng is None):
        raise ValueError("PIN_DROP requires centroid_lat/centroid_lng or Point GeoJSON")
    if geometry_source in ("GPS_WALK", "MANUAL_DRAW", "SATELLITE") and (not normalized_geojson or normalized_geojson.get("type") != "Polygon"):
        raise ValueError(f"{geometry_source} requires Polygon GeoJSON")

    parcel.geometry_source = geometry_source
    parcel.geometry_accuracy_meters = accuracy_meters
    parcel.geometry_captured_at = datetime.now(timezone.utc)
    parcel.geometry_captured_by = _uuid_or_none(actor_id)

    if normalized_geojson and normalized_geojson.get("type") == "Polygon":
        centroid_lat, centroid_lng, area_hectares = _polygon_centroid_area(db, normalized_geojson)
        parcel.centroid_lat = centroid_lat
        parcel.centroid_lng = centroid_lng
        parcel.computed_area_hectares = area_hectares
        db.flush()
        db.execute(
            text(
                """
                UPDATE parcels
                SET geometry = ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)
                WHERE id = :parcel_id AND tenant_id = :tenant_id
                """
            ),
            {"geojson": json.dumps(normalized_geojson), "parcel_id": str(parcel_id), "tenant_id": tenant_id},
        )
    else:
        if centroid_lat is not None and centroid_lng is not None:
            parcel.centroid_lat = centroid_lat
            parcel.centroid_lng = centroid_lng
        parcel.computed_area_hectares = None
        db.flush()
        db.execute(
            text("UPDATE parcels SET geometry = NULL WHERE id = :parcel_id AND tenant_id = :tenant_id"),
            {"parcel_id": str(parcel_id), "tenant_id": tenant_id},
        )

    _apply_parcel_centroid_digipin(parcel)
    parcel.updated_at = datetime.now(timezone.utc)


def _materialize_farmer_project_enrollment_event(
    db: Session,
    tenant_id: str,
    actor_id: str,
    event: SyncEvent,
) -> None:
    """Upsert accepted offline project enrollment events into membership table.

    Android/project-led enrollment can arrive through sync before the web admin
    flow is used. The membership row is the durable source of truth; the legacy
    farmers.project_id column is only backfilled for compatibility with older
    screens and reports.
    """
    payload = event.payload or {}
    enrollment_id = _uuid_or_none(
        event.entity_id
        or _first_payload_value(payload, "id", "enrollment_id", "enrollmentId")
    )

    def find_existing():
        if enrollment_id:
            existing = db.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.id == enrollment_id,
                FarmerProjectEnrollment.tenant_id == tenant_id,
            ).first()
            if existing:
                return existing

        farmer_lookup = _uuid_or_none(_first_payload_value(payload, "farmer_id", "farmerId"))
        project_lookup = _uuid_or_none(_first_payload_value(payload, "project_id", "projectId"))
        if farmer_lookup and project_lookup:
            return db.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.tenant_id == tenant_id,
                FarmerProjectEnrollment.farmer_id == farmer_lookup,
                FarmerProjectEnrollment.project_id == project_lookup,
            ).first()
        return None

    if event.operation == "DELETE":
        enrollment = find_existing()
        if enrollment:
            enrollment.status = "ARCHIVED"
            enrollment.is_active = False
            enrollment.updated_at = datetime.now(timezone.utc)
        return

    farmer_id = _uuid_or_none(_first_payload_value(payload, "farmer_id", "farmerId"))
    project_id = _uuid_or_none(_first_payload_value(payload, "project_id", "projectId"))
    if not farmer_id or not project_id:
        raise ValueError("farmer project enrollment sync requires farmer_id and project_id")

    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == tenant_id).first()
    if not farmer:
        raise ValueError("farmer project enrollment sync references unknown farmer")

    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise ValueError("farmer project enrollment sync references unknown project")

    enrollment = find_existing()
    if not enrollment:
        enrollment = FarmerProjectEnrollment(
            id=enrollment_id or uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)

    enrollment.farmer_id = farmer_id
    enrollment.project_id = project_id
    enrollment.enrollment_method = str(
        _first_payload_value(payload, "enrollment_method", "enrollmentMethod")
        or enrollment.enrollment_method
        or "SYNC_MATERIALIZED"
    ).upper()
    enrollment.enrollment_source = _first_payload_value(
        payload,
        "enrollment_source",
        "enrollmentSource",
    ) or enrollment.enrollment_source or "sync"
    enrollment.enrollment_batch_id = _first_payload_value(
        payload,
        "enrollment_batch_id",
        "enrollmentBatchId",
    ) or enrollment.enrollment_batch_id
    enrollment.enrolled_by = _uuid_or_none(
        _first_payload_value(payload, "enrolled_by", "enrolledBy")
    ) or _uuid_or_none(actor_id)
    enrollment.status = str(_first_payload_value(payload, "status") or enrollment.status or "ACTIVE").upper()

    parcel_ids = _first_payload_value(payload, "parcel_ids", "parcelIds")
    if parcel_ids is not None:
        enrollment.parcel_ids = _uuid_string_list_or_empty(parcel_ids)

    assigned_user_ids = _first_payload_value(payload, "assigned_user_ids", "assignedUserIds")
    if assigned_user_ids is not None:
        enrollment.assigned_user_ids = _uuid_string_list_or_empty(assigned_user_ids)

    metadata = _first_payload_value(payload, "metadata", "metadata_")
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("farmer project enrollment metadata must be an object")
        enrollment.metadata_ = metadata
    elif enrollment.metadata_ is None:
        enrollment.metadata_ = {}

    notes = _first_payload_value(payload, "notes")
    if notes is not None:
        enrollment.notes = notes

    enrollment.is_active = enrollment.status != "ARCHIVED"
    enrollment.updated_at = datetime.now(timezone.utc)

    if not farmer.project_id and enrollment.status in ("ACTIVE", "PENDING"):
        farmer.project_id = project_id
        farmer.updated_at = datetime.now(timezone.utc)



FIELD_EVENT_TYPES = {"RAIN", "PEST", "DISEASE", "HAILSTORM", "LOCUST", "FLOOD", "DROUGHT_STRESS", "THUNDERSTORM_WIND", "HEAT_STRESS", "COLD_STRESS", "IRRIGATION_FAILURE", "OTHER"}
FIELD_EVENT_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
FIELD_EVENT_SOURCES = {"FARMER_ANDROID", "FIELD_AGENT_ANDROID", "ADMIN_WEB", "EXTERNAL_API", "IOT_DEVICE"}
FIELD_EVENT_STATUSES = {"REPORTED", "UNDER_REVIEW", "ADVISORY_SENT", "RESOLVED", "DISMISSED"}
QUERY_CATEGORIES = {"CROP_HEALTH", "INPUT_USAGE", "IRRIGATION", "MARKET", "INSURANCE", "TECH_SUPPORT", "OTHER"}
QUERY_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
QUERY_STATUSES = {"OPEN", "ASSIGNED", "ANSWERED", "CLOSED"}
QUERY_SENDER_TYPES = {"FARMER", "FIELD_AGENT", "AGRONOMIST", "ADMIN", "SYSTEM"}
QUERY_MESSAGE_TYPES = {"TEXT", "AUDIO", "PHOTO", "DOCUMENT", "SYSTEM"}

def _normalized_choice(value, allowed: set[str], default: str, label: str) -> str:
    normalized = str(value or default).upper()
    if normalized not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)}")
    return normalized


def _datetime_or_now(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return datetime.now(timezone.utc)


def _string_or_none(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _validate_tenant_reference(db: Session, tenant_id: str, model, value, label: str):
    if value and not db.query(model).filter(model.id == value, model.tenant_id == tenant_id).first():
        raise ValueError(f"field event sync references unknown {label}")

def _record_query_sync_audit(db: Session, *, tenant_id: str, thread_id: uuid.UUID, action: str, actor_type=None, actor_id=None, before=None, after=None, reason=None, metadata=None, timestamp=None) -> None:
    db.add(QueryThreadAudit(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        thread_id=thread_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        before=before or {},
        after=after or {},
        reason=reason,
        metadata_=metadata or {},
        created_at=timestamp or datetime.now(timezone.utc),
    ))


def _query_message_attachment_payloads(payload: dict) -> list[dict]:
    attachments = _first_payload_value(payload, "media_attachments", "mediaAttachments", "attachments")
    if attachments is None:
        return []
    if not isinstance(attachments, list):
        raise ValueError("query message media_attachments must be a list")
    return attachments


def _materialize_query_message_attachments(db: Session, tenant_id: str, message_id: uuid.UUID, payload: dict, timestamp: datetime) -> int:
    count = 0
    for index, item in enumerate(_query_message_attachment_payloads(payload)):
        if not isinstance(item, dict):
            raise ValueError("query message media attachment must be an object")
        asset_id = _uuid_or_none(_first_payload_value(item, "media_asset_id", "mediaAssetId", "asset_id", "assetId"))
        if not asset_id:
            raise ValueError("query message media attachment requires media_asset_id")
        asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.tenant_id == tenant_id).first()
        if not asset:
            raise ValueError(f"query message sync references unknown media asset {asset_id}")

        attachment = db.query(MediaAttachment).filter(
            MediaAttachment.tenant_id == tenant_id,
            MediaAttachment.media_asset_id == asset_id,
            MediaAttachment.entity_type == "QUERY_MESSAGE",
            MediaAttachment.entity_id == message_id,
        ).first()

        if not attachment:
            attachment = MediaAttachment(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                media_asset_id=asset_id,
                entity_type="QUERY_MESSAGE",
                entity_id=message_id,
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(attachment)

        attachment.purpose = str(_first_payload_value(item, "purpose") or attachment.purpose or "QUERY_ATTACHMENT").upper()
        attachment.caption = _string_or_none(_first_payload_value(item, "caption"))
        attachment.display_order = int(_first_payload_value(item, "display_order", "displayOrder") or index)
        attachment.is_primary = bool(_first_payload_value(item, "is_primary", "isPrimary") or False)
        attachment.metadata_ = _first_payload_value(item, "metadata", "metadata_") or attachment.metadata_ or {}
        attachment.updated_at = timestamp
        count += 1
    return count

def _field_event_attachment_payloads(payload: dict) -> list[dict]:
    attachments = _first_payload_value(payload, "media_attachments", "mediaAttachments", "attachments")
    if attachments is None:
        return []
    if not isinstance(attachments, list):
        raise ValueError("field event media_attachments must be a list")
    return attachments


def _materialize_field_event_media_attachments(db: Session, tenant_id: str, report_id: uuid.UUID, payload: dict, timestamp: datetime) -> None:
    for index, item in enumerate(_field_event_attachment_payloads(payload)):
        if not isinstance(item, dict):
            raise ValueError("field event media attachment must be an object")
        asset_id = _uuid_or_none(_first_payload_value(item, "media_asset_id", "mediaAssetId", "asset_id", "assetId"))
        if not asset_id:
            raise ValueError("field event media attachment requires media_asset_id")
        asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.tenant_id == tenant_id).first()
        if not asset:
            raise ValueError(f"field event sync references unknown media asset {asset_id}")

        attachment_id = _uuid_or_none(_first_payload_value(item, "id", "attachment_id", "attachmentId"))
        query = db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id)
        if attachment_id:
            attachment = query.filter(MediaAttachment.id == attachment_id).first()
        else:
            attachment = query.filter(
                MediaAttachment.media_asset_id == asset_id,
                MediaAttachment.entity_type == "FIELD_EVENT",
                MediaAttachment.entity_id == report_id,
            ).first()

        if not attachment:
            attachment = MediaAttachment(
                id=attachment_id or uuid.uuid4(),
                tenant_id=tenant_id,
                media_asset_id=asset_id,
                entity_type="FIELD_EVENT",
                entity_id=report_id,
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(attachment)

        attachment.media_asset_id = asset_id
        attachment.entity_type = "FIELD_EVENT"
        attachment.entity_id = report_id
        attachment.purpose = str(_first_payload_value(item, "purpose") or attachment.purpose or "GENERAL").upper()
        attachment.caption = _string_or_none(_first_payload_value(item, "caption"))
        attachment.display_order = int(_first_payload_value(item, "display_order", "displayOrder") or index)
        attachment.is_primary = bool(_first_payload_value(item, "is_primary", "isPrimary") or False)
        metadata = _first_payload_value(item, "metadata", "metadata_")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("field event media attachment metadata must be an object")
        attachment.metadata_ = metadata or attachment.metadata_ or {}
        attachment.updated_at = timestamp

def _materialize_query_thread_event(db: Session, tenant_id: str, actor_id: str, event: SyncEvent) -> None:
    payload = event.payload or {}
    thread_id = _uuid_or_none(event.entity_id or _first_payload_value(payload, "id", "thread_id", "threadId"))
    if not thread_id:
        raise ValueError("QUERY_THREAD requires entity_id or payload.id")

    thread = db.query(QueryThread).filter(QueryThread.id == thread_id, QueryThread.tenant_id == tenant_id).first()

    if event.operation == "DELETE":
        if thread:
            thread.is_active = False
            thread.status = "CLOSED"
            thread.updated_at = datetime.now(timezone.utc)
            _record_query_sync_audit(db, tenant_id=tenant_id, thread_id=thread.id, action="SYNC_DELETE_THREAD", actor_type="SYSTEM", actor_id=_uuid_or_none(actor_id), timestamp=thread.updated_at)
        return

    farmer_id = _uuid_or_none(_first_payload_value(payload, "farmer_id", "farmerId"))
    if not farmer_id:
        raise ValueError("QUERY_THREAD requires farmer_id")

    project_id = _uuid_or_none(_first_payload_value(payload, "project_id", "projectId"))
    parcel_id = _uuid_or_none(_first_payload_value(payload, "parcel_id", "parcelId"))

    _validate_tenant_reference(db, tenant_id, Farmer, farmer_id, "farmer")
    _validate_tenant_reference(db, tenant_id, Project, project_id, "project")
    _validate_tenant_reference(db, tenant_id, Parcel, parcel_id, "parcel")

    now_ts = datetime.now(timezone.utc)
    created = thread is None
    before = None if created else {"status": thread.status, "assigned_to": str(thread.assigned_to) if thread.assigned_to else None}

    if not thread:
        thread = QueryThread(id=thread_id, tenant_id=tenant_id, created_at=now_ts, updated_at=now_ts)
        db.add(thread)

    thread.project_id = project_id
    thread.farmer_id = farmer_id
    thread.parcel_id = parcel_id
    thread.crop_cycle_id = _uuid_or_none(_first_payload_value(payload, "crop_cycle_id", "cropCycleId"))
    thread.stage_code = _string_or_none(_first_payload_value(payload, "stage_code", "stageCode"))
    thread.subject = _string_or_none(_first_payload_value(payload, "subject")) or thread.subject or "Farmer query"
    thread.category = _normalized_choice(_first_payload_value(payload, "category"), QUERY_CATEGORIES, "OTHER", "query category")
    thread.priority = _normalized_choice(_first_payload_value(payload, "priority"), QUERY_PRIORITIES, "MEDIUM", "query priority")
    thread.status = _normalized_choice(_first_payload_value(payload, "status"), QUERY_STATUSES, "OPEN", "query status")
    thread.assigned_to = _uuid_or_none(_first_payload_value(payload, "assigned_to", "assignedTo"))
    last_message_at = _first_payload_value(payload, "last_message_at", "lastMessageAt")
    if last_message_at:
        thread.last_message_at = _datetime_or_now(last_message_at)

    metadata = _first_payload_value(payload, "metadata", "metadata_")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("query thread metadata must be an object")
    thread.metadata_ = metadata or thread.metadata_ or {}
    thread.is_active = True
    thread.updated_at = now_ts

    _record_query_sync_audit(
        db,
        tenant_id=tenant_id,
        thread_id=thread.id,
        action="SYNC_CREATE_THREAD" if created else "SYNC_UPDATE_THREAD",
        actor_type="SYSTEM",
        actor_id=_uuid_or_none(actor_id),
        before=before,
        after={"status": thread.status, "subject": thread.subject, "category": thread.category, "priority": thread.priority},
        metadata={"sync_event_id": str(event.event_id)},
        timestamp=now_ts,
    )


def _materialize_query_message_event(db: Session, tenant_id: str, actor_id: str, event: SyncEvent) -> None:
    payload = event.payload or {}
    message_id = _uuid_or_none(event.entity_id or _first_payload_value(payload, "id", "message_id", "messageId"))
    if not message_id:
        raise ValueError("QUERY_MESSAGE requires entity_id or payload.id")

    thread_id = _uuid_or_none(_first_payload_value(payload, "thread_id", "threadId"))
    if not thread_id:
        raise ValueError("QUERY_MESSAGE requires thread_id")

    thread = db.query(QueryThread).filter(QueryThread.id == thread_id, QueryThread.tenant_id == tenant_id, QueryThread.is_active == True).first()
    if not thread:
        raise ValueError(f"QUERY_MESSAGE references missing thread {thread_id}")

    now_ts = datetime.now(timezone.utc)
    message = db.query(QueryMessage).filter(QueryMessage.id == message_id, QueryMessage.tenant_id == tenant_id).first()
    created = message is None

    if event.operation == "DELETE":
        if message:
            message.is_active = False
            message.updated_at = now_ts
            _record_query_sync_audit(db, tenant_id=tenant_id, thread_id=thread.id, action="SYNC_DELETE_MESSAGE", actor_type="SYSTEM", actor_id=_uuid_or_none(actor_id), after={"message_id": str(message.id)}, timestamp=now_ts)
        return

    if not message:
        message = QueryMessage(id=message_id, tenant_id=tenant_id, thread_id=thread_id, created_at=now_ts, updated_at=now_ts)
        db.add(message)

    message.thread_id = thread_id
    message.sender_type = _normalized_choice(_first_payload_value(payload, "sender_type", "senderType"), QUERY_SENDER_TYPES, "FARMER", "query sender type")
    message.sender_id = _uuid_or_none(_first_payload_value(payload, "sender_id", "senderId"))
    message.message_type = _normalized_choice(_first_payload_value(payload, "message_type", "messageType"), QUERY_MESSAGE_TYPES, "TEXT", "query message type")
    message.body_text = _string_or_none(_first_payload_value(payload, "body_text", "bodyText", "text", "message"))

    metadata = _first_payload_value(payload, "metadata", "metadata_")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("query message metadata must be an object")
    message.metadata_ = metadata or message.metadata_ or {}
    message.is_active = True
    message.updated_at = now_ts

    thread.last_message_at = now_ts
    thread.updated_at = now_ts
    if message.sender_type in {"AGRONOMIST", "ADMIN", "FIELD_AGENT", "SYSTEM"} and thread.status == "OPEN":
        thread.status = "ANSWERED"

    attachment_count = _materialize_query_message_attachments(db, tenant_id, message.id, payload, now_ts)

    _record_query_sync_audit(
        db,
        tenant_id=tenant_id,
        thread_id=thread.id,
        action="SYNC_ADD_MESSAGE" if created else "SYNC_UPDATE_MESSAGE",
        actor_type=message.sender_type,
        actor_id=message.sender_id,
        after={"message_id": str(message.id), "message_type": message.message_type, "status": thread.status},
        metadata={"sync_event_id": str(event.event_id), "media_attachment_count": attachment_count},
        timestamp=now_ts,
    )
def _materialize_field_event_report_event(db: Session, tenant_id: str, event: SyncEvent) -> None:
    """Upsert accepted offline field event reports into operational table."""
    payload = event.payload or {}
    report_id = _uuid_or_none(event.entity_id or _first_payload_value(payload, "id", "event_id", "eventId"))
    if not report_id:
        raise ValueError("FIELD_EVENT_REPORT requires entity_id or payload.id")

    report = db.query(FieldEventReport).filter(
        FieldEventReport.id == report_id,
        FieldEventReport.tenant_id == tenant_id,
    ).first()

    if event.operation == "DELETE":
        if report:
            report.is_active = False
            report.status = "DISMISSED"
            report.updated_at = datetime.now(timezone.utc)
        return

    farmer_id = _uuid_or_none(_first_payload_value(payload, "farmer_id", "farmerId"))
    if not farmer_id:
        raise ValueError("FIELD_EVENT_REPORT requires farmer_id")

    project_id = _uuid_or_none(_first_payload_value(payload, "project_id", "projectId"))
    parcel_id = _uuid_or_none(_first_payload_value(payload, "parcel_id", "parcelId"))
    crop_cycle_id = _uuid_or_none(_first_payload_value(payload, "crop_cycle_id", "cropCycleId"))

    _validate_tenant_reference(db, tenant_id, Farmer, farmer_id, "farmer")
    _validate_tenant_reference(db, tenant_id, Project, project_id, "project")
    _validate_tenant_reference(db, tenant_id, Parcel, parcel_id, "parcel")

    now_ts = datetime.now(timezone.utc)
    if not report:
        report = FieldEventReport(
            id=report_id,
            tenant_id=tenant_id,
            created_at=now_ts,
            updated_at=now_ts,
        )
        db.add(report)

    report.project_id = project_id
    report.farmer_id = farmer_id
    report.parcel_id = parcel_id
    report.crop_cycle_id = crop_cycle_id
    report.stage_code = _string_or_none(_first_payload_value(payload, "stage_code", "stageCode"))
    report.event_type = _normalized_choice(_first_payload_value(payload, "event_type", "eventType"), FIELD_EVENT_TYPES, "OTHER", "field event type")
    report.severity = _normalized_choice(_first_payload_value(payload, "severity"), FIELD_EVENT_SEVERITIES, "MEDIUM", "field event severity")
    report.event_date = _datetime_or_now(_first_payload_value(payload, "event_date", "eventDate", "occurred_at", "occurredAt"))
    report.reported_at = _datetime_or_now(_first_payload_value(payload, "reported_at", "reportedAt"))
    report.lat = _string_or_none(_first_payload_value(payload, "lat", "latitude"))
    report.lng = _string_or_none(_first_payload_value(payload, "lng", "longitude"))
    report.accuracy_meters = _string_or_none(_first_payload_value(payload, "accuracy_meters", "accuracyMeters"))
    report.description = _string_or_none(_first_payload_value(payload, "description", "notes"))
    report.estimated_area_affected = _string_or_none(_first_payload_value(payload, "estimated_area_affected", "estimatedAreaAffected"))
    report.estimated_loss_percent = _string_or_none(_first_payload_value(payload, "estimated_loss_percent", "estimatedLossPercent"))
    report.source = _normalized_choice(_first_payload_value(payload, "source"), FIELD_EVENT_SOURCES, "FARMER_ANDROID", "field event source")
    report.external_source = _string_or_none(_first_payload_value(payload, "external_source", "externalSource"))
    report.external_event_id = _string_or_none(_first_payload_value(payload, "external_event_id", "externalEventId"))
    report.status = _normalized_choice(_first_payload_value(payload, "status"), FIELD_EVENT_STATUSES, "REPORTED", "field event status")

    metadata = _first_payload_value(payload, "metadata", "metadata_")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("field event metadata must be an object")
    report.metadata_ = metadata or report.metadata_ or {}
    report.is_active = report.status != "DISMISSED"
    report.updated_at = now_ts
    _materialize_field_event_media_attachments(db, tenant_id, report.id, payload, now_ts)


def materialize_operational_event(db: Session, tenant_id: str, actor_id: str, event: SyncEvent) -> None:
    entity_type = (event.entity_type or "").lower()
    if entity_type == "farmer":
        _materialize_farmer_event(db, tenant_id, actor_id, event)
    elif entity_type == "parcel":
        _materialize_parcel_event(db, tenant_id, event)
    elif entity_type in ("parcel_geometry", "parcelgeometry"):
        _materialize_parcel_geometry_event(db, tenant_id, actor_id, event)
    elif entity_type in ("farmer_project_enrollment", "farmerprojectenrollment", "project_enrollment", "projectenrollment"):
        _materialize_farmer_project_enrollment_event(db, tenant_id, actor_id, event)
    elif entity_type in ("query_thread", "querythread", "farmer_query_thread", "farmerquerythread"):
        _materialize_query_thread_event(db, tenant_id, actor_id, event)
    elif entity_type in ("query_message", "querymessage", "farmer_query_message", "farmerquerymessage"):
        _materialize_query_message_event(db, tenant_id, actor_id, event)
    elif entity_type in ("field_event_report", "fieldeventreport", "field_event", "fieldevent"):
        _materialize_field_event_report_event(db, tenant_id, event)


# --- Schemas for sync events ---

class SyncEvent:
    """A single sync event from the mobile client."""

    def __init__(self, data: dict):
        self.event_id = data["event_id"]
        self.entity_type = data["entity_type"]
        self.entity_id = data.get("entity_id")
        self.operation = data["operation"]  # CREATE, UPDATE, DELETE
        self.payload = data["payload"]
        self.client_version = data.get("version", 1)
        self.dependency_ids = data.get("dependency_ids", [])
        self.metadata = data.get("metadata", {})


class SyncResult:
    """Result of processing a sync batch."""

    def __init__(self):
        self.accepted: list[str] = []  # event_ids committed
        self.conflicts: list[dict] = []  # event_ids with conflict info
        self.failed: list[dict] = []  # event_ids with error info


# --- Audit Chain ---

def compute_chain_hash(
    prev_hash: str,
    action: str,
    payload_hash: str,
    actor_id: str,
    timestamp: str,
) -> str:
    """Compute chain hash: SHA256(prev + action + payload + actor + time)."""
    data = f"{prev_hash}:{action}:{payload_hash}:{actor_id}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()


def compute_payload_hash(payload: dict) -> str:
    """SHA256 of deterministic JSON serialization."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def get_prev_chain_hash(db: Session, tenant_id: str) -> str:
    """Get the most recent chain_hash for this tenant."""
    result = db.execute(
        text("""
            SELECT chain_hash FROM audit_chain
            WHERE tenant_id = :tenant_id
            ORDER BY id DESC LIMIT 1
        """),
        {"tenant_id": tenant_id},
    ).fetchone()
    return result[0] if result else "0" * 64  # Genesis hash


def append_audit(
    db: Session,
    tenant_id: str,
    actor_id: str,
    correlation_id: str,
    entity_type: str,
    entity_id: Optional[str],
    action: str,
    payload: dict,
    metadata: dict,
) -> str:
    """Append an entry to the audit chain. Returns the new chain_hash."""
    now_str = datetime.now(timezone.utc).isoformat()
    prev_hash = get_prev_chain_hash(db, tenant_id)
    payload_hash = compute_payload_hash(payload)
    chain_hash = compute_chain_hash(prev_hash, action, payload_hash, actor_id, now_str)

    entry = AuditChainEntry(
        tenant_id=tenant_id,
        actor_id=uuid.UUID(actor_id),
        correlation_id=uuid.UUID(correlation_id),
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        action=action,
        after_hash=payload_hash,
        chain_hash=chain_hash,
        metadata_=metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    return chain_hash


# --- Idempotency ---

def filter_already_processed(
    db: Session, tenant_id: str, event_ids: list[str]
) -> set[str]:
    """Return set of event_ids that have already been processed."""
    if not event_ids:
        return set()

    # Use ORM query to avoid raw SQL array casting issues
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    uuid_list = [uuid.UUID(eid) for eid in event_ids]
    results = (
        db.query(SyncProcessedEvent.event_id)
        .filter(
            SyncProcessedEvent.tenant_id == tenant_id,
            SyncProcessedEvent.event_id.in_(uuid_list),
            SyncProcessedEvent.status == "COMMITTED",
        )
        .all()
    )
    return {str(r[0]) for r in results}


# --- Dependency Validation ---

def upsert_processed_event_record(
    db: Session,
    tenant_id: str,
    actor_id: str,
    event: SyncEvent,
    status: str,
    server_version: Optional[int] = None,
) -> SyncProcessedEvent:
    """Create or update the idempotency row for this event.

    DEPENDENCY_MISSING events are retryable; when the client resubmits the same
    event after dependencies exist, this lets the row advance to COMMITTED
    instead of colliding on the event_id primary key.
    """
    event_uuid = uuid.UUID(str(event.event_id))
    record = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.tenant_id == tenant_id,
        SyncProcessedEvent.event_id == event_uuid,
    ).first()

    if not record:
        record = SyncProcessedEvent(event_id=event_uuid, tenant_id=tenant_id)
        db.add(record)

    record.actor_id = uuid.UUID(actor_id)
    record.entity_type = event.entity_type
    record.entity_id = uuid.UUID(event.entity_id) if event.entity_id else None
    record.operation = event.operation
    record.server_version = server_version if server_version is not None else event.client_version
    record.status = status
    record.processed_at = datetime.now(timezone.utc)
    return record


def validate_dependencies(
    db: Session, tenant_id: str, dependency_ids: list[str]
) -> list[str]:
    """Check which dependency_ids are missing from processed events.

    Per sync-engine-contract §4: dependency skip does NOT count as retry failure.
    Returns list of MISSING dependency event_ids.
    """
    if not dependency_ids:
        return []

    dependency_uuid_list = [uuid.UUID(str(dep)) for dep in dependency_ids]
    processed_rows = (
        db.query(SyncProcessedEvent.event_id, SyncProcessedEvent.entity_id)
        .filter(
            SyncProcessedEvent.tenant_id == tenant_id,
            SyncProcessedEvent.status == "COMMITTED",
            (
                SyncProcessedEvent.event_id.in_(dependency_uuid_list)
                | SyncProcessedEvent.entity_id.in_(dependency_uuid_list)
            ),
        )
        .all()
    )
    processed = set()
    for event_id, entity_id in processed_rows:
        processed.add(str(event_id))
        if entity_id:
            processed.add(str(entity_id))

    return [d for d in dependency_ids if d not in processed]


# --- Conflict Detection ---

def detect_conflict(
    db: Session,
    tenant_id: str,
    event: SyncEvent,
) -> Optional[dict]:
    """Detect if an event conflicts with current server state.

    Returns conflict info dict if conflict detected, None if safe to commit.

    Per ADR-007:
    - VERSION_MISMATCH: client version < server version
    - GEO_OVERLAP: parcel geometry overlaps >5% (stub until parcels exist)
    - WORKFLOW_INVALID: stage transition violates lifecycle template
    """
    # Check if entity already exists with higher version
    if event.operation == "UPDATE" and event.entity_id:
        existing = db.execute(
            text("""
                SELECT server_version, status FROM sync_processed_events
                WHERE tenant_id = :tenant_id
                AND entity_id = :entity_id
                AND entity_type = :entity_type
                AND status = 'COMMITTED'
                ORDER BY processed_at DESC LIMIT 1
            """),
            {
                "tenant_id": tenant_id,
                "entity_id": event.entity_id,
                "entity_type": event.entity_type,
            },
        ).fetchone()

        if existing and existing[0] > event.client_version:
            return {
                "conflict_type": "VERSION_MISMATCH",
                "resolution_strategy": "MANUAL_REVIEW",
                "server_version": existing[0],
                "client_version": event.client_version,
            }

    # Workflow validation for crop_cycle stage transitions
    if event.entity_type in ("crop_stage", "crop_cycle") and event.operation == "UPDATE":
        conflict = validate_workflow_transition(db, tenant_id, event)
        if conflict:
            return conflict

    # GEO_OVERLAP detection (stub — will be implemented when parcel geometry exists)
    # if event.entity_type == "parcel" and event.operation in ("CREATE", "UPDATE"):
    #     conflict = detect_geo_overlap(db, tenant_id, event)
    #     if conflict:
    #         return conflict

    return None


def validate_workflow_transition(
    db: Session, tenant_id: str, event: SyncEvent
) -> Optional[dict]:
    """Validate stage transition against lifecycle template.

    Never hardcodes stage names — always loads from crop_lifecycle_templates.
    """
    payload = event.payload
    target_stage_code = payload.get("stage_code")
    template_id = payload.get("lifecycle_template_id")

    if not target_stage_code or not template_id:
        return None  # Can't validate without these — allow through

    # Load template stages
    from app.modules.master_data.models import CropLifecycleTemplate
    template = (
        db.query(CropLifecycleTemplate)
        .filter(
            CropLifecycleTemplate.id == uuid.UUID(template_id),
            CropLifecycleTemplate.is_active == True,
        )
        .first()
    )

    if not template:
        return None  # Template not found — allow through (may be tenant-custom)

    stages = template.stages
    valid_codes = {s["code"] for s in stages if isinstance(s, dict)}

    if target_stage_code not in valid_codes:
        return {
            "conflict_type": "WORKFLOW_INVALID",
            "resolution_strategy": "SERVER_AUTHORITY",
            "detail": f"Stage '{target_stage_code}' not in template",
            "valid_stages": sorted(valid_codes),
        }

    return None


# --- Batch Processing Pipeline ---

def process_sync_batch(
    db: Session,
    tenant_id: str,
    actor_id: str,
    events: list[dict],
) -> SyncResult:
    """Process a batch of sync events through the full pipeline.

    Steps:
    1. Idempotency filter (skip already-processed)
    2. Dependency validation (defer if deps missing)
    3. Conflict detection (route to conflict queue)
    4. Transactional commit (all-or-nothing per event)
    5. Audit chain (append immutable record)
    """
    result = SyncResult()
    correlation_id = str(uuid.uuid4())

    # Parse events
    parsed_events = [SyncEvent(e) for e in events]
    all_event_ids = [str(e.event_id) for e in parsed_events]

    # Step 1: Idempotency filter
    already_processed = filter_already_processed(db, tenant_id, all_event_ids)

    for event in parsed_events:
        event_id_str = str(event.event_id)

        # Skip already processed (idempotent)
        if event_id_str in already_processed:
            result.accepted.append(event_id_str)
            continue

        # Step 2: Dependency validation
        missing_deps = validate_dependencies(db, tenant_id, event.dependency_ids)
        if missing_deps:
            # Record as failed with DEPENDENCY_MISSING
            upsert_processed_event_record(
                db, tenant_id, actor_id, event, "DEPENDENCY_MISSING"
            )
            result.failed.append({
                "event_id": event_id_str,
                "error_code": "DEPENDENCY_MISSING",
                "message": f"Missing dependencies: {missing_deps}",
            })
            continue

        # Step 3: Conflict detection
        conflict = detect_conflict(db, tenant_id, event)
        if conflict:
            # Record processed event with CONFLICT status (flush to satisfy FK)
            record = upsert_processed_event_record(
                db, tenant_id, actor_id, event, "CONFLICT"
            )
            db.flush()  # Flush so FK constraint is satisfied

            # Insert conflict record
            conflict_record = SyncConflict(
                id=uuid.uuid4(),
                event_id=uuid.UUID(event_id_str),
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                entity_type=event.entity_type,
                entity_id=uuid.UUID(event.entity_id) if event.entity_id else uuid.uuid4(),
                conflict_type=conflict["conflict_type"],
                client_payload=event.payload,
                server_payload=conflict,
                resolution_strategy=conflict.get("resolution_strategy", "MANUAL_REVIEW"),
                status="PENDING_REVIEW",
                created_at=datetime.now(timezone.utc),
            )
            db.add(conflict_record)

            # Audit: conflict detected
            append_audit(
                db, tenant_id, actor_id, correlation_id,
                event.entity_type, event.entity_id,
                "SYNC_CONFLICT", event.payload,
                {**event.metadata, "conflict_type": conflict["conflict_type"]},
            )

            result.conflicts.append({
                "event_id": event_id_str,
                "conflict_type": conflict["conflict_type"],
                "resolution_strategy": conflict.get("resolution_strategy"),
                "detail": conflict.get("detail", ""),
            })
            continue

        # Step 4/5: Materialize, record idempotency, and audit as one per-event unit.
        try:
            with db.begin_nested():
                materialize_operational_event(db, tenant_id, actor_id, event)

                upsert_processed_event_record(
                    db, tenant_id, actor_id, event, "COMMITTED", event.client_version
                )

                append_audit(
                    db, tenant_id, actor_id, correlation_id,
                    event.entity_type, event.entity_id,
                    "SYNC_COMMIT", event.payload, event.metadata,
                )
                db.flush()
        except Exception as exc:
            result.failed.append({
                "event_id": event_id_str,
                "error_code": "MATERIALIZATION_FAILED",
                "message": str(exc),
            })
            continue

        result.accepted.append(event_id_str)

    # Commit entire batch
    db.commit()
    return result
