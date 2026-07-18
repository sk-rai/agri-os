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
from sqlalchemy import Column, String, Date, DECIMAL, Text, ForeignKey, Index, DateTime, Boolean
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


# --- API Schemas ---

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


def _validate_profile_option_value(db: Session, *, tenant_id: str, option_set: str, value: Optional[str], path: str) -> None:
    """Reject stale Android-hardcoded values that are no longer valid for backend-owned profile option sets."""
    if value is None or value == "":
        return
    from app.modules.workflow.forms import _effective_profile_option_registry

    registry = _effective_profile_option_registry(db, tenant_id=tenant_id)
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


# --- API Router ---

router = APIRouter(prefix="/api/v1/soil-profiles", tags=["soil-profiles"])


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
    _validate_profile_option_value(db, tenant_id=x_tenant_id, option_set="soil_textures", value=body.soil_texture, path="soil_texture")
    _validate_profile_option_value(db, tenant_id=x_tenant_id, option_set="soil_colors", value=body.soil_color, path="soil_color")
    _validate_profile_option_value(db, tenant_id=x_tenant_id, option_set="soil_data_sources", value=body.data_source, path="data_source")

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
