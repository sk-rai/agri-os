"""Soil Profile models and API.

Based on India's Soil Health Card (SHC) scheme.
12 parameters: N, P, K, S (macro), Zn, Fe, Cu, Mn, Bo (micro), pH, EC, OC (physical).

Each profile is linked to a parcel and has a test date.
Farmers can have multiple tests over time (soil health tracking).

Source: https://soilhealth.dac.gov.in
"""

import uuid
from datetime import datetime, timezone, date
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import Column, String, Date, DECIMAL, Text, ForeignKey, Index, DateTime, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import Base, get_db
from app.shared.models import AuditMixin, UUIDPrimaryKey


# --- Model ---

class SoilProfile(Base, UUIDPrimaryKey, AuditMixin):
    """Soil Health Card test results for a parcel.

    12 parameters per India SHC standard.
    Multiple tests over time allowed (tracked by test_date).
    """

    __tablename__ = "soil_profiles"

    tenant_id = Column(String(50), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)

    # Test metadata
    test_date = Column(Date, nullable=False)
    lab_name = Column(String(200))
    sample_id = Column(String(100))  # Lab sample number
    shc_card_number = Column(String(100))  # Government SHC number if available

    # Macro Nutrients (kg/hectare typically)
    nitrogen_n = Column(DECIMAL(8, 2))  # Available Nitrogen
    phosphorus_p = Column(DECIMAL(8, 2))  # Available Phosphorus
    potassium_k = Column(DECIMAL(8, 2))  # Available Potassium
    sulphur_s = Column(DECIMAL(8, 2))  # Available Sulphur

    # Micro Nutrients (ppm typically)
    zinc_zn = Column(DECIMAL(8, 3))
    iron_fe = Column(DECIMAL(8, 3))
    copper_cu = Column(DECIMAL(8, 3))
    manganese_mn = Column(DECIMAL(8, 3))
    boron_bo = Column(DECIMAL(8, 3))

    # Physical Properties
    ph = Column(DECIMAL(4, 2))  # 0-14 scale
    ec = Column(DECIMAL(6, 3))  # Electrical Conductivity (dS/m)
    organic_carbon_oc = Column(DECIMAL(5, 2))  # Percentage

    # Soil type (from reference table)
    soil_type_code = Column(String(30))  # ALLUVIAL, BLACK_COTTON, etc.
    soil_texture = Column(String(50))  # Sandy, Loamy, Clay, Sandy Loam, etc.
    soil_color = Column(String(50))  # Dark brown, Reddish, Black, etc.

    # Ratings (Low/Medium/High per SHC standard) — stored as JSONB for flexibility
    ratings = Column(JSONB, default=dict)
    # e.g., {"nitrogen_n": "LOW", "phosphorus_p": "MEDIUM", "potassium_k": "HIGH"}

    # Recommendations from SHC
    recommendations = Column(JSONB, default=dict)
    # e.g., {"urea_kg_per_hectare": 120, "dap_kg_per_hectare": 50}

    # Source of data
    data_source = Column(String(30), default="MANUAL")
    # MANUAL, SHC_CARD, LAB_REPORT, ESTIMATED

    notes = Column(Text)

    __table_args__ = (
        Index("idx_soil_profile_tenant", "tenant_id"),
        Index("idx_soil_profile_parcel", "parcel_id"),
        Index("idx_soil_profile_farmer", "farmer_id"),
        Index("idx_soil_profile_date", "test_date"),
    )

    @property
    def boron_b(self):
        """Android/form payload alias for SHC boron_bo storage."""
        return self.boron_bo


class SoilEnrichmentJobAudit(Base, UUIDPrimaryKey, AuditMixin):
    """Operational audit trail for backend soil enrichment queue attempts."""

    __tablename__ = "soil_enrichment_job_audit_events"

    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=True)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)

    job_type = Column(String(50), nullable=False)
    provider = Column(String(50), nullable=True)
    status = Column(String(30), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=1)
    reason = Column(Text)
    error_code = Column(String(100))
    metadata_ = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_soil_enrichment_job_audit_tenant", "tenant_id"),
        Index("idx_soil_enrichment_job_audit_farmer", "farmer_id"),
        Index("idx_soil_enrichment_job_audit_parcel", "parcel_id"),
        Index("idx_soil_enrichment_job_audit_project", "project_id"),
        Index("idx_soil_enrichment_job_audit_status", "status"),
        Index("idx_soil_enrichment_job_audit_job_type", "job_type"),
    )


class SoilEnrichmentSnapshot(Base, UUIDPrimaryKey, AuditMixin):
    """Provider-derived soil baseline or dynamic soil-water snapshot for a parcel.

    Examples:
    - SOILGRIDS baseline pH/OC/N/texture at 250m resolution.
    - OPEN_METEO soil moisture/temperature forecast snapshot.
    - Future in-house satellite/model-derived parcel enrichment.
    """

    __tablename__ = "soil_enrichment_snapshots"

    tenant_id = Column(String(50), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=False)
    farmer_id = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)

    provider = Column(String(50), nullable=False)
    provider_dataset = Column(String(100))
    snapshot_type = Column(String(30), nullable=False, default="BASELINE")
    status = Column(String(30), nullable=False, default="AVAILABLE")

    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    depth_layer = Column(String(50))
    resolution_meters = Column(Integer)
    confidence = Column(String(30))

    observed_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True))

    ph = Column(DECIMAL(5, 2))
    organic_carbon = Column(DECIMAL(10, 4))
    nitrogen = Column(DECIMAL(10, 4))
    clay_percent = Column(DECIMAL(6, 2))
    silt_percent = Column(DECIMAL(6, 2))
    sand_percent = Column(DECIMAL(6, 2))
    bulk_density = Column(DECIMAL(10, 4))
    cec = Column(DECIMAL(10, 4))

    surface_soil_moisture = Column(DECIMAL(10, 4))
    root_zone_soil_moisture = Column(DECIMAL(10, 4))
    soil_temperature_c = Column(DECIMAL(6, 2))
    evapotranspiration_mm = Column(DECIMAL(8, 3))

    normalized_values = Column(JSONB, nullable=False, default=dict)
    raw_payload = Column(JSONB, nullable=False, default=dict)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    error_message = Column(Text)

    __table_args__ = (
        Index("idx_soil_enrichment_tenant", "tenant_id"),
        Index("idx_soil_enrichment_parcel", "parcel_id"),
        Index("idx_soil_enrichment_farmer", "farmer_id"),
        Index("idx_soil_enrichment_provider", "provider"),
        Index("idx_soil_enrichment_type", "snapshot_type"),
        Index("idx_soil_enrichment_observed", "observed_at"),
        Index("idx_soil_enrichment_latest", "tenant_id", "parcel_id", "provider", "snapshot_type", "observed_at"),
    )


# --- API Schemas ---

def _model_patch_values(body: BaseModel) -> dict:
    if hasattr(body, "model_dump"):
        return body.model_dump(exclude_unset=True)
    return body.dict(exclude_unset=True)


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _iso_datetime(value):
    return value.isoformat() if value else None


class SoilGridsFetchRequest(BaseModel):
    parcel_id: uuid.UUID
    depth_layer: str = "0-5cm"
    provider_payload: Optional[dict] = None
    use_live_provider: bool = False


class ShcSlusiManualCaptureRequest(BaseModel):
    parcel_id: uuid.UUID
    state: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    cycle: Optional[str] = Field(None, max_length=20)
    parameter: str = Field(..., min_length=1, max_length=80)
    status_class: Optional[str] = Field(None, max_length=80)
    value_text: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, max_length=50)
    depth_layer: str = "district_visual_layer"
    source_url: str = "https://soilhealth.dac.gov.in/slusi-visualisation/"
    observed_at: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=1000)
    raw_payload: dict = Field(default_factory=dict)


class ShcSlusiPointCaptureRequest(BaseModel):
    parcel_id: uuid.UUID
    state: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    village: Optional[str] = Field(None, max_length=150)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    cycle: Optional[str] = Field(None, max_length=20)
    source_url: str = "https://soilhealth.dac.gov.in/slusi-visualisation/"
    wms_url: Optional[str] = Field(None, max_length=2000)
    observed_at: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=1000)
    n_kg_ha: Optional[float] = None
    p_kg_ha: Optional[float] = None
    k_kg_ha: Optional[float] = None
    b_ppm: Optional[float] = None
    fe_ppm: Optional[float] = None
    zn_ppm: Optional[float] = None
    cu_ppm: Optional[float] = None
    s_ppm: Optional[float] = None
    organic_carbon_percent: Optional[float] = None
    ph: Optional[float] = None
    ec_ds_m: Optional[float] = None
    mn_ppm: Optional[float] = None
    depth_50k: Optional[str] = Field(None, max_length=100)
    slope_50k: Optional[str] = Field(None, max_length=150)
    erosion_50k: Optional[str] = Field(None, max_length=100)
    texture_50k: Optional[str] = Field(None, max_length=100)
    lcc_50k: Optional[str] = Field(None, max_length=50)
    lic_50k: Optional[str] = Field(None, max_length=50)
    hsg_50k: Optional[str] = Field(None, max_length=50)
    cec_text: Optional[str] = Field(None, max_length=100)
    soil_code: Optional[str] = Field(None, max_length=100)
    raw_payload: dict = Field(default_factory=dict)


class SoilEnrichmentJobAuditCreate(BaseModel):
    farmer_id: Optional[uuid.UUID] = None
    parcel_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    job_type: str = Field(..., pattern=r"^(FETCH_SOIL_BASELINE|FETCH_SOIL_MOISTURE|FETCH_SLUSI_POINT|FETCH_SATELLITE_SOIL)$")
    provider: Optional[str] = None
    status: str = Field(..., pattern=r"^(QUEUED|FETCHED|FAILED|SKIPPED|DEFERRED)$")
    attempt_count: int = Field(default=1, ge=1, le=100)
    reason: Optional[str] = None
    error_code: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class SoilEnrichmentJobAuditResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    farmer_id: Optional[uuid.UUID] = None
    parcel_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    job_type: str
    provider: Optional[str] = None
    status: str
    attempt_count: int
    reason: Optional[str] = None
    error_code: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SoilEnrichmentSnapshotCreate(BaseModel):
    parcel_id: uuid.UUID
    farmer_id: Optional[uuid.UUID] = None
    provider: str = Field(..., min_length=2, max_length=50)
    provider_dataset: Optional[str] = None
    snapshot_type: str = Field(default="BASELINE", pattern=r"^(BASELINE|MOISTURE|FORECAST|MODEL_DERIVED)$")
    status: str = Field(default="AVAILABLE", pattern=r"^(AVAILABLE|STALE|FAILED)$")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    depth_layer: Optional[str] = None
    resolution_meters: Optional[int] = Field(None, ge=1)
    confidence: Optional[str] = None
    observed_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ph: Optional[float] = None
    organic_carbon: Optional[float] = None
    nitrogen: Optional[float] = None
    clay_percent: Optional[float] = None
    silt_percent: Optional[float] = None
    sand_percent: Optional[float] = None
    bulk_density: Optional[float] = None
    cec: Optional[float] = None
    surface_soil_moisture: Optional[float] = None
    root_zone_soil_moisture: Optional[float] = None
    soil_temperature_c: Optional[float] = None
    evapotranspiration_mm: Optional[float] = None
    normalized_values: dict = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    error_message: Optional[str] = None


class SoilEnrichmentSnapshotResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    parcel_id: uuid.UUID
    farmer_id: uuid.UUID
    provider: str
    provider_dataset: Optional[str] = None
    snapshot_type: str
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    depth_layer: Optional[str] = None
    resolution_meters: Optional[int] = None
    confidence: Optional[str] = None
    observed_at: Optional[str] = None
    fetched_at: str
    expires_at: Optional[str] = None
    ph: Optional[float] = None
    organic_carbon: Optional[float] = None
    nitrogen: Optional[float] = None
    clay_percent: Optional[float] = None
    silt_percent: Optional[float] = None
    sand_percent: Optional[float] = None
    bulk_density: Optional[float] = None
    cec: Optional[float] = None
    surface_soil_moisture: Optional[float] = None
    root_zone_soil_moisture: Optional[float] = None
    soil_temperature_c: Optional[float] = None
    evapotranspiration_mm: Optional[float] = None
    normalized_values: dict = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


SOIL_ENRICHMENT_SOURCE_REGISTRY = {
    "SOILGRIDS": {
        "provider_family": "OPEN_SOURCE_BASELINE",
        "display_name": "ISRIC SoilGrids",
        "snapshot_types": ["BASELINE"],
        "default_confidence": "MODELLED",
        "source_granularity": "GRID_CELL_250M",
        "automation_mode": "BACKEND_PROVIDER_ADAPTER",
        "notes": "Automated lat/lon baseline for pH, organic carbon, nitrogen, texture, and related soil properties.",
    },
    "OPEN_METEO": {
        "provider_family": "WEATHER_SOIL_MOISTURE",
        "display_name": "Open-Meteo Weather & Soil",
        "snapshot_types": ["MOISTURE", "FORECAST"],
        "default_confidence": "FORECAST_MODEL",
        "source_granularity": "WEATHER_GRID",
        "automation_mode": "BACKEND_PROVIDER_ADAPTER",
        "notes": "Backend-scheduled soil moisture, soil temperature, evapotranspiration, and forecast snapshots.",
    },
    "SHC_SLUSI": {
        "provider_family": "GOVT_VISUAL_BASELINE",
        "display_name": "Soil Health Card / SLUSI visualisation",
        "snapshot_types": ["BASELINE"],
        "default_confidence": "GOVT_VISUAL_LAYER",
        "source_granularity": "DISTRICT_OR_MICROWATERSHED_OR_POINT_POPUP",
        "automation_mode": "MANUAL_OR_IMPORT_UNTIL_OFFICIAL_API",
        "observed_transport": "OGC_WMS_GETFEATUREINFO_JSON",
        "observed_request": {
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetFeatureInfo",
            "info_format": "application/json",
            "srs": "EPSG:4326",
            "hide_geometry": True,
        },
        "expected_point_fields": [
            "state", "district", "village", "latitude", "longitude", "cycle",
            "n_kg_ha", "p_kg_ha", "k_kg_ha", "b_ppm", "fe_ppm", "zn_ppm",
            "cu_ppm", "s_ppm", "organic_carbon_percent", "ph", "ec_ds_m", "mn_ppm",
            "depth_50k", "slope_50k", "erosion_50k", "texture_50k", "lcc_50k", "lic_50k", "hsg_50k", "cec_text", "soil_code",
        ],
        "notes": "Observed as GeoServer-style WMS GetFeatureInfo JSON behind the public UI. Store observed/admin-imported point payloads now; enable automated fetch only after endpoint stability and usage permission are confirmed.",
    },
    "IN_HOUSE_SATELLITE": {
        "provider_family": "IN_HOUSE_MODEL",
        "display_name": "Agri-OS satellite/model pipeline",
        "snapshot_types": ["BASELINE", "MOISTURE", "MODEL_DERIVED"],
        "default_confidence": "MODEL_DERIVED",
        "source_granularity": "PARCEL_OR_GRID",
        "automation_mode": "FUTURE_BACKEND_MODEL",
        "notes": "Future open-source satellite/remote-sensing pipeline for parcel-level enrichment.",
    },
}


def _soil_enrichment_source_metadata(provider: str, metadata: Optional[dict] = None) -> dict:
    provider_key = (provider or "").strip().upper()
    contract = SOIL_ENRICHMENT_SOURCE_REGISTRY.get(provider_key, {})
    merged = dict(metadata or {})
    merged.setdefault("provider_key", provider_key)
    if contract:
        merged.setdefault("provider_family", contract["provider_family"])
        merged.setdefault("source_granularity", contract["source_granularity"])
        merged.setdefault("automation_mode", contract["automation_mode"])
        merged.setdefault("provenance_contract", "soil_enrichment_sources.v1")
    return merged


class SoilProfileCreate(BaseModel):
    """Create soil profile — supports 3 tiers of data entry."""
    parcel_id: uuid.UUID
    farmer_id: uuid.UUID

    # Tier 1: Inferred (auto-populated from geography)
    soil_type_code: Optional[str] = None  # ALLUVIAL, BLACK_COTTON, etc.

    # Tier 2: Farmer-reported (simple observation)
    soil_texture: Optional[str] = None  # SANDY, LOAMY, CLAY, SANDY_LOAM, CLAY_LOAM
    soil_color: Optional[str] = None  # DARK_BROWN, LIGHT_BROWN, REDDISH, BLACK, GREY

    # Tier 3: Lab-tested (SHC card data — all optional)
    test_date: Optional[date] = None
    lab_name: Optional[str] = None
    shc_card_number: Optional[str] = None
    nitrogen_n: Optional[float] = None
    phosphorus_p: Optional[float] = None
    potassium_k: Optional[float] = None
    sulphur_s: Optional[float] = None
    zinc_zn: Optional[float] = None
    iron_fe: Optional[float] = None
    copper_cu: Optional[float] = None
    manganese_mn: Optional[float] = None
    boron_bo: Optional[float] = None
    boron_b: Optional[float] = None  # Android/form payload alias; stored as boron_bo
    ph: Optional[float] = None
    ec: Optional[float] = None
    organic_carbon_oc: Optional[float] = None

    # Source
    data_source: str = "MANUAL"  # MANUAL, SHC_CARD, LAB_REPORT, INFERRED
    notes: Optional[str] = None


class SoilProfileUpdate(BaseModel):
    soil_type_code: Optional[str] = None
    soil_texture: Optional[str] = None
    soil_color: Optional[str] = None
    test_date: Optional[date] = None
    lab_name: Optional[str] = None
    shc_card_number: Optional[str] = None
    nitrogen_n: Optional[float] = None
    phosphorus_p: Optional[float] = None
    potassium_k: Optional[float] = None
    sulphur_s: Optional[float] = None
    zinc_zn: Optional[float] = None
    iron_fe: Optional[float] = None
    copper_cu: Optional[float] = None
    manganese_mn: Optional[float] = None
    boron_bo: Optional[float] = None
    boron_b: Optional[float] = None
    ph: Optional[float] = None
    ec: Optional[float] = None
    organic_carbon_oc: Optional[float] = None
    data_source: Optional[str] = None
    notes: Optional[str] = None


class SoilProfileResponse(BaseModel):
    id: uuid.UUID
    parcel_id: uuid.UUID
    farmer_id: uuid.UUID
    soil_type_code: Optional[str] = None
    soil_texture: Optional[str] = None
    soil_color: Optional[str] = None
    test_date: Optional[date] = None
    ph: Optional[float] = None
    nitrogen_n: Optional[float] = None
    phosphorus_p: Optional[float] = None
    potassium_k: Optional[float] = None
    organic_carbon_oc: Optional[float] = None
    boron_b: Optional[float] = None
    data_source: str
    ratings: Optional[dict] = None
    recommendations: Optional[dict] = None

    class Config:
        from_attributes = True


class InferredSoilResponse(BaseModel):
    """Response for district-level soil inference."""
    district_name: str
    inferred_soil_type: str
    inferred_soil_type_name: str
    typical_ph_range: str
    typical_texture: str
    confidence: str  # HIGH, MEDIUM, LOW
    description: str


# --- District-level soil defaults for UP ---
# Source: ICAR, NBSS&LUP research, published SHC aggregate data
UP_DISTRICT_SOIL_DEFAULTS = {
    # Eastern UP (Indo-Gangetic Plain — predominantly Alluvial)
    "AZAMGARH": {"type": "ALLUVIAL", "ph": "6.5-7.8", "texture": "LOAMY", "confidence": "HIGH"},
    "GORAKHPUR": {"type": "ALLUVIAL", "ph": "6.5-7.5", "texture": "CLAY_LOAM", "confidence": "HIGH"},
    "DEORIA": {"type": "ALLUVIAL", "ph": "6.8-8.0", "texture": "LOAMY", "confidence": "HIGH"},
    "KUSHINAGAR": {"type": "ALLUVIAL", "ph": "6.5-7.5", "texture": "CLAY_LOAM", "confidence": "HIGH"},
    "BALLIA": {"type": "ALLUVIAL", "ph": "7.0-8.2", "texture": "LOAMY", "confidence": "HIGH"},
    "JAUNPUR": {"type": "ALLUVIAL", "ph": "6.8-7.8", "texture": "LOAMY", "confidence": "HIGH"},
    "VARANASI": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "SANDY_LOAM", "confidence": "HIGH"},
    "GHAZIPUR": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "LOAMY", "confidence": "HIGH"},
    "AYODHYA": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "LOAMY", "confidence": "HIGH"},
    "LUCKNOW": {"type": "ALLUVIAL", "ph": "7.2-8.2", "texture": "SANDY_LOAM", "confidence": "HIGH"},
    # Western UP
    "AGRA": {"type": "ALLUVIAL", "ph": "7.5-8.5", "texture": "SANDY_LOAM", "confidence": "HIGH"},
    "MEERUT": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "LOAMY", "confidence": "HIGH"},
    "ALIGARH": {"type": "ALLUVIAL", "ph": "7.5-8.5", "texture": "SANDY_LOAM", "confidence": "HIGH"},
    "BAREILLY": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "LOAMY", "confidence": "HIGH"},
    # Bundelkhand (mixed — some Red/Laterite)
    "JHANSI": {"type": "RED", "ph": "6.0-7.5", "texture": "SANDY_LOAM", "confidence": "MEDIUM"},
    "BANDA": {"type": "RED", "ph": "6.5-7.5", "texture": "SANDY", "confidence": "MEDIUM"},
    "CHITRAKOOT": {"type": "RED", "ph": "6.0-7.0", "texture": "SANDY_LOAM", "confidence": "MEDIUM"},
    # Default for unmatched UP districts (most are alluvial)
    "_DEFAULT": {"type": "ALLUVIAL", "ph": "7.0-8.0", "texture": "LOAMY", "confidence": "MEDIUM"},
}

SOIL_TYPE_NAMES = {
    "ALLUVIAL": "Alluvial Soil (जलोढ़ मिट्टी)",
    "BLACK_COTTON": "Black Cotton Soil (काली मिट्टी)",
    "RED": "Red Soil (लाल मिट्टी)",
    "LATERITE": "Laterite Soil (लैटेराइट मिट्टी)",
    "SANDY": "Sandy Soil (बालू मिट्टी)",
}

SOIL_TYPE_DESCRIPTIONS = {
    "ALLUVIAL": "Fertile soil found in Indo-Gangetic plains. Good for rice, wheat, sugarcane.",
    "BLACK_COTTON": "Clay-rich, retains moisture. Good for cotton, soybean, wheat.",
    "RED": "Iron-rich, found in southern/eastern India. Good for groundnut, millets.",
    "LATERITE": "Leached soil in high rainfall areas. Good for tea, coffee, cashew.",
    "SANDY": "Low moisture retention. Good for bajra, guar.",
}


def _validate_profile_option_value(db: Session, *, tenant_id: str, option_set: str, value: Optional[str], path: str, project_id: Optional[uuid.UUID] = None) -> None:
    """Reject stale Android-hardcoded values that are no longer valid for backend-owned profile option sets."""
    if value is None or value == "":
        return
    from app.modules.workflow.forms import _effective_profile_option_registry

    registry = _effective_profile_option_registry(db, tenant_id=tenant_id, project_id=project_id)
    resolved = registry.get(option_set)
    allowed = {str(option.value) for option in (resolved.options if resolved else [])}
    if str(value) not in allowed:
        raise HTTPException(400, {
            "error": "INVALID_PROFILE_OPTION_VALUE",
            "path": path,
            "option_set": option_set,
            "value": value,
            "allowed_values": sorted(allowed),
            "message": f"{path} must be one of the backend-owned {option_set} options.",
        })


def _infer_soil_profile_project_id(db: Session, *, tenant_id: str, parcel_id: uuid.UUID, farmer_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Infer project context for soil profile option validation from parcel/farmer linkage."""
    from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel

    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == tenant_id, Parcel.farmer_id == farmer_id).first()
    if not parcel:
        raise HTTPException(404, "Parcel not found for farmer")
    if parcel.project_id:
        return parcel.project_id
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == tenant_id, Farmer.status != "ARCHIVED").first()
    if farmer and farmer.project_id:
        return farmer.project_id
    active_enrollments = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == tenant_id,
        FarmerProjectEnrollment.farmer_id == farmer_id,
        FarmerProjectEnrollment.status == "ACTIVE",
    ).all()
    if len(active_enrollments) == 1:
        return active_enrollments[0].project_id
    return None


def _soil_enrichment_summary_payload(snapshots: list[SoilEnrichmentSnapshot]) -> dict:
    """Summarize backend-owned soil enrichment snapshots for Android/admin."""
    latest_by_type: dict[str, dict] = {}
    provider_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for snapshot in snapshots:
        payload = _soil_enrichment_payload(snapshot)
        provider = payload.get("provider") or "UNKNOWN"
        snapshot_type = payload.get("snapshot_type") or "UNKNOWN"
        status = payload.get("status") or "UNKNOWN"

        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        type_counts[snapshot_type] = type_counts.get(snapshot_type, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

        if snapshot_type not in latest_by_type:
            latest_by_type[snapshot_type] = payload

    latest_baseline = latest_by_type.get("BASELINE")
    latest_moisture = latest_by_type.get("MOISTURE")
    latest_slusi = next(
        (payload for payload in latest_by_type.values() if payload.get("provider") in {"SHC_SLUSI", "SLUSI", "SHC"}),
        None,
    )

    return {
        "snapshot_count": len(snapshots),
        "provider_counts": provider_counts,
        "snapshot_type_counts": type_counts,
        "status_counts": status_counts,
        "has_baseline": latest_baseline is not None,
        "has_moisture": latest_moisture is not None,
        "has_slusi_or_shc": latest_slusi is not None,
        "latest_by_type": latest_by_type,
        "latest_baseline": latest_baseline,
        "latest_moisture": latest_moisture,
        "latest_slusi_or_shc": latest_slusi,
    }


def _soil_enrichment_job_audit_payload(event: SoilEnrichmentJobAudit) -> dict:
    return {
        "id": str(event.id),
        "tenant_id": event.tenant_id,
        "farmer_id": str(event.farmer_id) if event.farmer_id else None,
        "parcel_id": str(event.parcel_id) if event.parcel_id else None,
        "project_id": str(event.project_id) if event.project_id else None,
        "job_type": event.job_type,
        "provider": event.provider,
        "status": event.status,
        "attempt_count": event.attempt_count,
        "reason": event.reason,
        "error_code": event.error_code,
        "metadata": event.metadata_ or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }


def _soil_enrichment_payload(snapshot: SoilEnrichmentSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "tenant_id": snapshot.tenant_id,
        "parcel_id": snapshot.parcel_id,
        "farmer_id": snapshot.farmer_id,
        "provider": snapshot.provider,
        "provider_dataset": snapshot.provider_dataset,
        "snapshot_type": snapshot.snapshot_type,
        "status": snapshot.status,
        "latitude": _json_number(snapshot.latitude),
        "longitude": _json_number(snapshot.longitude),
        "depth_layer": snapshot.depth_layer,
        "resolution_meters": snapshot.resolution_meters,
        "confidence": snapshot.confidence,
        "observed_at": _iso_datetime(snapshot.observed_at),
        "fetched_at": _iso_datetime(snapshot.fetched_at),
        "expires_at": _iso_datetime(snapshot.expires_at),
        "ph": _json_number(snapshot.ph),
        "organic_carbon": _json_number(snapshot.organic_carbon),
        "nitrogen": _json_number(snapshot.nitrogen),
        "clay_percent": _json_number(snapshot.clay_percent),
        "silt_percent": _json_number(snapshot.silt_percent),
        "sand_percent": _json_number(snapshot.sand_percent),
        "bulk_density": _json_number(snapshot.bulk_density),
        "cec": _json_number(snapshot.cec),
        "surface_soil_moisture": _json_number(snapshot.surface_soil_moisture),
        "root_zone_soil_moisture": _json_number(snapshot.root_zone_soil_moisture),
        "soil_temperature_c": _json_number(snapshot.soil_temperature_c),
        "evapotranspiration_mm": _json_number(snapshot.evapotranspiration_mm),
        "normalized_values": snapshot.normalized_values or {},
        "raw_payload": snapshot.raw_payload or {},
        "metadata": snapshot.metadata_ or {},
        "error_message": snapshot.error_message,
        "created_at": _iso_datetime(snapshot.created_at),
        "updated_at": _iso_datetime(snapshot.updated_at),
    }


def _parcel_for_soil_enrichment(db: Session, *, tenant_id: str, parcel_id: uuid.UUID):
    from app.modules.farmer.models import Parcel

    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == tenant_id, Parcel.status != "ARCHIVED").first()
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    return parcel


# --- API Router ---

router = APIRouter(prefix="/api/v1/soil-profiles", tags=["soil-profiles"])


@router.get("/enrichments/source-contract")
def soil_enrichment_source_contract():
    """Describe supported soil enrichment source families and provenance expectations."""
    return {
        "schema_version": "soil_enrichment_sources.v1",
        "sources": SOIL_ENRICHMENT_SOURCE_REGISTRY,
        "guidance": {
            "android_calls_provider_directly": False,
            "admin_map_capture_allowed": True,
            "slusi_scraping_allowed_by_default": False,
            "preferred_baseline_order": ["SOILGRIDS", "SHC_SLUSI", "IN_HOUSE_SATELLITE"],
            "dynamic_moisture_sources": ["OPEN_METEO", "IN_HOUSE_SATELLITE"],
        },
    }


@router.get("/infer/{district_name}", response_model=InferredSoilResponse)
def infer_soil_from_district(
    district_name: str,
):
    """Infer soil type from district name (no farmer input needed).

    Uses published district-level soil data from ICAR/SHC aggregates.
    Returns: soil type, typical pH, texture, confidence level.
    """
    key = district_name.upper().strip()
    defaults = UP_DISTRICT_SOIL_DEFAULTS.get(key, UP_DISTRICT_SOIL_DEFAULTS["_DEFAULT"])
    soil_code = defaults["type"]

    return InferredSoilResponse(
        district_name=district_name,
        inferred_soil_type=soil_code,
        inferred_soil_type_name=SOIL_TYPE_NAMES.get(soil_code, soil_code),
        typical_ph_range=defaults["ph"],
        typical_texture=defaults["texture"],
        confidence=defaults["confidence"],
        description=SOIL_TYPE_DESCRIPTIONS.get(soil_code, ""),
    )


@router.post("/enrichments/soilgrids/fetch", response_model=SoilEnrichmentSnapshotResponse, status_code=201)
def fetch_soilgrids_baseline_snapshot(
    body: SoilGridsFetchRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Fetch/normalize a SoilGrids baseline snapshot for a parcel.

    Regression and scheduled jobs may pass provider_payload to avoid live network.
    Set use_live_provider=true only when backend provider access is intentionally enabled.
    """
    from app.modules.farmer.soilgrids_service import (
        fetch_soilgrids_payload,
        normalize_soilgrids_payload,
        resolve_parcel_soilgrids_coordinate,
    )

    parcel = _parcel_for_soil_enrichment(db, tenant_id=x_tenant_id, parcel_id=body.parcel_id)
    try:
        coordinate = resolve_parcel_soilgrids_coordinate(db, parcel)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    if body.provider_payload is not None:
        provider_payload = body.provider_payload
    elif body.use_live_provider:
        try:
            provider_payload = fetch_soilgrids_payload(coordinate.latitude, coordinate.longitude, depth_layer=body.depth_layer)
        except Exception as exc:
            raise HTTPException(502, f"SoilGrids provider fetch failed: {exc}")
    else:
        raise HTTPException(400, "provider_payload is required unless use_live_provider=true")

    normalized = normalize_soilgrids_payload(
        provider_payload,
        latitude=coordinate.latitude,
        longitude=coordinate.longitude,
        depth_layer=body.depth_layer,
        coordinate_source=coordinate.source,
    )
    timestamp = datetime.now(timezone.utc)
    snapshot = SoilEnrichmentSnapshot(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        parcel_id=parcel.id,
        farmer_id=parcel.farmer_id,
        provider=normalized["provider"],
        provider_dataset=normalized.get("provider_dataset"),
        snapshot_type=normalized["snapshot_type"],
        status=normalized["status"],
        latitude=normalized.get("latitude"),
        longitude=normalized.get("longitude"),
        depth_layer=normalized.get("depth_layer"),
        resolution_meters=normalized.get("resolution_meters"),
        confidence=normalized.get("confidence"),
        observed_at=normalized.get("observed_at") or timestamp,
        fetched_at=normalized.get("fetched_at") or timestamp,
        ph=normalized.get("ph"),
        organic_carbon=normalized.get("organic_carbon"),
        nitrogen=normalized.get("nitrogen"),
        clay_percent=normalized.get("clay_percent"),
        silt_percent=normalized.get("silt_percent"),
        sand_percent=normalized.get("sand_percent"),
        bulk_density=normalized.get("bulk_density"),
        cec=normalized.get("cec"),
        normalized_values=normalized.get("normalized_values") or {},
        raw_payload=normalized.get("raw_payload") or {},
        metadata_=_soil_enrichment_source_metadata(normalized["provider"], normalized.get("metadata") or {}),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _soil_enrichment_payload(snapshot)


@router.post("/enrichments/shc-slusi/manual-capture", response_model=SoilEnrichmentSnapshotResponse, status_code=201)
def create_shc_slusi_manual_capture_snapshot(
    body: ShcSlusiManualCaptureRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Store an admin-observed SHC/SLUSI visual-layer soil baseline.

    This endpoint intentionally does not scrape/fetch SLUSI data. It records a trusted manual
    observation or future import row from the government visualisation with explicit provenance.
    """
    parcel = _parcel_for_soil_enrichment(db, tenant_id=x_tenant_id, parcel_id=body.parcel_id)
    timestamp = datetime.now(timezone.utc)
    parameter_key = body.parameter.strip().upper().replace(" ", "_")
    normalized_values = {
        "state": body.state.strip().upper(),
        "district": body.district.strip().upper(),
        "parameter": parameter_key,
    }
    if body.cycle:
        normalized_values["cycle"] = body.cycle.strip()
    if body.status_class:
        normalized_values["status_class"] = body.status_class.strip().upper()
    if body.value_text:
        normalized_values["value_text"] = body.value_text.strip()
    if body.unit:
        normalized_values["unit"] = body.unit.strip()

    metadata = _soil_enrichment_source_metadata("SHC_SLUSI", {
        "capture_method": "ADMIN_VISUAL_CAPTURE",
        "source_url": body.source_url,
        "notes": body.notes,
    })
    snapshot = SoilEnrichmentSnapshot(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        parcel_id=parcel.id,
        farmer_id=parcel.farmer_id,
        provider="SHC_SLUSI",
        provider_dataset="soilhealth.dac.gov.in/slusi-visualisation",
        snapshot_type="BASELINE",
        status="AVAILABLE",
        depth_layer=body.depth_layer,
        confidence="GOVT_VISUAL_LAYER",
        observed_at=body.observed_at or timestamp,
        fetched_at=timestamp,
        normalized_values=normalized_values,
        raw_payload=body.raw_payload or {},
        metadata_=metadata,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _soil_enrichment_payload(snapshot)


@router.post("/enrichments/shc-slusi/point-capture", response_model=SoilEnrichmentSnapshotResponse, status_code=201)
def create_shc_slusi_point_capture_snapshot(
    body: ShcSlusiPointCaptureRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Store a full SHC/SLUSI point popup or WMS GetFeatureInfo observation.

    This records the richer point-level values visible after zoom/click in the public UI.
    It still does not fetch/scrape the government service directly.
    """
    parcel = _parcel_for_soil_enrichment(db, tenant_id=x_tenant_id, parcel_id=body.parcel_id)
    timestamp = datetime.now(timezone.utc)
    numeric_values = {
        "n_kg_ha": body.n_kg_ha,
        "p_kg_ha": body.p_kg_ha,
        "k_kg_ha": body.k_kg_ha,
        "b_ppm": body.b_ppm,
        "fe_ppm": body.fe_ppm,
        "zn_ppm": body.zn_ppm,
        "cu_ppm": body.cu_ppm,
        "s_ppm": body.s_ppm,
        "organic_carbon_percent": body.organic_carbon_percent,
        "ph": body.ph,
        "ec_ds_m": body.ec_ds_m,
        "mn_ppm": body.mn_ppm,
    }
    land_properties = {
        "depth_50k": body.depth_50k,
        "slope_50k": body.slope_50k,
        "erosion_50k": body.erosion_50k,
        "texture_50k": body.texture_50k,
        "lcc_50k": body.lcc_50k,
        "lic_50k": body.lic_50k,
        "hsg_50k": body.hsg_50k,
        "cec_text": body.cec_text,
        "soil_code": body.soil_code,
    }
    normalized_values = {
        "state": body.state.strip().upper(),
        "district": body.district.strip().upper(),
        "capture_granularity": "POINT_POPUP",
        "nutrients": {key: value for key, value in numeric_values.items() if value is not None},
        "soil_land_properties": {key: value for key, value in land_properties.items() if value not in (None, "")},
    }
    if body.village:
        normalized_values["village"] = body.village.strip()
    if body.cycle:
        normalized_values["cycle"] = body.cycle.strip()

    metadata = _soil_enrichment_source_metadata("SHC_SLUSI", {
        "capture_method": "ADMIN_POINT_POPUP_CAPTURE",
        "source_granularity": "POINT_POPUP",
        "observed_transport": "OGC_WMS_GETFEATUREINFO_JSON",
        "source_url": body.source_url,
        "wms_url": body.wms_url,
        "notes": body.notes,
    })
    snapshot = SoilEnrichmentSnapshot(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        parcel_id=parcel.id,
        farmer_id=parcel.farmer_id,
        provider="SHC_SLUSI",
        provider_dataset="soilhealth.dac.gov.in/slusi-visualisation/wms",
        snapshot_type="BASELINE",
        status="AVAILABLE",
        latitude=body.latitude,
        longitude=body.longitude,
        depth_layer="point_popup",
        confidence="GOVT_POINT_POPUP",
        observed_at=body.observed_at or timestamp,
        fetched_at=timestamp,
        ph=body.ph,
        organic_carbon=body.organic_carbon_percent,
        nitrogen=body.n_kg_ha,
        cec=body.cec_text if isinstance(body.cec_text, (int, float)) else None,
        normalized_values=normalized_values,
        raw_payload=body.raw_payload or {},
        metadata_=metadata,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _soil_enrichment_payload(snapshot)


@router.post("/enrichments", response_model=SoilEnrichmentSnapshotResponse, status_code=201)
def create_soil_enrichment_snapshot(
    body: SoilEnrichmentSnapshotCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Store a provider-derived soil baseline/moisture snapshot for a parcel."""
    parcel = _parcel_for_soil_enrichment(db, tenant_id=x_tenant_id, parcel_id=body.parcel_id)
    farmer_id = body.farmer_id or parcel.farmer_id
    if farmer_id != parcel.farmer_id:
        raise HTTPException(400, "farmer_id must match parcel farmer_id")

    timestamp = datetime.now(timezone.utc)
    snapshot = SoilEnrichmentSnapshot(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        parcel_id=body.parcel_id,
        farmer_id=farmer_id,
        provider=body.provider.strip().upper(),
        provider_dataset=body.provider_dataset,
        snapshot_type=body.snapshot_type.strip().upper(),
        status=body.status.strip().upper(),
        latitude=body.latitude,
        longitude=body.longitude,
        depth_layer=body.depth_layer,
        resolution_meters=body.resolution_meters,
        confidence=body.confidence,
        observed_at=body.observed_at or body.fetched_at or timestamp,
        fetched_at=body.fetched_at or timestamp,
        expires_at=body.expires_at,
        ph=body.ph,
        organic_carbon=body.organic_carbon,
        nitrogen=body.nitrogen,
        clay_percent=body.clay_percent,
        silt_percent=body.silt_percent,
        sand_percent=body.sand_percent,
        bulk_density=body.bulk_density,
        cec=body.cec,
        surface_soil_moisture=body.surface_soil_moisture,
        root_zone_soil_moisture=body.root_zone_soil_moisture,
        soil_temperature_c=body.soil_temperature_c,
        evapotranspiration_mm=body.evapotranspiration_mm,
        normalized_values=body.normalized_values or {},
        raw_payload=body.raw_payload or {},
        metadata_=_soil_enrichment_source_metadata(body.provider, body.metadata or {}),
        error_message=body.error_message,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _soil_enrichment_payload(snapshot)


@router.get("/enrichments/latest", response_model=SoilEnrichmentSnapshotResponse)
def latest_soil_enrichment_snapshot(
    parcel_id: uuid.UUID = Query(...),
    provider: Optional[str] = Query(None),
    snapshot_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return the latest provider-derived soil enrichment for a parcel."""
    _parcel_for_soil_enrichment(db, tenant_id=x_tenant_id, parcel_id=parcel_id)
    query = db.query(SoilEnrichmentSnapshot).filter(
        SoilEnrichmentSnapshot.tenant_id == x_tenant_id,
        SoilEnrichmentSnapshot.parcel_id == parcel_id,
    )
    if provider:
        query = query.filter(SoilEnrichmentSnapshot.provider == provider.strip().upper())
    if snapshot_type:
        query = query.filter(SoilEnrichmentSnapshot.snapshot_type == snapshot_type.strip().upper())
    snapshot = query.order_by(SoilEnrichmentSnapshot.observed_at.desc().nullslast(), SoilEnrichmentSnapshot.fetched_at.desc()).first()
    if not snapshot:
        raise HTTPException(404, "Soil enrichment snapshot not found")
    return _soil_enrichment_payload(snapshot)


@router.get("/enrichments", response_model=list[SoilEnrichmentSnapshotResponse])
def list_soil_enrichment_snapshots(
    parcel_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    provider: Optional[str] = Query(None),
    snapshot_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List provider-derived soil enrichment snapshots."""
    query = db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == x_tenant_id)
    if parcel_id:
        query = query.filter(SoilEnrichmentSnapshot.parcel_id == parcel_id)
    if farmer_id:
        query = query.filter(SoilEnrichmentSnapshot.farmer_id == farmer_id)
    if provider:
        query = query.filter(SoilEnrichmentSnapshot.provider == provider.strip().upper())
    if snapshot_type:
        query = query.filter(SoilEnrichmentSnapshot.snapshot_type == snapshot_type.strip().upper())
    return [_soil_enrichment_payload(row) for row in query.order_by(SoilEnrichmentSnapshot.observed_at.desc().nullslast(), SoilEnrichmentSnapshot.fetched_at.desc()).limit(limit).all()]


@router.post("/enrichments/jobs/audit", response_model=SoilEnrichmentJobAuditResponse, status_code=201)
def record_soil_enrichment_job_audit(
    body: SoilEnrichmentJobAuditCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Record a backend soil enrichment job attempt."""
    event = SoilEnrichmentJobAudit(
        tenant_id=x_tenant_id,
        farmer_id=body.farmer_id,
        parcel_id=body.parcel_id,
        project_id=body.project_id,
        job_type=body.job_type,
        provider=body.provider.strip().upper() if body.provider else None,
        status=body.status,
        attempt_count=body.attempt_count,
        reason=body.reason,
        error_code=body.error_code,
        metadata_=body.metadata or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _soil_enrichment_job_audit_payload(event)


@router.get("/enrichments/jobs/audit")
def list_soil_enrichment_job_audit(
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    job_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    query = db.query(SoilEnrichmentJobAudit).filter(SoilEnrichmentJobAudit.tenant_id == x_tenant_id)
    if farmer_id:
        query = query.filter(SoilEnrichmentJobAudit.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(SoilEnrichmentJobAudit.parcel_id == parcel_id)
    if project_id:
        query = query.filter(SoilEnrichmentJobAudit.project_id == project_id)
    if job_type:
        query = query.filter(SoilEnrichmentJobAudit.job_type == job_type.strip().upper())
    if status:
        query = query.filter(SoilEnrichmentJobAudit.status == status.strip().upper())

    events = query.order_by(SoilEnrichmentJobAudit.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "soil_enrichment_job_audit.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "project_id": str(project_id) if project_id else None,
            "job_type": job_type.strip().upper() if job_type else None,
            "status": status.strip().upper() if status else None,
            "limit": limit,
        },
        "count": len(events),
        "events": [_soil_enrichment_job_audit_payload(event) for event in events],
    }


@router.get("/enrichments/queue")
def list_soil_enrichment_queue(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    missing: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return backend operational queue for soil enrichment fetch jobs.

    This endpoint is intentionally provider-neutral. It tells admin/jobs which
    farmer/parcel records have enough location context for backend enrichment
    and which snapshot families are currently missing.
    """
    from app.modules.farmer.models import Farmer, Parcel
    from app.modules.farmer.api import _soil_enrichment_snapshot_counts

    missing_filter = missing.strip().upper() if missing else None
    allowed_missing = {None, "BASELINE", "MOISTURE", "ANY"}
    if missing_filter not in allowed_missing:
        raise HTTPException(400, "missing must be BASELINE, MOISTURE, or ANY")

    parcel_query = db.query(Parcel).filter(
        Parcel.tenant_id == x_tenant_id,
        Parcel.status != "ARCHIVED",
    )
    if project_id:
        parcel_query = parcel_query.filter(Parcel.project_id == project_id)
    if farmer_id:
        parcel_query = parcel_query.filter(Parcel.farmer_id == farmer_id)

    parcels = parcel_query.order_by(Parcel.updated_at.desc(), Parcel.created_at.desc()).limit(limit).all()
    farmer_ids = {parcel.farmer_id for parcel in parcels if parcel.farmer_id}
    farmers = {
        farmer.id: farmer
        for farmer in db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id, Farmer.id.in_(farmer_ids)).all()
    } if farmer_ids else {}

    rows = []
    reason_counts = {
        "MISSING_BASELINE": 0,
        "MISSING_MOISTURE": 0,
        "READY_FOR_BASELINE_FETCH": 0,
        "READY_FOR_MOISTURE_FETCH": 0,
        "LOCATION_READY": 0,
    }

    for parcel in parcels:
        farmer = farmers.get(parcel.farmer_id)
        has_location = (
            (parcel.centroid_lat is not None and parcel.centroid_lng is not None)
            or parcel.geometry_source in {"PIN_DROP", "GPS_WALK", "SATELLITE", "MANUAL_DRAW"}
            or bool(parcel.village_id or parcel.village_name_manual or parcel.pin_code)
        )
        if not has_location:
            continue

        counts = _soil_enrichment_snapshot_counts(db, tenant_id=x_tenant_id, farmer_id=parcel.farmer_id)
        missing_baseline = counts["baseline"] == 0
        missing_moisture = counts["moisture"] == 0

        if missing_filter == "BASELINE" and not missing_baseline:
            continue
        if missing_filter == "MOISTURE" and not missing_moisture:
            continue
        if missing_filter == "ANY" and not (missing_baseline or missing_moisture):
            continue

        reasons = []
        if missing_baseline:
            reasons.append("MISSING_BASELINE")
            reasons.append("READY_FOR_BASELINE_FETCH")
        if missing_moisture:
            reasons.append("MISSING_MOISTURE")
            reasons.append("READY_FOR_MOISTURE_FETCH")
        reasons.append("LOCATION_READY")

        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        rows.append({
            "farmer": {
                "id": str(parcel.farmer_id),
                "display_name": farmer.display_name if farmer else None,
                "mobile_number": farmer.mobile_number if farmer else None,
                "village_name_manual": farmer.village_name_manual if farmer else None,
                "pin_code": farmer.pin_code if farmer else None,
            },
            "parcel": {
                "id": str(parcel.id),
                "project_id": str(parcel.project_id) if parcel.project_id else None,
                "village_id": str(parcel.village_id) if parcel.village_id else None,
                "village_name_manual": parcel.village_name_manual,
                "pin_code": parcel.pin_code,
                "geometry_source": parcel.geometry_source,
                "has_centroid": parcel.centroid_lat is not None and parcel.centroid_lng is not None,
            },
            "snapshot_counts": counts,
            "missing_baseline": missing_baseline,
            "missing_moisture": missing_moisture,
            "reasons": reasons,
            "recommended_jobs": [
                job for job, should_run in [
                    ("FETCH_SOIL_BASELINE", missing_baseline),
                    ("FETCH_SOIL_MOISTURE", missing_moisture),
                ] if should_run
            ],
        })

    return {
        "schema_version": "soil_enrichment_queue.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "missing": missing_filter,
            "limit": limit,
        },
        "count": len(rows),
        "reason_counts": reason_counts,
        "items": rows,
    }


@router.get("/enrichments/summary")
def get_soil_enrichment_summary(
    parcel_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    provider: Optional[str] = Query(None),
    snapshot_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Return grouped soil enrichment snapshot summary for Android/admin.

    Android should use this endpoint to understand whether backend-owned
    SoilGrids/SLUSI/soil-moisture enrichment is available for a farmer/parcel,
    instead of grouping raw snapshots locally.
    """
    if not parcel_id and not farmer_id:
        raise HTTPException(400, "parcel_id or farmer_id is required")

    query = db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == x_tenant_id)
    if parcel_id:
        query = query.filter(SoilEnrichmentSnapshot.parcel_id == parcel_id)
    if farmer_id:
        query = query.filter(SoilEnrichmentSnapshot.farmer_id == farmer_id)
    if provider:
        query = query.filter(SoilEnrichmentSnapshot.provider == provider.strip().upper())
    if snapshot_type:
        query = query.filter(SoilEnrichmentSnapshot.snapshot_type == snapshot_type.strip().upper())

    snapshots = query.order_by(
        SoilEnrichmentSnapshot.observed_at.desc().nullslast(),
        SoilEnrichmentSnapshot.fetched_at.desc(),
    ).limit(limit).all()

    summary = _soil_enrichment_summary_payload(snapshots)
    return {
        "schema_version": "soil_enrichment_summary.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "parcel_id": str(parcel_id) if parcel_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "provider": provider.strip().upper() if provider else None,
            "snapshot_type": snapshot_type.strip().upper() if snapshot_type else None,
            "limit": limit,
        },
        **summary,
    }


@router.post("", response_model=SoilProfileResponse, status_code=201)
def create_soil_profile(
    body: SoilProfileCreate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
):
    """Create or update soil profile for a parcel.

    Supports 3 tiers:
    - Tier 1: Just soil_type_code (inferred from geography)
    - Tier 2: + soil_texture + soil_color (farmer observation)
    - Tier 3: + all 12 SHC parameters (lab test data)
    """
    inferred_project_id = _infer_soil_profile_project_id(db, tenant_id=x_tenant_id, parcel_id=body.parcel_id, farmer_id=body.farmer_id)
    _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_textures", value=body.soil_texture, path="soil_texture")
    _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_colors", value=body.soil_color, path="soil_color")
    _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_data_sources", value=body.data_source, path="data_source")
    _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_types", value=body.soil_type_code, path="soil_type_code")

    profile = SoilProfile(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        parcel_id=body.parcel_id,
        farmer_id=body.farmer_id,
        test_date=body.test_date or date.today(),
        lab_name=body.lab_name,
        shc_card_number=body.shc_card_number,
        soil_type_code=body.soil_type_code,
        soil_texture=body.soil_texture,
        soil_color=body.soil_color,
        nitrogen_n=body.nitrogen_n,
        phosphorus_p=body.phosphorus_p,
        potassium_k=body.potassium_k,
        sulphur_s=body.sulphur_s,
        zinc_zn=body.zinc_zn,
        iron_fe=body.iron_fe,
        copper_cu=body.copper_cu,
        manganese_mn=body.manganese_mn,
        boron_bo=body.boron_bo if body.boron_bo is not None else body.boron_b,
        ph=body.ph,
        ec=body.ec,
        organic_carbon_oc=body.organic_carbon_oc,
        data_source=body.data_source,
        notes=body.notes,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=SoilProfileResponse)
def update_soil_profile(
    profile_id: uuid.UUID,
    body: SoilProfileUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Update mutable soil profile fields for backend-driven profile maintenance."""
    profile = db.query(SoilProfile).filter(SoilProfile.id == profile_id, SoilProfile.tenant_id == x_tenant_id).first()
    if not profile:
        raise HTTPException(404, "Soil profile not found")

    values = _model_patch_values(body)
    if not values:
        raise HTTPException(400, "At least one soil profile field must be provided")

    inferred_project_id = _infer_soil_profile_project_id(db, tenant_id=x_tenant_id, parcel_id=profile.parcel_id, farmer_id=profile.farmer_id)
    if "soil_texture" in values:
        _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_textures", value=values.get("soil_texture"), path="soil_texture")
    if "soil_color" in values:
        _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_colors", value=values.get("soil_color"), path="soil_color")
    if "data_source" in values:
        _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_data_sources", value=values.get("data_source"), path="data_source")
    if "soil_type_code" in values:
        _validate_profile_option_value(db, tenant_id=x_tenant_id, project_id=inferred_project_id, option_set="soil_types", value=values.get("soil_type_code"), path="soil_type_code")

    for field in ["soil_type_code", "soil_texture", "soil_color", "test_date", "lab_name", "shc_card_number", "nitrogen_n", "phosphorus_p", "potassium_k", "sulphur_s", "zinc_zn", "iron_fe", "copper_cu", "manganese_mn", "ph", "ec", "organic_carbon_oc", "data_source", "notes"]:
        if field in values:
            setattr(profile, field, values[field])
    if "boron_bo" in values or "boron_b" in values:
        profile.boron_bo = values.get("boron_bo") if "boron_bo" in values else values.get("boron_b")
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=list[SoilProfileResponse])
def list_soil_profiles(
    parcel_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List soil profiles for a parcel or farmer."""
    query = db.query(SoilProfile).filter(SoilProfile.tenant_id == x_tenant_id)
    if parcel_id:
        query = query.filter(SoilProfile.parcel_id == parcel_id)
    if farmer_id:
        query = query.filter(SoilProfile.farmer_id == farmer_id)
    return query.order_by(SoilProfile.test_date.desc()).all()
