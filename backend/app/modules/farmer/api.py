"""Tenant, Project, Farmer, Parcel CRUD APIs.

POST /api/v1/tenants                    — Register a tenant (enterprise/FPO)
POST /api/v1/projects                   — Create a project within a tenant
POST /api/v1/projects/{id}/roles        — Assign user to project
GET  /api/v1/projects                   — List projects for tenant
POST /api/v1/farmers                    — Enroll a farmer (progressive)
GET  /api/v1/farmers                    — List farmers (tenant-scoped)
POST /api/v1/parcels                    — Register a parcel (GPS optional)
GET  /api/v1/parcels                    — List parcels (tenant-scoped)
PATCH /api/v1/parcels/{id}/geometry     — Add/update GPS data (progressive)
"""

import csv
import io
import json
import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.auth.models import TenantUserAccessAuditEvent, User
from app.modules.farmer.models import Tenant, Project, ProjectRole, Farmer, Parcel, FarmerProjectEnrollment, FarmerProjectEnrollmentImportBatch, ProjectAppConfigAuditEvent

router = APIRouter(prefix="/api/v1", tags=["operations"])


# --- Schemas ---

class TenantCreate(BaseModel):
    id: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=2, max_length=200)
    type: str = Field(default="ENTERPRISE")
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    type: str
    is_active: bool
    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    start_date: date
    end_date: date
    geography_scope: dict = Field(default_factory=dict)
    crop_scope: list[str] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    name: str
    start_date: date
    end_date: date
    status: str
    geography_scope: dict
    crop_scope: list
    class Config:
        from_attributes = True


class ProjectAppConfigPatch(BaseModel):
    branding: Optional[dict] = None
    localization: Optional[dict] = None
    units: Optional[dict] = None
    enabled_modules: Optional[list[str]] = None
    feature_flags: Optional[dict] = None
    self_service: Optional[dict] = None
    reason: Optional[str] = Field(None, min_length=3, max_length=500)


class ProjectAppConfigResponse(BaseModel):
    schema_version: str
    project_id: str
    tenant_id: str
    updated: bool
    config: dict
    edit_policy: dict
    applied_sections: list[str]
    blocked_sections: list[str] = Field(default_factory=list)
    message: Optional[str] = None


class TenantAppConfigResponse(BaseModel):
    schema_version: str
    tenant_id: str
    updated: bool
    config: dict
    applied_sections: list[str]
    message: Optional[str] = None


class RoleAssign(BaseModel):
    user_id: uuid.UUID
    role: str = Field(..., pattern=r"^(DEALER|FIELD_AGENT|AGRONOMIST|MANAGER|ENTERPRISE_ADMIN)$")
    territory_scope: dict = Field(default_factory=dict)
    reason: Optional[str] = None


class FarmerCreate(BaseModel):
    """Minimum for enrollment: mobile + village. Everything else is progressive."""
    mobile_number: str = Field(..., pattern=r"^\+91[6-9]\d{9}$")
    village_id: Optional[uuid.UUID] = None  # From geography DB (preferred)
    village_name_manual: Optional[str] = None  # If village not in DB (new settlement, etc.)
    primary_crop_code: Optional[str] = None
    crops_by_season: Optional[dict] = None  # {"KHARIF": ["RICE"], "RABI": ["WHEAT"]}
    display_name: Optional[str] = None
    father_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    aadhaar_number: Optional[str] = Field(None, pattern=r"^\d{12}$")
    total_land_area: Optional[float] = None
    total_land_unit: str = "BIGHA"
    language_preference: str = "hi"  # ISO 639-1
    enrollment_gps_lat: Optional[float] = None
    enrollment_gps_lng: Optional[float] = None


class FarmerResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    mobile_number: str
    village_id: uuid.UUID
    display_name: Optional[str] = None
    primary_crop_code: Optional[str] = None
    status: str
    class Config:
        from_attributes = True


class ParcelCreate(BaseModel):
    """Minimum: farmer_id + village + reported area. GPS is optional."""
    farmer_id: uuid.UUID
    village_id: Optional[uuid.UUID] = None  # From geography DB (preferred)
    village_name_manual: Optional[str] = None  # If village not in DB
    reported_area: float = Field(..., gt=0)
    reported_area_unit: str = "BIGHA"
    current_crop_code: Optional[str] = None
    soil_type_code: Optional[str] = None
    local_name: Optional[str] = None
    survey_number: Optional[str] = None
    ownership_type: str = "OWNED"  # OWNED, LEASED, SHARED, SHARECROP, FAMILY
    annual_rent: Optional[float] = None  # Required if LEASED
    annual_rent_currency: str = "INR"
    share_percentage: Optional[int] = Field(None, ge=1, le=100)  # For SHARED
    sharecrop_percentage: Optional[int] = Field(None, ge=1, le=100)  # For SHARECROP
    irrigation_source: Optional[str] = None
    # TUBEWELL_DIESEL, TUBEWELL_ELECTRIC, CANAL, PURCHASED_WATER, RAIN_FED, POND_TANK, RIVER_STREAM
    crops_by_season: Optional[dict] = None  # {"KHARIF": ["RICE"], "RABI": ["WHEAT"]}
    # Optional GPS (pin drop)
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None


class ParcelResponse(BaseModel):
    id: uuid.UUID
    farmer_id: uuid.UUID
    village_id: uuid.UUID
    reported_area: float
    reported_area_unit: str
    geometry_source: str
    current_crop_code: Optional[str] = None
    local_name: Optional[str] = None
    status: str
    class Config:
        from_attributes = True


class GeometryUpdate(BaseModel):
    """Progressive geometry update — add GPS data to existing parcel.

    Accepts 3 formats:
    - PIN_DROP: centroid_lat + centroid_lng (single point)
    - GPS_WALK: geojson with type "Polygon"
    - SATELLITE: geojson with type "Polygon" (from remote sensing)

    GeoJSON format: {"type": "Point|Polygon", "coordinates": ...}
    """
    geometry_source: str = Field(..., pattern=r"^(NONE|PIN_DROP|GPS_WALK|MANUAL_DRAW|SATELLITE)$")
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None
    geojson: Optional[dict] = None  # Standard GeoJSON: Point, MultiPoint, or Polygon
    accuracy_meters: Optional[float] = None


class FarmerProjectEnrollmentCreate(BaseModel):
    project_id: uuid.UUID
    enrollment_method: str = Field(default="ASSISTED", pattern=r"^(SELF|ASSISTED|BULK_IMPORT|WEB_ADMIN|PROJECT_INVITE|SYNC_MATERIALIZED)$")
    enrollment_source: Optional[str] = None
    enrollment_batch_id: Optional[str] = None
    status: str = Field(default="ACTIVE", pattern=r"^(PENDING|ACTIVE|COMPLETED|ARCHIVED|CANCELLED)$")
    parcel_ids: list[uuid.UUID] = Field(default_factory=list)
    assigned_user_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class FarmerProjectEnrollmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    farmer_id: uuid.UUID
    project_id: uuid.UUID
    project_name: Optional[str] = None
    project_status: Optional[str] = None
    enrollment_method: str
    enrollment_source: Optional[str] = None
    enrollment_batch_id: Optional[str] = None
    enrolled_by: Optional[uuid.UUID] = None
    status: str
    parcel_ids: list[str] = Field(default_factory=list)
    assigned_user_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DuplicateFarmerArchiveRequest(BaseModel):
    duplicate_farmer_ids: list[uuid.UUID] = Field(..., min_length=1)
    reason: Optional[str] = None
    force: bool = False


class FarmerProjectEnrollmentImportApplyRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class FarmerProjectEnrollmentStatusPatch(BaseModel):
    status: str = Field(..., pattern=r"^(COMPLETED|CANCELLED|ARCHIVED|ACTIVE|PENDING)$")
    reason: str = Field(..., min_length=3, max_length=500)


class ProjectEnrollmentLifecycleApplyRequest(BaseModel):
    target_status: str = Field(..., pattern=r"^(COMPLETED|CANCELLED|ARCHIVED|ACTIVE|PENDING)$")
    reason: str = Field(..., min_length=3, max_length=500)


PROJECT_APP_CONFIG_SECTIONS = {
    "branding",
    "localization",
    "units",
    "enabled_modules",
    "feature_flags",
    "self_service",
}
PROJECT_APP_CONFIG_LOCKED_SAFE_SECTIONS = {"branding"}


def _deep_merge_config(base: dict, override: dict) -> dict:
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _project_app_config_patch_payload(body: ProjectAppConfigPatch) -> dict:
    payload = body.model_dump(exclude_none=True)
    payload.pop("reason", None)
    return {key: value for key, value in payload.items() if key in PROJECT_APP_CONFIG_SECTIONS}


def normalize_mobile_number(mobile_number: str) -> str:
    """Normalize Indian mobile numbers for profile lookup.

    Android may have either +919900000001 or 9900000001 depending on which
    screen/local entity produced the value. Store and compare as +91XXXXXXXXXX.
    """
    value = (mobile_number or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("91") and len(value) == 12:
        value = f"+{value}"
    elif len(value) == 10 and value[0] in "6789":
        value = f"+91{value}"
    return value


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _iso_date(value):
    return value.isoformat() if value else None



def _validate_lng_lat(point: list, label: str) -> tuple[float, float]:
    if not isinstance(point, list) or len(point) < 2:
        raise HTTPException(400, f"{label} must be [longitude, latitude]")
    try:
        lng = float(point[0])
        lat = float(point[1])
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label} coordinates must be numeric")
    if not -180 <= lng <= 180:
        raise HTTPException(400, f"{label} longitude out of range")
    if not -90 <= lat <= 90:
        raise HTTPException(400, f"{label} latitude out of range")
    return lng, lat


def normalize_geojson_for_parcel(geojson: Optional[dict], geometry_source: str) -> tuple[Optional[dict], Optional[float], Optional[float]]:
    """Validate Android GeoJSON and return normalized geometry + centroid lat/lng.

    GeoJSON coordinates are [longitude, latitude]. For polygons, the first ring
    is closed automatically if Android omitted the final repeated point.
    """
    if not geojson:
        return None, None, None

    geometry_type = geojson.get("type")
    coordinates = geojson.get("coordinates")

    if geometry_type == "Point":
        lng, lat = _validate_lng_lat(coordinates, "Point")
        if geometry_source not in ("PIN_DROP", "GPS_WALK", "MANUAL_DRAW", "SATELLITE"):
            raise HTTPException(400, "Point GeoJSON requires a GPS geometry_source")
        return {"type": "Point", "coordinates": [lng, lat]}, lat, lng

    if geometry_type == "Polygon":
        if geometry_source not in ("GPS_WALK", "MANUAL_DRAW", "SATELLITE"):
            raise HTTPException(400, "Polygon GeoJSON requires GPS_WALK, MANUAL_DRAW, or SATELLITE geometry_source")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise HTTPException(400, "Polygon coordinates must contain at least one linear ring")

        normalized_rings = []
        for ring_index, ring in enumerate(coordinates):
            if not isinstance(ring, list):
                raise HTTPException(400, f"Polygon ring {ring_index} must be a list")
            normalized_ring = []
            for point_index, point in enumerate(ring):
                lng, lat = _validate_lng_lat(point, f"Polygon ring {ring_index} point {point_index}")
                normalized_ring.append([lng, lat])

            if len(normalized_ring) < 3:
                raise HTTPException(400, f"Polygon ring {ring_index} must have at least 3 distinct points")
            if normalized_ring[0] != normalized_ring[-1]:
                normalized_ring.append(normalized_ring[0])
            if len(normalized_ring) < 4:
                raise HTTPException(400, f"Polygon ring {ring_index} must have at least 4 coordinates including closure")
            normalized_rings.append(normalized_ring)

        return {"type": "Polygon", "coordinates": normalized_rings}, None, None

    raise HTTPException(400, "GeoJSON type must be Point or Polygon")


def _centroid_from_geojson(db: Session, normalized_geojson: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if normalized_geojson.get("type") != "Polygon":
        return None, None, None
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
    return (float(row.lat), float(row.lng), float(row.area_hectares)) if row else (None, None, None)


def _select_hydration_farmer(db: Session, tenant_id: str, mobile_number: str) -> tuple[Optional[Farmer], list[Farmer]]:
    normalized_mobile = normalize_mobile_number(mobile_number)
    candidates = (
        db.query(Farmer)
        .filter(
            Farmer.tenant_id == tenant_id,
            Farmer.mobile_number == normalized_mobile,
            Farmer.status != "ARCHIVED",
        )
        .all()
    )
    if not candidates:
        return None, []

    from app.modules.workflow.models import CropCycle

    scored = []
    for farmer in candidates:
        parcel_count = db.query(Parcel).filter(Parcel.farmer_id == farmer.id, Parcel.tenant_id == tenant_id).count()
        cycle_count = db.query(CropCycle).filter(CropCycle.farmer_id == farmer.id, CropCycle.tenant_id == tenant_id).count()
        active_rank = 1 if farmer.status == "ACTIVE" else 0
        updated_at = farmer.updated_at or farmer.created_at or datetime.min.replace(tzinfo=timezone.utc)
        scored.append(((active_rank, parcel_count, cycle_count, updated_at), farmer))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[0][1]
    duplicates = [farmer for _, farmer in scored[1:]]
    return selected, duplicates


def _farmer_payload(farmer: Farmer) -> dict:
    return {
        "id": str(farmer.id),
        "tenant_id": farmer.tenant_id,
        "project_id": str(farmer.project_id) if farmer.project_id else None,
        "user_id": str(farmer.user_id) if farmer.user_id else None,
        "mobile_number": farmer.mobile_number,
        "display_name": farmer.display_name,
        "father_name": farmer.father_name,
        "age": farmer.age,
        "gender": farmer.gender,
        "village_id": str(farmer.village_id) if farmer.village_id else None,
        "village_name_manual": farmer.village_name_manual,
        "primary_crop_code": farmer.primary_crop_code,
        "crops_by_season": farmer.crops_by_season or {},
        "total_land_area": _json_number(farmer.total_land_area),
        "total_land_unit": farmer.total_land_unit,
        "language_preference": farmer.language_preference,
        "status": farmer.status,
        "created_at": _iso_date(farmer.created_at),
        "updated_at": _iso_date(farmer.updated_at),
    }


def _parcel_geojson(db: Session, parcel: Parcel) -> Optional[dict]:
    row = db.execute(
        text("SELECT ST_AsGeoJSON(geometry) AS geojson FROM parcels WHERE id=:id AND tenant_id=:tenant_id"),
        {"id": str(parcel.id), "tenant_id": parcel.tenant_id},
    ).fetchone()
    if not row or not row.geojson:
        return None
    return json.loads(row.geojson)


def _parcel_payload(db: Session, parcel: Parcel) -> dict:
    geojson = _parcel_geojson(db, parcel)
    return {
        "id": str(parcel.id),
        "farmer_id": str(parcel.farmer_id),
        "tenant_id": parcel.tenant_id,
        "project_id": str(parcel.project_id) if parcel.project_id else None,
        "village_id": str(parcel.village_id) if parcel.village_id else None,
        "village_name_manual": parcel.village_name_manual,
        "reported_area": _json_number(parcel.reported_area),
        "reported_area_unit": parcel.reported_area_unit,
        "current_crop_code": parcel.current_crop_code,
        "soil_type_code": parcel.soil_type_code,
        "local_name": parcel.local_name,
        "survey_number": parcel.survey_number,
        "ownership_type": parcel.ownership_type,
        "annual_rent": _json_number(parcel.annual_rent),
        "annual_rent_currency": parcel.annual_rent_currency,
        "share_percentage": parcel.share_percentage,
        "sharecrop_percentage": parcel.sharecrop_percentage,
        "irrigation_source": parcel.irrigation_source,
        "crops_by_season": parcel.crops_by_season or {},
        "geometry_source": parcel.geometry_source,
        "centroid_lat": _json_number(parcel.centroid_lat),
        "centroid_lng": _json_number(parcel.centroid_lng),
        "computed_area_hectares": _json_number(parcel.computed_area_hectares),
        "geometry_accuracy_meters": _json_number(parcel.geometry_accuracy_meters),
        "geometry_captured_at": _iso_date(parcel.geometry_captured_at),
        "geojson": geojson,
        "geojson_type": geojson.get("type") if geojson else None,
        "status": parcel.status,
        "created_at": _iso_date(parcel.created_at),
        "updated_at": _iso_date(parcel.updated_at),
    }


def _soil_profile_payload(profile) -> dict:
    return {
        "id": str(profile.id),
        "parcel_id": str(profile.parcel_id),
        "farmer_id": str(profile.farmer_id),
        "soil_type_code": profile.soil_type_code,
        "soil_texture": profile.soil_texture,
        "soil_color": profile.soil_color,
        "test_date": _iso_date(profile.test_date),
        "lab_name": profile.lab_name,
        "shc_card_number": profile.shc_card_number,
        "nitrogen_n": _json_number(profile.nitrogen_n),
        "phosphorus_p": _json_number(profile.phosphorus_p),
        "potassium_k": _json_number(profile.potassium_k),
        "sulphur_s": _json_number(profile.sulphur_s),
        "zinc_zn": _json_number(profile.zinc_zn),
        "iron_fe": _json_number(profile.iron_fe),
        "copper_cu": _json_number(profile.copper_cu),
        "manganese_mn": _json_number(profile.manganese_mn),
        "boron_bo": _json_number(profile.boron_bo),
        "ph": _json_number(profile.ph),
        "ec": _json_number(profile.ec),
        "organic_carbon_oc": _json_number(profile.organic_carbon_oc),
        "ratings": profile.ratings or {},
        "recommendations": profile.recommendations or {},
        "data_source": profile.data_source,
        "notes": profile.notes,
        "created_at": _iso_date(profile.created_at),
        "updated_at": _iso_date(profile.updated_at),
    }


def _enrollment_payload(enrollment: FarmerProjectEnrollment, project: Optional[Project] = None) -> dict:
    return {
        "id": str(enrollment.id),
        "tenant_id": enrollment.tenant_id,
        "farmer_id": str(enrollment.farmer_id),
        "project_id": str(enrollment.project_id),
        "project_name": project.name if project else None,
        "project_status": project.status if project else None,
        "enrollment_method": enrollment.enrollment_method,
        "enrollment_source": enrollment.enrollment_source,
        "enrollment_batch_id": enrollment.enrollment_batch_id,
        "enrolled_by": str(enrollment.enrolled_by) if enrollment.enrolled_by else None,
        "status": enrollment.status,
        "parcel_ids": [str(value) for value in (enrollment.parcel_ids or [])],
        "assigned_user_ids": [str(value) for value in (enrollment.assigned_user_ids or [])],
        "metadata": enrollment.metadata_ or {},
        "notes": enrollment.notes,
        "created_at": _iso_date(enrollment.created_at),
        "updated_at": _iso_date(enrollment.updated_at),
    }


def _farmer_profile_completion(farmer: Farmer, parcel_count: int, soil_profile_count: int) -> dict:
    missing = []
    if not farmer.display_name:
        missing.append("display_name")
    if not farmer.village_id and not farmer.village_name_manual:
        missing.append("village")
    if parcel_count == 0:
        missing.append("parcel")
    return {
        "is_complete_for_home": len(missing) == 0,
        "missing_fields": missing,
        "parcel_count": parcel_count,
        "soil_profile_count": soil_profile_count,
    }


def _launch_navigation_decision(farmer: Farmer, enrollments: list[FarmerProjectEnrollment], completion: dict) -> str:
    active_enrollments = [enrollment for enrollment in enrollments if enrollment.status == "ACTIVE"]
    if farmer.status not in {"ACTIVE", "PENDING"}:
        return "SHOW_REGISTRATION"
    if len(active_enrollments) > 1:
        return "SHOW_PROJECT_PICKER"
    if not completion["is_complete_for_home"]:
        return "SHOW_PROFILE_COMPLETION"
    return "SHOW_HOME"


def _farmer_context_payload(
    enrollments: list[FarmerProjectEnrollment],
    projects: dict[uuid.UUID, Project],
) -> dict:
    active_enrollments = [enrollment for enrollment in enrollments if enrollment.status == "ACTIVE"]
    completed_enrollments = [enrollment for enrollment in enrollments if enrollment.status == "COMPLETED"]
    selected_enrollment = active_enrollments[0] if len(active_enrollments) == 1 else None
    selected_project = projects.get(selected_enrollment.project_id) if selected_enrollment else None

    if len(active_enrollments) > 1:
        mode = "PROJECT_PICKER"
        reason = "MULTIPLE_ACTIVE_PROJECTS"
    elif selected_enrollment:
        mode = "PROJECT"
        reason = "ACTIVE_PROJECT_ENROLLMENT"
    elif completed_enrollments:
        mode = "SELF_SERVICE"
        reason = "NO_ACTIVE_PROJECT_AFTER_COMPLETED_PROJECT"
    else:
        mode = "SELF_SERVICE"
        reason = "NO_PROJECT_ENROLLMENT"

    return {
        "mode": mode,
        "reason": reason,
        "can_continue_independently": len(active_enrollments) == 0,
        "active_project_count": len(active_enrollments),
        "completed_project_count": len(completed_enrollments),
        "project_selection_required": len(active_enrollments) > 1,
        "active_project_candidate": None if not selected_enrollment else _enrollment_payload(selected_enrollment, selected_project),
        "notes": [
            "Farmer identity is independent from project participation.",
            "When no ACTIVE project enrollment exists, Android should continue in SELF_SERVICE context rather than sending the farmer back to registration.",
            "If a company later enrolls the same farmer, keep the farmer_id/local linkage and add or update a project_enrollment row.",
        ],
    }


def _build_profile_hydration_response(db: Session, tenant_id: str, farmer: Farmer, duplicate_farmers: list[Farmer]) -> dict:
    from app.modules.farmer.soil_profile import SoilProfile
    from app.modules.master_data.models import Crop
    from app.modules.workflow.api import build_crop_cycle_response
    from app.modules.workflow.models import CropCycle, CropStageInstance

    parcels = (
        db.query(Parcel)
        .filter(Parcel.tenant_id == tenant_id, Parcel.farmer_id == farmer.id)
        .order_by(Parcel.created_at, Parcel.id)
        .all()
    )
    soil_profiles = (
        db.query(SoilProfile)
        .filter(SoilProfile.tenant_id == tenant_id, SoilProfile.farmer_id == farmer.id)
        .order_by(SoilProfile.test_date.desc(), SoilProfile.updated_at.desc())
        .all()
    )
    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.tenant_id == tenant_id, CropCycle.farmer_id == farmer.id)
        .order_by(CropCycle.updated_at.desc(), CropCycle.created_at.desc())
        .all()
    )
    project_enrollments = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer.id,
            FarmerProjectEnrollment.status != "ARCHIVED",
        )
        .order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc())
        .all()
    )
    enrollment_project_ids = [enrollment.project_id for enrollment in project_enrollments]
    enrollment_projects = {
        project.id: project
        for project in db.query(Project).filter(Project.id.in_(enrollment_project_ids)).all()
    } if enrollment_project_ids else {}

    crop_codes = sorted({cycle.crop_code for cycle in cycles if cycle.crop_code})
    crop_names = {
        crop.code: crop.canonical_name
        for crop in db.query(Crop).filter(Crop.code.in_(crop_codes)).all()
    } if crop_codes else {}

    cycle_payloads = []
    for cycle in cycles:
        stages = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == cycle.id,
                CropStageInstance.tenant_id == tenant_id,
            )
            .order_by(CropStageInstance.stage_order)
            .all()
        )
        cycle_payloads.append(build_crop_cycle_response(cycle, stages, crop_names.get(cycle.crop_code)))

    active_statuses = {"PLANNED", "ACTIVE", "PARTIALLY_TRACKED"}
    completed_statuses = {"COMPLETED"}

    duplicate_payloads = []
    for duplicate in duplicate_farmers:
        duplicate_payloads.append({
            "id": str(duplicate.id),
            "mobile_number": duplicate.mobile_number,
            "display_name": duplicate.display_name,
            "status": duplicate.status,
            "parcel_count": db.query(Parcel).filter(Parcel.tenant_id == tenant_id, Parcel.farmer_id == duplicate.id).count(),
            "crop_cycle_count": db.query(CropCycle).filter(CropCycle.tenant_id == tenant_id, CropCycle.farmer_id == duplicate.id).count(),
            "created_at": _iso_date(duplicate.created_at),
            "updated_at": _iso_date(duplicate.updated_at),
        })

    return {
        "schema_version": "profile_hydration.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_exists": True,
        "tenant_id": tenant_id,
        "farmer": _farmer_payload(farmer),
        "parcels": [_parcel_payload(db, parcel) for parcel in parcels],
        "soil_profiles": [_soil_profile_payload(profile) for profile in soil_profiles],
        "project_enrollments": [_enrollment_payload(enrollment, enrollment_projects.get(enrollment.project_id)) for enrollment in project_enrollments],
        "farmer_context": _farmer_context_payload(project_enrollments, enrollment_projects),
        "crop_cycles": {
            "active": [cycle for cycle in cycle_payloads if cycle["status"] in active_statuses],
            "completed": [cycle for cycle in cycle_payloads if cycle["status"] in completed_statuses],
            "other": [cycle for cycle in cycle_payloads if cycle["status"] not in active_statuses and cycle["status"] not in completed_statuses and cycle["status"] != "ARCHIVED"],
        },
        "summary": {
            "parcel_count": len(parcels),
            "soil_profile_count": len(soil_profiles),
            "project_enrollment_count": len(project_enrollments),
            "active_project_enrollment_count": len([enrollment for enrollment in project_enrollments if enrollment.status == "ACTIVE"]),
            "active_crop_cycle_count": len([cycle for cycle in cycle_payloads if cycle["status"] in active_statuses]),
            "completed_crop_cycle_count": len([cycle for cycle in cycle_payloads if cycle["status"] in completed_statuses]),
            "archived_crop_cycle_count": len([cycle for cycle in cycle_payloads if cycle["status"] == "ARCHIVED"]),
            "duplicate_farmer_count": len(duplicate_farmers),
        },
        "duplicates": duplicate_payloads,
        "geometry_contract": {
            "pin_drop": "PIN_DROP returns geometry_source plus centroid_lat/centroid_lng. geojson is null for MVP because backend does not store Point geometry in PostGIS.",
            "gps_walk": "GPS_WALK returns geometry_source, centroid_lat/centroid_lng, computed_area_hectares, and Polygon GeoJSON when captured.",
        },
    }


ENROLLMENT_CSV_COLUMNS = [
    "farmer_id",
    "mobile_number",
    "display_name",
    "father_name",
    "village_name_manual",
    "language_preference",
    "primary_crop_code",
    "parcel_ids",
    "assigned_user_ids",
    "enrollment_status",
    "enrollment_source",
    "notes",
    "metadata_json",
]
ENROLLMENT_CSV_REQUIRED_COLUMNS = {"mobile_number", "display_name", "village_name_manual"}
ENROLLMENT_CSV_MAX_FILE_BYTES = 2 * 1024 * 1024
ENROLLMENT_CSV_MAX_ROWS = 5000
ENROLLMENT_VALID_STATUSES = {"PENDING", "ACTIVE", "COMPLETED", "ARCHIVED", "CANCELLED"}


def _csv_response(rows: list[dict], fieldnames: list[str], file_name: str) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def _split_uuid_list(raw: Optional[str], field: str, errors: list[dict]) -> list[str]:
    values = [value.strip() for value in (raw or "").replace(",", "|").split("|") if value.strip()]
    normalized = []
    for value in values:
        try:
            normalized.append(str(uuid.UUID(value)))
        except ValueError:
            errors.append({"field": field, "code": "INVALID_UUID", "message": f"Invalid UUID: {value}"})
    return normalized


def _parse_metadata_json(raw: Optional[str], errors: list[dict]) -> dict:
    value = (raw or "").strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        errors.append({"field": "metadata_json", "code": "INVALID_JSON", "message": "metadata_json must be valid JSON"})
        return {}
    if not isinstance(parsed, dict):
        errors.append({"field": "metadata_json", "code": "INVALID_JSON_TYPE", "message": "metadata_json must be a JSON object"})
        return {}
    return parsed


def _enrollment_import_batch_payload(batch: FarmerProjectEnrollmentImportBatch) -> dict:
    report = batch.validation_report or {}
    return {
        "batch_id": str(batch.id),
        "project_id": str(batch.project_id),
        "file_name": batch.file_name,
        "status": batch.status,
        "can_apply": batch.status == "VALIDATED" and report.get("can_apply", False) and batch.expires_at > datetime.now(timezone.utc),
        "expires_at": batch.expires_at.isoformat(),
        "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
        "created_at": batch.created_at.isoformat(),
        "report": report,
    }


async def _read_enrollment_csv_upload(file: UploadFile) -> str:
    content = await file.read(ENROLLMENT_CSV_MAX_FILE_BYTES + 1)
    if len(content) > ENROLLMENT_CSV_MAX_FILE_BYTES:
        raise HTTPException(413, "CSV file exceeds 2 MB")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")


def _normalize_enrollment_csv_row(raw: dict[str, str], row_number: int, existing_by_mobile: dict[str, Farmer]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    mobile_raw = (raw.get("mobile_number") or "").strip()
    try:
        mobile_number = normalize_mobile_number(mobile_raw)
    except Exception:
        mobile_number = mobile_raw
        errors.append({"field": "mobile_number", "code": "INVALID_MOBILE", "message": "Use a 10-digit Indian mobile or +91 format"})

    farmer_id_raw = (raw.get("farmer_id") or "").strip()
    farmer_id = None
    if farmer_id_raw:
        try:
            farmer_id = str(uuid.UUID(farmer_id_raw))
        except ValueError:
            errors.append({"field": "farmer_id", "code": "INVALID_UUID", "message": "farmer_id must be a UUID"})

    display_name = (raw.get("display_name") or "").strip()
    village_name_manual = (raw.get("village_name_manual") or "").strip()
    status = ((raw.get("enrollment_status") or "ACTIVE").strip() or "ACTIVE").upper()
    if not display_name:
        errors.append({"field": "display_name", "code": "REQUIRED", "message": "display_name is required"})
    if not village_name_manual:
        errors.append({"field": "village_name_manual", "code": "REQUIRED", "message": "village_name_manual is required"})
    if status not in ENROLLMENT_VALID_STATUSES:
        errors.append({"field": "enrollment_status", "code": "INVALID_STATUS", "message": "Use PENDING, ACTIVE, COMPLETED, ARCHIVED, or CANCELLED"})

    parcel_ids = _split_uuid_list(raw.get("parcel_ids"), "parcel_ids", errors)
    assigned_user_ids = _split_uuid_list(raw.get("assigned_user_ids"), "assigned_user_ids", errors)
    metadata = _parse_metadata_json(raw.get("metadata_json"), errors)
    action = "INVALID" if errors else ("UPDATE" if mobile_number in existing_by_mobile else "CREATE")
    normalized = {
        "farmer_id": farmer_id,
        "mobile_number": mobile_number,
        "display_name": display_name,
        "father_name": (raw.get("father_name") or "").strip() or None,
        "village_name_manual": village_name_manual,
        "language_preference": (raw.get("language_preference") or "hi").strip() or "hi",
        "primary_crop_code": (raw.get("primary_crop_code") or "").strip().upper() or None,
        "parcel_ids": parcel_ids,
        "assigned_user_ids": assigned_user_ids,
        "enrollment_status": status,
        "enrollment_source": (raw.get("enrollment_source") or "bulk_csv").strip() or "bulk_csv",
        "notes": (raw.get("notes") or "").strip() or None,
        "metadata": metadata,
    }
    return {"row_number": row_number, "mobile_number": mobile_number, "action": action, "errors": errors, "warnings": warnings, "normalized": normalized}


def _enrollment_validation_report(rows: list[dict], file_name: str, project_id: uuid.UUID) -> dict:
    summary = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "invalid": 0, "warnings": 0, "errors": 0}
    for row in rows:
        summary["warnings"] += len(row["warnings"])
        summary["errors"] += len(row["errors"])
        if row["action"] == "CREATE":
            summary["create"] += 1
        elif row["action"] == "UPDATE":
            summary["update"] += 1
        elif row["action"] == "INVALID":
            summary["invalid"] += 1
        else:
            summary["unchanged"] += 1
    can_apply = summary["errors"] == 0
    return {
        "schema_version": "project_enrollment_csv_validation.v1",
        "mode": "VALIDATE_ONLY",
        "project_id": str(project_id),
        "file_name": file_name,
        "can_apply": can_apply,
        "summary": summary,
        "rows": rows,
        "message": "Validation passed. Enrollment CSV can be applied." if can_apply else "Validation failed. Fix errors and upload again.",
    }


# --- Tenant Endpoints ---

@router.post("/tenants", response_model=TenantResponse, status_code=201)
def create_tenant(body: TenantCreate, db: Session = Depends(get_db)):
    """Register a new tenant (enterprise, FPO, insurer)."""
    existing = db.query(Tenant).filter(Tenant.id == body.id).first()
    if existing:
        raise HTTPException(409, "Tenant ID already exists")

    tenant = Tenant(
        id=body.id,
        name=body.name,
        type=body.type,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(tenant)
    db.commit()
    return tenant


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(
    db: Session = Depends(get_db),
):
    """List all active tenants. Used by super-admin for platform management."""
    return (
        db.query(Tenant)
        .filter(Tenant.is_active == True)
        .order_by(Tenant.name)
        .all()
    )


@router.patch("/tenants/{tenant_id}/app-config", response_model=TenantAppConfigResponse)
def update_tenant_app_config(
    tenant_id: str,
    body: ProjectAppConfigPatch,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    """Update tenant-level runtime app configuration.

    Tenant app-config defines white-label/default behavior. Project app-config
    can still override tenant defaults through /projects/{project_id}/app-config.
    """
    if tenant_id != x_tenant_id:
        raise HTTPException(403, {
            "error": "TENANT_ID_MISMATCH",
            "message": "Path tenant_id must match X-Tenant-ID.",
        })
    if principal.role != "ENTERPRISE_ADMIN":
        raise HTTPException(403, {
            "error": "ENTERPRISE_ADMIN_REQUIRED",
            "message": "Only enterprise admins can update tenant app-config.",
            "current_role": principal.role,
        })

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    patch_payload = _project_app_config_patch_payload(body)
    if not patch_payload:
        raise HTTPException(400, "At least one app-config section must be provided")

    tenant.config = _deep_merge_config(tenant.config or {}, patch_payload)
    tenant.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tenant)

    return {
        "schema_version": "tenant_app_config.v1",
        "tenant_id": tenant_id,
        "updated": True,
        "config": tenant.config or {},
        "applied_sections": sorted(patch_payload.keys()),
        "message": "Tenant app-config updated.",
    }


# --- Project Endpoints ---

def _project_edit_policy(db: Session, project: Project, tenant_id: str) -> dict:
    from app.modules.workflow.models import CropCycle

    legacy_farmer_ids = {
        row[0]
        for row in db.query(Farmer.id)
        .filter(
            Farmer.tenant_id == tenant_id,
            Farmer.project_id == project.id,
            Farmer.status != "ARCHIVED",
        )
        .all()
    }
    enrolled_farmer_ids = {
        row[0]
        for row in db.query(FarmerProjectEnrollment.farmer_id)
        .filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.project_id == project.id,
            FarmerProjectEnrollment.status != "ARCHIVED",
        )
        .all()
    }
    farmer_count = len(legacy_farmer_ids | enrolled_farmer_ids)
    parcel_count = db.query(Parcel).filter(
        Parcel.tenant_id == tenant_id,
        Parcel.project_id == project.id,
        Parcel.status != "ARCHIVED",
    ).count()
    crop_cycle_count = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.project_id == project.id,
        CropCycle.status != "ARCHIVED",
    ).count()

    locked_reasons = []
    if project.status in {"ACTIVE", "COMPLETED", "ARCHIVED"}:
        locked_reasons.append({
            "code": f"PROJECT_{project.status}",
            "message": f"Project status is {project.status}; core configuration edits are locked.",
        })
    if farmer_count > 0:
        locked_reasons.append({"code": "FARMERS_ENROLLED", "message": "Farmers are already enrolled in this project."})
    if parcel_count > 0:
        locked_reasons.append({"code": "PARCELS_REGISTERED", "message": "Land parcels are already linked to this project."})
    if crop_cycle_count > 0:
        locked_reasons.append({"code": "CROP_CYCLES_STARTED", "message": "Crop cycles already exist for this project."})

    can_edit_core_config = len(locked_reasons) == 0
    return {
        "schema_version": "project_edit_policy.v1",
        "project_id": str(project.id),
        "tenant_id": tenant_id,
        "project_status": project.status,
        "can_edit_core_config": can_edit_core_config,
        "lock_state": "OPEN" if can_edit_core_config else "LOCKED",
        "locked_fields": [] if can_edit_core_config else [
            "start_date",
            "end_date",
            "geography_scope",
            "crop_scope",
            "workflow_enablements",
            "workflow_template_assignments",
        ],
        "allowed_changes": ["name", "description"] if not can_edit_core_config else [
            "name",
            "description",
            "start_date",
            "end_date",
            "geography_scope",
            "crop_scope",
            "workflow_enablements",
            "workflow_template_assignments",
        ],
        "counts": {
            "farmers": farmer_count,
            "parcels": parcel_count,
            "crop_cycles": crop_cycle_count,
        },
        "reasons": locked_reasons,
    }


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Create a project within a tenant."""
    tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    project = Project(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        name=body.name,
        description=body.description,
        start_date=body.start_date,
        end_date=body.end_date,
        geography_scope=body.geography_scope,
        crop_scope=body.crop_scope,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List projects for a tenant."""
    query = db.query(Project).filter(Project.tenant_id == x_tenant_id)
    if status:
        query = query.filter(Project.status == status)
    return query.order_by(Project.start_date.desc()).all()


@router.get("/projects/{project_id}/edit-policy")
def get_project_edit_policy(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return whether core project configuration can still be edited safely."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return _project_edit_policy(db, project, x_tenant_id)


@router.patch("/projects/{project_id}/app-config", response_model=ProjectAppConfigResponse)
def update_project_app_config(
    project_id: uuid.UUID,
    body: ProjectAppConfigPatch,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)),
):
    """Safely update runtime app/project configuration.

    Planned empty projects can update all supported app-config sections. Once a
    project is active or farmers/parcels/crop cycles exist, only display-level
    branding changes are allowed; risky behavior-changing sections are blocked.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    patch_payload = _project_app_config_patch_payload(body)
    if not patch_payload:
        raise HTTPException(400, "At least one app-config section must be provided")

    edit_policy = _project_edit_policy(db, project, x_tenant_id)
    requested_sections = set(patch_payload.keys())
    blocked_sections = []
    if not edit_policy["can_edit_core_config"]:
        blocked_sections = sorted(requested_sections - PROJECT_APP_CONFIG_LOCKED_SAFE_SECTIONS)
        if blocked_sections:
            raise HTTPException(409, {
                "error": "PROJECT_APP_CONFIG_LOCKED",
                "message": "Project has enrolled/runtime data; only branding app-config changes are allowed.",
                "blocked_sections": blocked_sections,
                "allowed_sections": sorted(PROJECT_APP_CONFIG_LOCKED_SAFE_SECTIONS),
                "edit_policy": edit_policy,
            })

    before_config = project.config or {}
    project.config = _deep_merge_config(before_config, patch_payload)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)

    return {
        "schema_version": "project_app_config.v1",
        "project_id": str(project.id),
        "tenant_id": x_tenant_id,
        "updated": True,
        "config": project.config or {},
        "edit_policy": _project_edit_policy(db, project, x_tenant_id),
        "applied_sections": sorted(requested_sections),
        "blocked_sections": [],
        "message": "Project app-config updated.",
    }


@router.post("/projects/{project_id}/roles", status_code=201)
def assign_role(
    project_id: uuid.UUID,
    body: RoleAssign,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    """Assign a user to a project with a role and territory scope."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.tenant_id == x_tenant_id
    ).first()
    if not project:
        raise HTTPException(404, "Project not found")

    user = db.query(User).filter(
        User.id == body.user_id,
        User.tenant_id == x_tenant_id,
        User.is_active == True,
    ).first()
    if not user:
        raise HTTPException(404, "Tenant user not found")
    role = db.query(ProjectRole).filter(
        ProjectRole.project_id == project_id,
        ProjectRole.user_id == body.user_id,
    ).first()
    before = None if not role else {
        "role": role.role,
        "territory_scope": role.territory_scope or {},
        "is_active": role.is_active,
    }
    if not role:
        role = ProjectRole(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=body.user_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(role)
    role.role = body.role
    role.territory_scope = body.territory_scope
    role.is_active = True
    role.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.add(TenantUserAccessAuditEvent(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        target_user_id=body.user_id,
        actor_id=principal.user_id,
        project_id=project_id,
        action="ASSIGN_PROJECT_ACCESS" if before is None else "CHANGE_PROJECT_ACCESS",
        before_payload=before,
        after_payload={
            "role": role.role,
            "territory_scope": role.territory_scope or {},
            "is_active": role.is_active,
        },
        reason=body.reason or "Legacy project role assignment API",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"status": "assigned", "role": body.role, "project_id": str(project_id)}


# --- Farmer Endpoints ---

@router.post("/farmers", response_model=FarmerResponse, status_code=201)
def enroll_farmer(
    body: FarmerCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Enroll a farmer (progressive — only mobile + village required)."""
    # Validate: at least one of village_id or village_name_manual must be provided
    if not body.village_id and not body.village_name_manual:
        raise HTTPException(400, "Either village_id or village_name_manual is required")

    normalized_mobile = normalize_mobile_number(body.mobile_number)
    existing_farmer = (
        db.query(Farmer)
        .filter(
            Farmer.tenant_id == x_tenant_id,
            Farmer.mobile_number == normalized_mobile,
            Farmer.status != "INACTIVE",
        )
        .order_by(Farmer.updated_at.desc(), Farmer.created_at.desc())
        .first()
    )
    if existing_farmer:
        raise HTTPException(
            409,
            {
                "message": "Farmer profile already exists for this mobile number",
                "farmer_id": str(existing_farmer.id),
                "hydrate_endpoint": f"/api/v1/farmers/by-mobile/{normalized_mobile}",
            },
        )

    farmer = Farmer(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        mobile_number=normalized_mobile,
        village_id=body.village_id,  # Can be None if manual village
        village_name_manual=body.village_name_manual,
        primary_crop_code=body.primary_crop_code,
        crops_by_season=body.crops_by_season or {},
        display_name=body.display_name,
        father_name=body.father_name,
        age=body.age,
        gender=body.gender,
        aadhaar_number=body.aadhaar_number,
        total_land_area=body.total_land_area,
        total_land_unit=body.total_land_unit,
        language_preference=body.language_preference,
        enrolled_by=uuid.UUID(x_actor_id),
        enrollment_gps_lat=body.enrollment_gps_lat,
        enrollment_gps_lng=body.enrollment_gps_lng,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return farmer


@router.get("/farmers", response_model=list[FarmerResponse])
def list_farmers(
    village_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query("ACTIVE"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List farmers for a tenant, optionally filtered by village."""
    query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id)
    if village_id:
        query = query.filter(Farmer.village_id == village_id)
    if status:
        query = query.filter(Farmer.status == status)
    return query.offset(offset).limit(limit).all()


# --- Farmer Project Enrollment Endpoints ---

@router.get("/projects/{project_id}/farmer-enrollments/csv/template")
def download_project_enrollment_csv_template(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW, project_scoped=True)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return _csv_response([
        {
            "farmer_id": "",
            "mobile_number": "9900000001",
            "display_name": "Example Farmer",
            "father_name": "Example Parent",
            "village_name_manual": "Example Village",
            "language_preference": "hi",
            "primary_crop_code": "RICE",
            "parcel_ids": "",
            "assigned_user_ids": "",
            "enrollment_status": "ACTIVE",
            "enrollment_source": "bulk_csv",
            "notes": "Initial project enrollment",
            "metadata_json": "{}",
        }
    ], ENROLLMENT_CSV_COLUMNS, "agri-os-project-enrollment-template.csv")


@router.post("/projects/{project_id}/farmer-enrollments/csv/validate")
async def validate_project_enrollment_csv(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT, project_scoped=True)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    text = await _read_enrollment_csv_upload(file)
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = sorted(ENROLLMENT_CSV_REQUIRED_COLUMNS - headers)
    if missing:
        raise HTTPException(400, {"error": "MISSING_COLUMNS", "columns": missing})
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(400, "CSV contains no data rows")
    if len(raw_rows) > ENROLLMENT_CSV_MAX_ROWS:
        raise HTTPException(413, "CSV exceeds 5000 rows")

    existing_by_mobile = {
        row.mobile_number: row
        for row in db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id).all()
    }
    rows = [_normalize_enrollment_csv_row(raw, index, existing_by_mobile) for index, raw in enumerate(raw_rows, start=2)]
    seen_mobile: set[str] = set()
    for row in rows:
        mobile = row["mobile_number"]
        if mobile in seen_mobile:
            row["errors"].append({"field": "mobile_number", "code": "DUPLICATE_MOBILE_IN_FILE", "message": f"Mobile also appears earlier in this file: {mobile}"})
            row["action"] = "INVALID"
        seen_mobile.add(mobile)

    report = _enrollment_validation_report(rows, file.filename or "project-enrollments.csv", project_id)
    now = datetime.now(timezone.utc)
    batch = FarmerProjectEnrollmentImportBatch(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=project_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "project-enrollments.csv")[:255],
        status="VALIDATED" if report["can_apply"] else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    return _enrollment_import_batch_payload(batch)


@router.get("/projects/{project_id}/farmer-enrollments/csv/imports")
def list_project_enrollment_imports(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW, project_scoped=True)),
):
    query = db.query(FarmerProjectEnrollmentImportBatch).filter(
        FarmerProjectEnrollmentImportBatch.tenant_id == x_tenant_id,
        FarmerProjectEnrollmentImportBatch.project_id == project_id,
        FarmerProjectEnrollmentImportBatch.is_active == True,
    )
    if status:
        query = query.filter(FarmerProjectEnrollmentImportBatch.status == status.upper())
    rows = query.order_by(FarmerProjectEnrollmentImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "project_enrollment_imports.v1",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "status": status.upper() if status else None,
        "count": len(rows),
        "imports": [_enrollment_import_batch_payload(row) for row in rows],
    }


@router.post("/projects/{project_id}/farmer-enrollments/csv/imports/{batch_id}/apply")
def apply_project_enrollment_import(
    project_id: uuid.UUID,
    batch_id: uuid.UUID,
    body: FarmerProjectEnrollmentImportApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT, project_scoped=True)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    batch = db.query(FarmerProjectEnrollmentImportBatch).filter(
        FarmerProjectEnrollmentImportBatch.id == batch_id,
        FarmerProjectEnrollmentImportBatch.tenant_id == x_tenant_id,
        FarmerProjectEnrollmentImportBatch.project_id == project_id,
        FarmerProjectEnrollmentImportBatch.is_active == True,
    ).first()
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Import batch status is {batch.status}")
    now = datetime.now(timezone.utc)
    if batch.expires_at <= now:
        batch.status = "EXPIRED"
        batch.updated_at = now
        db.commit()
        raise HTTPException(409, "Import batch has expired; validate the CSV again")

    applied = {"farmers_created": 0, "farmers_updated": 0, "enrollments_created": 0, "enrollments_updated": 0}
    for row in batch.normalized_rows or []:
        farmer = None
        if row.get("farmer_id"):
            farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(row["farmer_id"]), Farmer.tenant_id == x_tenant_id).first()
            if not farmer:
                batch.status = "STALE"
                batch.updated_at = now
                db.commit()
                raise HTTPException(409, f"Farmer no longer exists: {row['farmer_id']}")
        if not farmer:
            farmer = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id, Farmer.mobile_number == row["mobile_number"]).first()
        if farmer:
            applied["farmers_updated"] += 1
            if row.get("display_name"):
                farmer.display_name = row["display_name"]
            if row.get("father_name"):
                farmer.father_name = row["father_name"]
            if row.get("village_name_manual"):
                farmer.village_name_manual = row["village_name_manual"]
            if row.get("primary_crop_code"):
                farmer.primary_crop_code = row["primary_crop_code"]
        else:
            farmer = Farmer(
                id=uuid.uuid4(),
                tenant_id=x_tenant_id,
                project_id=project_id,
                mobile_number=row["mobile_number"],
                display_name=row.get("display_name"),
                father_name=row.get("father_name"),
                village_name_manual=row.get("village_name_manual"),
                language_preference=row.get("language_preference") or "hi",
                primary_crop_code=row.get("primary_crop_code"),
                enrollment_method="BULK_IMPORT",
                enrolled_by=principal.user_id,
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
            db.add(farmer)
            db.flush()
            applied["farmers_created"] += 1
        farmer.updated_at = now

        enrollment = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer.id,
            FarmerProjectEnrollment.project_id == project_id,
        ).first()
        if enrollment:
            applied["enrollments_updated"] += 1
        else:
            enrollment = FarmerProjectEnrollment(
                id=uuid.uuid4(),
                tenant_id=x_tenant_id,
                farmer_id=farmer.id,
                project_id=project_id,
                created_at=now,
            )
            db.add(enrollment)
            applied["enrollments_created"] += 1
        enrollment.enrollment_method = "BULK_IMPORT"
        enrollment.enrollment_source = row.get("enrollment_source") or "bulk_csv"
        enrollment.enrollment_batch_id = str(batch.id)
        enrollment.enrolled_by = principal.user_id
        enrollment.status = row.get("enrollment_status") or "ACTIVE"
        enrollment.parcel_ids = row.get("parcel_ids") or []
        enrollment.assigned_user_ids = row.get("assigned_user_ids") or []
        enrollment.metadata_ = row.get("metadata") or {}
        enrollment.notes = row.get("notes") or body.reason
        enrollment.updated_at = now
        if farmer.project_id is None and enrollment.status in {"PENDING", "ACTIVE"}:
            farmer.project_id = project_id

    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = applied
    report["apply_reason"] = body.reason
    report["applied_by"] = str(principal.user_id)
    batch.validation_report = report
    db.commit()
    db.refresh(batch)
    return _enrollment_import_batch_payload(batch)


@router.post("/farmers/{farmer_id}/project-enrollments", response_model=FarmerProjectEnrollmentResponse, status_code=201)
def create_farmer_project_enrollment(
    farmer_id: uuid.UUID,
    body: FarmerProjectEnrollmentCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
):
    """Attach a farmer profile to a project without duplicating the farmer.

    Existing farmers.project_id is preserved as a legacy compatibility pointer.
    If it is empty, this endpoint backfills it with the first project enrollment.
    """
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    project = db.query(Project).filter(Project.id == body.project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    parcel_ids = [str(value) for value in body.parcel_ids]
    if parcel_ids:
        parcel_count = (
            db.query(Parcel)
            .filter(
                Parcel.tenant_id == x_tenant_id,
                Parcel.farmer_id == farmer_id,
                Parcel.id.in_([uuid.UUID(value) for value in parcel_ids]),
            )
            .count()
        )
        if parcel_count != len(parcel_ids):
            raise HTTPException(400, "All parcel_ids must belong to this farmer and tenant")

    enrollment = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.project_id == body.project_id,
        )
        .first()
    )
    if not enrollment:
        enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=x_tenant_id,
            farmer_id=farmer_id,
            project_id=body.project_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)

    enrollment.enrollment_method = body.enrollment_method
    enrollment.enrollment_source = body.enrollment_source
    enrollment.enrollment_batch_id = body.enrollment_batch_id
    enrollment.enrolled_by = uuid.UUID(x_actor_id) if x_actor_id else None
    enrollment.status = body.status
    enrollment.parcel_ids = parcel_ids
    enrollment.assigned_user_ids = [str(value) for value in body.assigned_user_ids]
    enrollment.metadata_ = body.metadata or {}
    enrollment.notes = body.notes
    enrollment.updated_at = datetime.now(timezone.utc)

    if farmer.project_id is None and enrollment.status in {"PENDING", "ACTIVE"}:
        farmer.project_id = body.project_id
        farmer.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(enrollment)
    return _enrollment_payload(enrollment, project)


PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES = {"ACTIVE", "PENDING"}


def _update_enrollment_lifecycle_status(
    db: Session,
    *,
    tenant_id: str,
    enrollment: FarmerProjectEnrollment,
    project: Project,
    target_status: str,
    reason: str,
    actor_id: uuid.UUID,
    action: str = "UPDATE_PROJECT_ENROLLMENT_STATUS",
) -> dict:
    before = _enrollment_payload(enrollment, project)
    if enrollment.status == target_status:
        return before
    if enrollment.status == "ARCHIVED":
        raise HTTPException(409, "Archived project enrollment cannot be updated")

    enrollment.status = target_status
    enrollment.updated_at = datetime.now(timezone.utc)
    metadata = dict(enrollment.metadata_ or {})
    lifecycle_events = list(metadata.get("lifecycle_events") or [])
    lifecycle_events.append({
        "action": action,
        "from_status": before["status"],
        "to_status": target_status,
        "reason": reason,
        "actor_id": str(actor_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    metadata["lifecycle_events"] = lifecycle_events[-20:]
    metadata["last_lifecycle_change"] = lifecycle_events[-1]
    enrollment.metadata_ = metadata

    db.flush()
    after = _enrollment_payload(enrollment, project)
    db.add(ProjectAppConfigAuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=enrollment.project_id,
        actor_id=actor_id,
        action=action,
        patched_sections=["farmer_project_enrollment.status"],
        before_config=before,
        after_config=after,
        config_patch={"enrollment_id": str(enrollment.id), "status": target_status},
        reason=reason,
        created_at=datetime.now(timezone.utc),
    ))
    return after


@router.patch("/farmer-project-enrollments/{enrollment_id}/status", response_model=FarmerProjectEnrollmentResponse)
def update_farmer_project_enrollment_status(
    enrollment_id: uuid.UUID,
    body: FarmerProjectEnrollmentStatusPatch,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PROJECT_EDIT)),
):
    """Update a project enrollment lifecycle status with reason and audit.

    Completing or cancelling the last active project enrollment does not deactivate
    the farmer; profile hydration/launch context will move them to SELF_SERVICE.
    """
    enrollment = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.id == enrollment_id,
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(404, "Project enrollment not found")

    project = db.query(Project).filter(Project.id == enrollment.project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    payload = _update_enrollment_lifecycle_status(
        db,
        tenant_id=x_tenant_id,
        enrollment=enrollment,
        project=project,
        target_status=body.status,
        reason=body.reason,
        actor_id=principal.user_id,
    )
    db.commit()
    db.refresh(enrollment)
    return _enrollment_payload(enrollment, project) if payload else _enrollment_payload(enrollment, project)


@router.get("/projects/{project_id}/farmer-enrollments/lifecycle-preview")
def preview_project_enrollment_lifecycle(
    project_id: uuid.UUID,
    target_status: str = Query(..., pattern=r"^(COMPLETED|CANCELLED|ARCHIVED|ACTIVE|PENDING)$"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW, project_scoped=True)),
):
    """Preview bulk enrollment lifecycle update for a project."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    query = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == x_tenant_id,
        FarmerProjectEnrollment.project_id == project_id,
        FarmerProjectEnrollment.status.in_(PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES),
    )
    affected = query.count()
    by_status = {
        status: db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.project_id == project_id,
            FarmerProjectEnrollment.status == status,
        ).count()
        for status in sorted(PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES)
    }
    return {
        "schema_version": "project_enrollment_lifecycle_preview.v1",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "target_status": target_status,
        "source_statuses": sorted(PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES),
        "affected_count": affected,
        "by_status": by_status,
        "can_apply": affected > 0,
        "message": f"{affected} ACTIVE/PENDING enrollment(s) would be marked {target_status}.",
    }


@router.post("/projects/{project_id}/farmer-enrollments/lifecycle-apply")
def apply_project_enrollment_lifecycle(
    project_id: uuid.UUID,
    body: ProjectEnrollmentLifecycleApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True)),
):
    """Bulk update ACTIVE/PENDING project enrollments with a single reason."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    enrollments = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.project_id == project_id,
            FarmerProjectEnrollment.status.in_(PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES),
        )
        .order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc())
        .all()
    )
    updated = []
    skipped = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == x_tenant_id,
        FarmerProjectEnrollment.project_id == project_id,
    ).count() - len(enrollments)
    for enrollment in enrollments:
        updated.append(_update_enrollment_lifecycle_status(
            db,
            tenant_id=x_tenant_id,
            enrollment=enrollment,
            project=project,
            target_status=body.target_status,
            reason=body.reason,
            actor_id=principal.user_id,
            action="BULK_UPDATE_PROJECT_ENROLLMENT_STATUS",
        ))
    db.add(ProjectAppConfigAuditEvent(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        project_id=project_id,
        actor_id=principal.user_id,
        action="BULK_UPDATE_PROJECT_ENROLLMENT_STATUS_SUMMARY",
        patched_sections=["farmer_project_enrollments.status"],
        before_config={"source_statuses": sorted(PROJECT_ENROLLMENT_BULK_SOURCE_STATUSES)},
        after_config={"target_status": body.target_status, "updated_count": len(updated), "skipped_count": skipped},
        config_patch={"target_status": body.target_status, "enrollment_ids": [item["id"] for item in updated]},
        reason=body.reason,
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return {
        "schema_version": "project_enrollment_lifecycle_apply.v1",
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "target_status": body.target_status,
        "updated_count": len(updated),
        "skipped_count": skipped,
        "updated_enrollment_ids": [item["id"] for item in updated],
        "reason": body.reason,
    }


@router.get("/farmers/{farmer_id}/project-enrollments", response_model=list[FarmerProjectEnrollmentResponse])
def list_farmer_project_enrollments(
    farmer_id: uuid.UUID,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List project memberships for a farmer."""
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    query = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == x_tenant_id,
        FarmerProjectEnrollment.farmer_id == farmer_id,
    )
    if status:
        query = query.filter(FarmerProjectEnrollment.status == status)
    enrollments = query.order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc()).all()
    project_ids = [enrollment.project_id for enrollment in enrollments]
    projects = {project.id: project for project in db.query(Project).filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    return [_enrollment_payload(enrollment, projects.get(enrollment.project_id)) for enrollment in enrollments]


@router.get("/projects/{project_id}/farmer-enrollments", response_model=list[FarmerProjectEnrollmentResponse])
def list_project_farmer_enrollments(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List farmer memberships for a project."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    query = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == x_tenant_id,
        FarmerProjectEnrollment.project_id == project_id,
    )
    if status:
        query = query.filter(FarmerProjectEnrollment.status == status)
    enrollments = query.order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc()).all()
    return [_enrollment_payload(enrollment, project) for enrollment in enrollments]


@router.get("/farmers/{farmer_id}/launch-context")
def get_farmer_launch_context(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return Android post-login launch decision context for a farmer."""
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    enrollments = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.status != "ARCHIVED",
        )
        .order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc())
        .all()
    )
    project_ids = [enrollment.project_id for enrollment in enrollments]
    projects = {project.id: project for project in db.query(Project).filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    active_enrollments = [enrollment for enrollment in enrollments if enrollment.status == "ACTIVE"]
    farmer_context = _farmer_context_payload(enrollments, projects)
    active_project_candidate = farmer_context["active_project_candidate"]

    parcel_count = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id, Parcel.farmer_id == farmer_id, Parcel.status != "ARCHIVED").count()
    try:
        from app.modules.farmer.soil_profile import SoilProfile
        soil_profile_count = db.query(SoilProfile).filter(SoilProfile.tenant_id == x_tenant_id, SoilProfile.farmer_id == farmer_id).count()
    except Exception:
        soil_profile_count = 0

    completion = _farmer_profile_completion(farmer, parcel_count, soil_profile_count)
    decision = _launch_navigation_decision(farmer, enrollments, completion)
    project_selection_required = len(active_enrollments) > 1

    bootstrap_endpoint = "/api/v1/app-config/bootstrap"
    if active_project_candidate:
        bootstrap_endpoint = f"/api/v1/app-config/bootstrap?project_id={active_project_candidate['project_id']}"

    return {
        "schema_version": "farmer_launch_context.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": x_tenant_id,
        "farmer": _farmer_payload(farmer),
        "project_enrollments": [_enrollment_payload(enrollment, projects.get(enrollment.project_id)) for enrollment in enrollments],
        "farmer_context": farmer_context,
        "active_project_count": len(active_enrollments),
        "active_project_candidate": active_project_candidate,
        "project_selection_required": project_selection_required,
        "profile_completion": completion,
        "recommended_navigation": decision,
        "endpoints": {
            "bootstrap": bootstrap_endpoint,
            "profile_hydration_by_mobile": f"/api/v1/farmers/by-mobile/{farmer.mobile_number}",
            "profile_hydration_me": "/api/v1/farmers/me/profile",
            "project_enrollments": f"/api/v1/farmers/{farmer.id}/project-enrollments",
        },
        "notes": [
            "Android may keep current native screens until backend-driven form flags are enabled.",
            "If project_selection_required is true, use project_enrollments to let the user choose context before calling bootstrap with project_id.",
        ],
    }


# --- Parcel Endpoints ---

@router.post("/parcels", response_model=ParcelResponse, status_code=201)
def create_parcel(
    body: ParcelCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Register a parcel. GPS is optional — reported area is sufficient."""
    # Validate: at least one of village_id or village_name_manual
    if not body.village_id and not body.village_name_manual:
        raise HTTPException(400, "Either village_id or village_name_manual is required")

    # Determine geometry source from provided data
    geometry_source = "NONE"
    if body.centroid_lat and body.centroid_lng:
        geometry_source = "PIN_DROP"

    parcel = Parcel(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        farmer_id=body.farmer_id,
        village_id=body.village_id,  # Can be None for manual villages
        village_name_manual=body.village_name_manual,
        reported_area=body.reported_area,
        reported_area_unit=body.reported_area_unit,
        current_crop_code=body.current_crop_code,
        soil_type_code=body.soil_type_code,
        local_name=body.local_name,
        survey_number=body.survey_number,
        ownership_type=body.ownership_type,
        annual_rent=body.annual_rent,
        annual_rent_currency=body.annual_rent_currency,
        share_percentage=body.share_percentage,
        sharecrop_percentage=body.sharecrop_percentage,
        irrigation_source=body.irrigation_source,
        crops_by_season=body.crops_by_season or {},
        geometry_source=geometry_source,
        centroid_lat=body.centroid_lat,
        centroid_lng=body.centroid_lng,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return parcel


@router.get("/parcels", response_model=list[ParcelResponse])
def list_parcels(
    farmer_id: Optional[uuid.UUID] = Query(None),
    village_id: Optional[uuid.UUID] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List parcels for a tenant."""
    query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id)
    if farmer_id:
        query = query.filter(Parcel.farmer_id == farmer_id)
    if village_id:
        query = query.filter(Parcel.village_id == village_id)
    return query.offset(offset).limit(limit).all()


@router.patch("/parcels/{parcel_id}/geometry")
def update_parcel_geometry(
    parcel_id: uuid.UUID,
    body: GeometryUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Progressively add GPS data to a parcel.

    Called when farmer/dealer does a GPS walk or pin drop.
    Does NOT replace reported_area — adds computed_area alongside it.
    """
    parcel = db.query(Parcel).filter(
        Parcel.id == parcel_id, Parcel.tenant_id == x_tenant_id
    ).first()
    if not parcel:
        raise HTTPException(404, "Parcel not found")

    normalized_geojson, point_lat, point_lng = normalize_geojson_for_parcel(
        body.geojson, body.geometry_source
    )

    if body.geometry_source == "PIN_DROP" and not normalized_geojson and (body.centroid_lat is None or body.centroid_lng is None):
        raise HTTPException(400, "PIN_DROP requires centroid_lat/centroid_lng or Point GeoJSON")
    if body.geometry_source in ("GPS_WALK", "MANUAL_DRAW", "SATELLITE") and (not normalized_geojson or normalized_geojson.get("type") != "Polygon"):
        raise HTTPException(400, f"{body.geometry_source} requires Polygon GeoJSON")

    parcel.geometry_source = body.geometry_source
    parcel.geometry_accuracy_meters = body.accuracy_meters
    parcel.geometry_captured_at = datetime.now(timezone.utc)
    parcel.geometry_captured_by = uuid.UUID(x_actor_id)

    if point_lat is not None and point_lng is not None:
        parcel.centroid_lat = point_lat
        parcel.centroid_lng = point_lng
    elif body.centroid_lat is not None and body.centroid_lng is not None:
        parcel.centroid_lat = body.centroid_lat
        parcel.centroid_lng = body.centroid_lng

    computed_area_hectares = None
    if normalized_geojson and normalized_geojson.get("type") == "Polygon":
        centroid_lat, centroid_lng, computed_area_hectares = _centroid_from_geojson(db, normalized_geojson)
        parcel.centroid_lat = centroid_lat
        parcel.centroid_lng = centroid_lng
        parcel.computed_area_hectares = computed_area_hectares
        db.flush()
        db.execute(
            text(
                """
                UPDATE parcels
                SET geometry = ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)
                WHERE id = :parcel_id AND tenant_id = :tenant_id
                """
            ),
            {
                "geojson": json.dumps(normalized_geojson),
                "parcel_id": str(parcel_id),
                "tenant_id": x_tenant_id,
            },
        )
    elif body.geometry_source in ("NONE", "PIN_DROP"):
        parcel.computed_area_hectares = None
        db.flush()
        db.execute(
            text(
                """
                UPDATE parcels
                SET geometry = NULL
                WHERE id = :parcel_id AND tenant_id = :tenant_id
                """
            ),
            {"parcel_id": str(parcel_id), "tenant_id": x_tenant_id},
        )

    parcel.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "geometry_updated",
        "geometry_source": parcel.geometry_source,
        "parcel_id": str(parcel_id),
        "centroid_lat": str(parcel.centroid_lat) if parcel.centroid_lat is not None else None,
        "centroid_lng": str(parcel.centroid_lng) if parcel.centroid_lng is not None else None,
        "computed_area_hectares": str(parcel.computed_area_hectares) if parcel.computed_area_hectares is not None else None,
        "geojson_type": normalized_geojson.get("type") if normalized_geojson else None,
    }


# --- Form Field Config (lightweight toggles for Android) ---

@router.get("/config/form-fields")
def get_form_field_config(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return which optional fields are enabled for this tenant.

    Not full SDUI — just toggles for optional form sections.
    Default: all enabled for pilot tenants.
    """
    # For MVP: return defaults. In future: load from tenant config in DB.
    return {
        "farmer": {
            "aadhaar_number": True,
            "father_name": True,
            "age": True,
            "gender": True,
            "crops_by_season": True,
            "assistance_mode": True,
            "language_preference": True,
        },
        "parcel": {
            "survey_number": True,
            "ownership_type": True,
            "annual_rent_for_leased": True,
            "irrigation_source": True,
            "soil_type_code": True,
            "local_name": True,
            "gps_pin_drop": True,
            "gps_walk_boundary": False,  # Not in MVP
        },
        "soil_profile": {
            "shc_card_section": True,
            "soil_texture": True,
            "soil_color": True,
            "macro_nutrients": True,
            "micro_nutrients": False,  # Advanced — off by default
        },
    }


# --- Farmer /me endpoint (for pre-registered/bulk-import flow) ---

@router.get("/farmers/duplicates")
def list_duplicate_farmers(
    mobile_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """List tenant/mobile duplicate farmer profiles for admin cleanup."""
    from app.modules.workflow.models import CropCycle

    query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id, Farmer.status != "ARCHIVED")
    if mobile_number:
        query = query.filter(Farmer.mobile_number == normalize_mobile_number(mobile_number))

    farmers = query.order_by(Farmer.mobile_number, Farmer.updated_at.desc(), Farmer.created_at.desc()).all()
    groups: dict[str, list[Farmer]] = {}
    for farmer in farmers:
        groups.setdefault(farmer.mobile_number, []).append(farmer)

    response = []
    for mobile, group in groups.items():
        if len(group) < 2:
            continue
        selected, duplicates = _select_hydration_farmer(db, x_tenant_id, mobile)
        response.append({
            "mobile_number": mobile,
            "recommended_primary_farmer_id": str(selected.id) if selected else None,
            "farmers": [
                {
                    "id": str(farmer.id),
                    "display_name": farmer.display_name,
                    "status": farmer.status,
                    "parcel_count": db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id, Parcel.farmer_id == farmer.id).count(),
                    "crop_cycle_count": db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.farmer_id == farmer.id).count(),
                    "is_recommended_primary": bool(selected and farmer.id == selected.id),
                    "created_at": _iso_date(farmer.created_at),
                    "updated_at": _iso_date(farmer.updated_at),
                }
                for farmer in group
            ],
            "duplicate_count": len(duplicates),
        })
    return {
        "schema_version": "farmer_duplicates.v1",
        "tenant_id": x_tenant_id,
        "groups": response,
        "group_count": len(response),
    }


@router.post("/farmers/{primary_farmer_id}/duplicates/archive")
def archive_duplicate_farmers(
    primary_farmer_id: uuid.UUID,
    body: DuplicateFarmerArchiveRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Safely archive duplicate farmer rows for the same mobile number."""
    from app.modules.workflow.models import CropCycle

    primary = db.query(Farmer).filter(Farmer.id == primary_farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not primary:
        raise HTTPException(404, "Primary farmer not found")

    archived = []
    blocked = []
    now = datetime.now(timezone.utc)
    for duplicate_id in body.duplicate_farmer_ids:
        duplicate = db.query(Farmer).filter(Farmer.id == duplicate_id, Farmer.tenant_id == x_tenant_id).first()
        if not duplicate:
            blocked.append({"id": str(duplicate_id), "reason": "not_found"})
            continue
        if duplicate.id == primary.id:
            blocked.append({"id": str(duplicate.id), "reason": "cannot_archive_primary"})
            continue
        if duplicate.mobile_number != primary.mobile_number:
            blocked.append({"id": str(duplicate.id), "reason": "mobile_number_mismatch"})
            continue

        parcel_count = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id, Parcel.farmer_id == duplicate.id).count()
        crop_cycle_count = db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.farmer_id == duplicate.id).count()
        if not body.force and (parcel_count or crop_cycle_count):
            blocked.append({
                "id": str(duplicate.id),
                "reason": "has_child_records",
                "parcel_count": parcel_count,
                "crop_cycle_count": crop_cycle_count,
            })
            continue

        duplicate.status = "ARCHIVED"
        duplicate.updated_at = now
        archived.append({
            "id": str(duplicate.id),
            "display_name": duplicate.display_name,
            "parcel_count": parcel_count,
            "crop_cycle_count": crop_cycle_count,
        })

    if blocked and not archived:
        raise HTTPException(400, {"message": "No duplicate farmers archived", "blocked": blocked})

    db.commit()
    return {
        "schema_version": "farmer_duplicate_archive.v1",
        "primary_farmer_id": str(primary.id),
        "mobile_number": primary.mobile_number,
        "archived": archived,
        "blocked": blocked,
        "reason": body.reason,
        "actor_id": x_actor_id,
    }


@router.get("/farmers/by-mobile/{mobile_number:path}")
def get_farmer_profile_by_mobile(
    mobile_number: str,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
):
    """Hydrate Android local storage after mobile login.

    Returns farmer + parcels + soil profiles + active/completed crop cycles.
    If multiple farmer rows share the mobile number, selects the richest active
    profile and reports the extras under `duplicates` for cleanup.
    """
    normalized_mobile = normalize_mobile_number(mobile_number)
    farmer, duplicates = _select_hydration_farmer(db, x_tenant_id, normalized_mobile)
    if not farmer:
        raise HTTPException(404, "No farmer profile found for this mobile number")
    return _build_profile_hydration_response(db, x_tenant_id, farmer, duplicates)


@router.get("/farmers/me/profile")
def get_my_profile_hydration(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Authenticated profile hydration endpoint for Android after login."""
    from app.modules.auth.models import User

    user = db.query(User).filter(User.id == uuid.UUID(x_actor_id)).first()
    if not user:
        raise HTTPException(404, "User not found")

    farmer, duplicates = _select_hydration_farmer(db, x_tenant_id, user.mobile_number)
    if not farmer:
        raise HTTPException(404, "No farmer profile found for this user")
    return _build_profile_hydration_response(db, x_tenant_id, farmer, duplicates)


@router.get("/farmers/me")
def get_my_farmer_profile(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Get farmer profile for the logged-in user.

    Returns 404 if no farmer profile exists (user hasn't been pre-registered).
    Used for bulk-import flow where enterprise pre-registers farmers.
    """
    from app.modules.auth.models import User

    # Find user by actor_id
    user = db.query(User).filter(User.id == uuid.UUID(x_actor_id)).first()
    if not user:
        raise HTTPException(404, "User not found")

    # Find farmer by mobile number + tenant
    farmer = (
        db.query(Farmer)
        .filter(
            Farmer.mobile_number == user.mobile_number,
            Farmer.tenant_id == x_tenant_id,
        )
        .first()
    )
    if not farmer:
        raise HTTPException(404, "No farmer profile found for this user")

    return {
        "id": str(farmer.id),
        "mobile_number": farmer.mobile_number,
        "display_name": farmer.display_name,
        "village_id": str(farmer.village_id) if farmer.village_id else None,
        "village_name_manual": farmer.village_name_manual,
        "primary_crop_code": farmer.primary_crop_code,
        "crops_by_season": farmer.crops_by_season,
        "total_land_area": str(farmer.total_land_area) if farmer.total_land_area else None,
        "total_land_unit": farmer.total_land_unit,
        "status": farmer.status,
    }
