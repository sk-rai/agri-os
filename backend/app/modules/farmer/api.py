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

import uuid
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.modules.farmer.models import Tenant, Project, ProjectRole, Farmer, Parcel

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


class RoleAssign(BaseModel):
    user_id: uuid.UUID
    role: str = Field(..., pattern=r"^(DEALER|FIELD_AGENT|AGRONOMIST|MANAGER|ENTERPRISE_ADMIN)$")
    territory_scope: dict = Field(default_factory=dict)


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
    ownership_type: str = "OWNED"  # OWNED, LEASED, SHARED, FAMILY
    annual_rent: Optional[float] = None  # Required if LEASED
    annual_rent_currency: str = "INR"
    irrigation_source: Optional[str] = None
    # TUBEWELL_DIESEL, TUBEWELL_ELECTRIC, CANAL, PURCHASED_WATER, RAIN_FED, POND_TANK, RIVER_STREAM
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
    geometry_source: str = Field(..., pattern=r"^(PIN_DROP|GPS_WALK|SATELLITE)$")
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None
    geojson: Optional[dict] = None  # Standard GeoJSON: Point, MultiPoint, or Polygon
    accuracy_meters: Optional[float] = None


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


# --- Project Endpoints ---

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


@router.post("/projects/{project_id}/roles", status_code=201)
def assign_role(
    project_id: uuid.UUID,
    body: RoleAssign,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Assign a user to a project with a role and territory scope."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.tenant_id == x_tenant_id
    ).first()
    if not project:
        raise HTTPException(404, "Project not found")

    role = ProjectRole(
        id=uuid.uuid4(),
        project_id=project_id,
        user_id=body.user_id,
        role=body.role,
        territory_scope=body.territory_scope,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(role)
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

    farmer = Farmer(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        mobile_number=body.mobile_number,
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
        irrigation_source=body.irrigation_source,
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

    parcel.geometry_source = body.geometry_source
    parcel.geometry_accuracy_meters = body.accuracy_meters
    parcel.geometry_captured_at = datetime.now(timezone.utc)
    parcel.geometry_captured_by = uuid.UUID(x_actor_id)

    if body.centroid_lat and body.centroid_lng:
        parcel.centroid_lat = body.centroid_lat
        parcel.centroid_lng = body.centroid_lng

    # TODO: If polygon_geojson provided, convert to PostGIS geometry
    # and compute area via ST_Area()

    parcel.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "geometry_updated",
        "geometry_source": parcel.geometry_source,
        "parcel_id": str(parcel_id),
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
