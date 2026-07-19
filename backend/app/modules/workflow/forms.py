"""Schema-driven form API.

GET /api/v1/forms/{form_id} — Returns form schema for client-side rendering.

Form schemas are:
- Flat (list of fields)
- Support depends_on relationships (cascading dropdowns)
- Support dynamic source with {field_id} variable substitution
- Cacheable with version field for invalidation
- i18n: all translatable strings are Map<lang_code, text>
  Android resolves: map[currentLanguage] ?: map["en"]
"""

from copy import deepcopy
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.farmer.models import Project, Tenant

router = APIRouter(prefix="/api/v1/forms", tags=["forms"])


# --- i18n: all translatable fields use dict[str, str] ---
# Example: {"en": "Crop", "hi": "फसल", "bn": "ফসল"}
# Android resolves: map[currentLanguageCode] ?: map["en"]

class FormFieldOption(BaseModel):
    value: str
    label: dict[str, str]  # {"en": "...", "hi": "..."}


class FormField(BaseModel):
    id: str
    type: str  # text, number, date, dropdown, single_select, multi_select, GPS_POINT, GPS_POLYGON, PHOTO, SECTION
    label: dict[str, str]
    required: bool = False
    source: Optional[str] = None  # API endpoint, "local_*" for Room data, or "profile_options.*" option set
    options: Optional[list[FormFieldOption]] = None
    depends_on: Optional[str] = None
    depends_on_value: Optional[str] = None
    default_value: Optional[str] = None
    placeholder: Optional[dict[str, str]] = None
    validation: Optional[dict] = None
    hint: Optional[dict[str, str]] = None
    canonical_field: Optional[str] = None
    android_hint: Optional[dict] = None
    capture_modes: Optional[list[str]] = None
    output_format: Optional[str] = None
    min_points: Optional[int] = None
    accuracy_required_meters: Optional[float] = None
    allow_offline_capture: bool = True


class FormSchema(BaseModel):
    form_id: str
    version: str
    title: dict[str, str]
    description: Optional[dict[str, str]] = None
    fields: list[FormField]
    submit_endpoint: str
    submit_method: str = "POST"
    submit_label: Optional[dict[str, str]] = None


class ProfileOptionSet(BaseModel):
    option_set: str
    version: str = "1.0.0"
    title: dict[str, str]
    options: list[FormFieldOption]
    metadata: dict = {}


PROFILE_OPTION_REGISTRY = {
    "seasons": ProfileOptionSet(option_set="seasons", title={"en": "Seasons", "hi": "Seasons"}, options=[FormFieldOption(value="KHARIF", label={"en": "Kharif", "hi": "Kharif"}), FormFieldOption(value="RABI", label={"en": "Rabi", "hi": "Rabi"}), FormFieldOption(value="ZAID", label={"en": "Zaid", "hi": "Zaid"})]),
    "land_units": ProfileOptionSet(option_set="land_units", title={"en": "Land Units", "hi": "Land Units"}, options=[FormFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}), FormFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}), FormFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}), FormFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}), FormFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}), FormFieldOption(value="GUNTHA", label={"en": "Guntha", "hi": "Guntha"})]),
    "ownership_types": ProfileOptionSet(option_set="ownership_types", title={"en": "Ownership Types", "hi": "Ownership Types"}, options=[FormFieldOption(value="OWNED", label={"en": "Owned", "hi": "Owned"}), FormFieldOption(value="PART_OWNER", label={"en": "Part owner", "hi": "Part owner"}), FormFieldOption(value="LEASED", label={"en": "Leased", "hi": "Leased"}), FormFieldOption(value="SHARED", label={"en": "Shared", "hi": "Shared"}), FormFieldOption(value="SHARECROP", label={"en": "Sharecrop", "hi": "Sharecrop"}), FormFieldOption(value="FAMILY", label={"en": "Family", "hi": "Family"})]),
    "irrigation_sources": ProfileOptionSet(option_set="irrigation_sources", title={"en": "Irrigation Sources", "hi": "Irrigation Sources"}, options=[FormFieldOption(value="TUBEWELL_DIESEL", label={"en": "Tubewell (Diesel)", "hi": "Tubewell (Diesel)"}), FormFieldOption(value="TUBEWELL_ELECTRIC", label={"en": "Tubewell (Electric)", "hi": "Tubewell (Electric)"}), FormFieldOption(value="CANAL", label={"en": "Canal", "hi": "Canal"}), FormFieldOption(value="PURCHASED_WATER", label={"en": "Purchased Water", "hi": "Purchased Water"}), FormFieldOption(value="RAIN_FED", label={"en": "Rain-fed", "hi": "Rain-fed"}), FormFieldOption(value="POND_TANK", label={"en": "Pond/Tank", "hi": "Pond/Tank"}), FormFieldOption(value="RIVER_STREAM", label={"en": "River/Stream", "hi": "River/Stream"})]),
    "geometry_sources": ProfileOptionSet(option_set="geometry_sources", title={"en": "GPS Capture Modes", "hi": "GPS Capture Modes"}, options=[FormFieldOption(value="NONE", label={"en": "No GPS", "hi": "No GPS"}), FormFieldOption(value="PIN_DROP", label={"en": "Pin drop", "hi": "Pin drop"}), FormFieldOption(value="PIN_CORNERS", label={"en": "Pin corners", "hi": "Pin corners"}), FormFieldOption(value="GPS_WALK", label={"en": "GPS walk", "hi": "GPS walk"})]),
    "soil_types": ProfileOptionSet(option_set="soil_types", title={"en": "Soil Types", "hi": "Soil Types"}, options=[FormFieldOption(value="ALLUVIAL", label={"en": "Alluvial Soil", "hi": "Alluvial Soil"}), FormFieldOption(value="BLACK_COTTON", label={"en": "Black Cotton Soil", "hi": "Black Cotton Soil"}), FormFieldOption(value="RED", label={"en": "Red Soil", "hi": "Red Soil"}), FormFieldOption(value="LATERITE", label={"en": "Laterite Soil", "hi": "Laterite Soil"}), FormFieldOption(value="DESERT", label={"en": "Desert Soil", "hi": "Desert Soil"}), FormFieldOption(value="MOUNTAIN", label={"en": "Mountain Soil", "hi": "Mountain Soil"}), FormFieldOption(value="SALINE_ALKALINE", label={"en": "Saline/Alkaline Soil", "hi": "Saline/Alkaline Soil"})]),
    "soil_textures": ProfileOptionSet(option_set="soil_textures", title={"en": "Soil Textures", "hi": "Soil Textures"}, options=[FormFieldOption(value="SANDY", label={"en": "Sandy", "hi": "Sandy"}), FormFieldOption(value="LOAM", label={"en": "Loam", "hi": "Loam"}), FormFieldOption(value="LOAMY", label={"en": "Loamy", "hi": "Loamy"}), FormFieldOption(value="CLAY", label={"en": "Clay", "hi": "Clay"}), FormFieldOption(value="SANDY_LOAM", label={"en": "Sandy Loam", "hi": "Sandy Loam"}), FormFieldOption(value="CLAY_LOAM", label={"en": "Clay Loam", "hi": "Clay Loam"})]),
    "soil_colors": ProfileOptionSet(option_set="soil_colors", title={"en": "Soil Colors", "hi": "Soil Colors"}, options=[FormFieldOption(value="BROWN", label={"en": "Brown", "hi": "Brown"}), FormFieldOption(value="DARK_BROWN", label={"en": "Dark brown", "hi": "Dark brown"}), FormFieldOption(value="LIGHT_BROWN", label={"en": "Light brown", "hi": "Light brown"}), FormFieldOption(value="REDDISH", label={"en": "Reddish", "hi": "Reddish"}), FormFieldOption(value="BLACK", label={"en": "Black", "hi": "Black"}), FormFieldOption(value="GREY", label={"en": "Grey", "hi": "Grey"})]),
    "soil_data_sources": ProfileOptionSet(option_set="soil_data_sources", title={"en": "Soil Data Sources", "hi": "Soil Data Sources"}, options=[FormFieldOption(value="MANUAL", label={"en": "Manual Observation", "hi": "Manual Observation"}), FormFieldOption(value="INFERRED", label={"en": "Inferred", "hi": "Inferred"}), FormFieldOption(value="SHC_CARD", label={"en": "Soil Health Card", "hi": "Soil Health Card"}), FormFieldOption(value="LAB_REPORT", label={"en": "Lab Report", "hi": "Lab Report"})]),
    "languages": ProfileOptionSet(option_set="languages", title={"en": "Languages", "hi": "Languages"}, options=[FormFieldOption(value="en", label={"en": "English", "hi": "English"}), FormFieldOption(value="hi", label={"en": "Hindi", "hi": "Hindi"}), FormFieldOption(value="kn", label={"en": "Kannada", "hi": "Kannada"}), FormFieldOption(value="ta", label={"en": "Tamil", "hi": "Tamil"}), FormFieldOption(value="te", label={"en": "Telugu", "hi": "Telugu"}), FormFieldOption(value="mr", label={"en": "Marathi", "hi": "Marathi"})]),
    "assistance_modes": ProfileOptionSet(option_set="assistance_modes", title={"en": "Assistance Modes", "hi": "Assistance Modes"}, options=[FormFieldOption(value="SELF_SERVICE", label={"en": "Self service", "hi": "Self service"}), FormFieldOption(value="DEALER_ASSISTED", label={"en": "Dealer assisted", "hi": "Dealer assisted"}), FormFieldOption(value="FIELD_AGENT_ASSISTED", label={"en": "Field-agent assisted", "hi": "Field-agent assisted"}), FormFieldOption(value="AGRONOMIST_ASSISTED", label={"en": "Agronomist assisted", "hi": "Agronomist assisted"})]),
}



def _option_set_from_config(option_set: str, payload: dict, source: str) -> ProfileOptionSet:
    """Build an option set from tenant/project config while preserving a stable shape."""
    base = PROFILE_OPTION_REGISTRY.get(option_set)
    if not isinstance(payload, dict):
        payload = {}

    raw_options = payload.get("options")
    if raw_options is None and base:
        options = deepcopy(base.options)
    else:
        options = [FormFieldOption(**item) for item in (raw_options or []) if isinstance(item, dict)]

    title = payload.get("title") or (base.title if base else {"en": option_set.replace("_", " ").title()})
    metadata = deepcopy(base.metadata if base else {})
    if isinstance(payload.get("metadata"), dict):
        metadata.update(payload["metadata"])
    metadata.update({"source": source, "overridden": source != "default"})

    return ProfileOptionSet(
        option_set=option_set,
        version=str(payload.get("version") or (base.version if base else "1.0.0")),
        title=title,
        options=options,
        metadata=metadata,
    )


def _profile_option_overrides(config: Optional[dict]) -> dict:
    if not isinstance(config, dict):
        return {}
    profile_options = config.get("profile_options")
    if not isinstance(profile_options, dict):
        return {}
    overrides = profile_options.get("overrides")
    return overrides if isinstance(overrides, dict) else {}


def _apply_profile_option_overrides(registry: dict[str, ProfileOptionSet], overrides: dict, source: str) -> None:
    for option_set, payload in sorted(overrides.items()):
        registry[option_set] = _option_set_from_config(option_set, payload, source)


def _effective_profile_option_registry(db: Session, *, tenant_id: str, project_id: Optional[uuid.UUID] = None) -> dict[str, ProfileOptionSet]:
    registry = {
        key: _option_set_from_config(key, value.model_dump() if hasattr(value, "model_dump") else value.dict(), "default")
        for key, value in PROFILE_OPTION_REGISTRY.items()
    }

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if tenant:
        _apply_profile_option_overrides(registry, _profile_option_overrides(tenant.config), "tenant")

    if project_id:
        project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id, Project.is_active == True).first()
        if not project:
            raise HTTPException(404, "Project not found")
        _apply_profile_option_overrides(registry, _profile_option_overrides(project.config), "project")

    return registry


# --- Form Definitions ---

FARMER_REGISTRATION_FORM = FormSchema(
    form_id="farmer_registration",
    version="1.0.0",
    title={"en": "Farmer Registration", "hi": "Farmer Registration"},
    description={"en": "Create or update a farmer profile", "hi": "Create or update a farmer profile"},
    submit_endpoint="/api/v1/farmers",
    submit_method="POST",
    submit_label={"en": "Save Farmer", "hi": "Save Farmer"},
    fields=[
        FormField(id="display_name", type="text", label={"en": "Farmer Name", "hi": "Farmer Name"}, required=False, placeholder={"en": "Full name", "hi": "Full name"}, canonical_field="farmer.display_name"),
        FormField(id="mobile_number", type="phone", label={"en": "Mobile Number", "hi": "Mobile Number"}, required=True, placeholder={"en": "+919900000001 or 9900000001", "hi": "+919900000001 or 9900000001"}, validation={"pattern": "^\\+?[0-9]{10,15}$", "min_length": 10}, canonical_field="farmer.mobile_number", android_hint={"keyboard": "phone", "default_country_code": "+91"}),
        FormField(id="village_id", type="dropdown", label={"en": "Village ID", "hi": "Village ID"}, required=False, source="/api/v1/geography/villages", canonical_field="farmer.village_id", android_hint={"manual_fallback_field": "village_name_manual"}),
        FormField(id="village_name_manual", type="text", label={"en": "Village", "hi": "Village"}, required=True, placeholder={"en": "Village name", "hi": "Village name"}, canonical_field="farmer.village_name_manual"),
        FormField(id="pin_code", type="text", label={"en": "PIN Code", "hi": "PIN Code"}, required=False, placeholder={"en": "6-digit PIN code", "hi": "6-digit PIN code"}, validation={"pattern": "^[0-9]{6}$"}, canonical_field="farmer.pin_code", android_hint={"payload_field": "pin_code"}),
        FormField(id="primary_crop_code", type="dropdown", label={"en": "Primary Crop", "hi": "Primary Crop"}, required=False, source="/api/v1/master-data/crops", placeholder={"en": "Select primary crop", "hi": "Select primary crop"}, canonical_field="farmer.primary_crop_code"),
        FormField(id="father_name", type="text", label={"en": "Father/Guardian Name", "hi": "Father/Guardian Name"}, required=False, canonical_field="farmer.father_name"),
        FormField(id="age", type="number", label={"en": "Age", "hi": "Age"}, required=False, validation={"min": 1, "max": 120}, canonical_field="farmer.age"),
        FormField(id="gender", type="single_select", label={"en": "Gender", "hi": "Gender"}, required=False, options=[FormFieldOption(value="MALE", label={"en": "Male", "hi": "Male"}), FormFieldOption(value="FEMALE", label={"en": "Female", "hi": "Female"}), FormFieldOption(value="OTHER", label={"en": "Other", "hi": "Other"})], canonical_field="farmer.gender"),
        FormField(id="aadhaar_number", type="text", label={"en": "Aadhaar Number", "hi": "Aadhaar Number"}, required=False, validation={"pattern": "^[0-9]{12}$"}, canonical_field="farmer.aadhaar_number", android_hint={"sensitive": True, "mask_in_logs": True}),
        FormField(id="total_land_area", type="number", label={"en": "Total Land Area", "hi": "Total Land Area"}, required=False, validation={"min": 0}, canonical_field="farmer.total_land_area"),
        FormField(id="total_land_unit", type="single_select", label={"en": "Land Unit", "hi": "Land Unit"}, source="profile_options.land_units", required=False, default_value="BIGHA", options=[FormFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}), FormFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}), FormFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}), FormFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}), FormFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}), FormFieldOption(value="GUNTHA", label={"en": "Guntha", "hi": "Guntha"})], canonical_field="farmer.total_land_unit"),
        FormField(id="language_preference", type="single_select", label={"en": "Preferred Language", "hi": "Preferred Language"}, source="profile_options.languages", required=False, default_value="hi", options=[FormFieldOption(value="en", label={"en": "English", "hi": "English"}), FormFieldOption(value="hi", label={"en": "Hindi", "hi": "Hindi"}), FormFieldOption(value="kn", label={"en": "Kannada", "hi": "Kannada"}), FormFieldOption(value="ta", label={"en": "Tamil", "hi": "Tamil"}), FormFieldOption(value="te", label={"en": "Telugu", "hi": "Telugu"}), FormFieldOption(value="mr", label={"en": "Marathi", "hi": "Marathi"})], canonical_field="farmer.language_preference"),
        FormField(id="assistance_mode", type="single_select", label={"en": "Assistance Mode", "hi": "Assistance Mode"}, source="profile_options.assistance_modes", required=False, default_value="DEALER_ASSISTED", options=[FormFieldOption(value="SELF_SERVICE", label={"en": "Self service", "hi": "Self service"}), FormFieldOption(value="DEALER_ASSISTED", label={"en": "Dealer assisted", "hi": "Dealer assisted"}), FormFieldOption(value="FIELD_AGENT_ASSISTED", label={"en": "Field-agent assisted", "hi": "Field-agent assisted"}), FormFieldOption(value="AGRONOMIST_ASSISTED", label={"en": "Agronomist assisted", "hi": "Agronomist assisted"})], canonical_field="farmer.enrollment_method", android_hint={"payload_field": "assistance_mode"}),
        FormField(id="enrollment_location", type="GPS_POINT", label={"en": "Enrollment Location", "hi": "Enrollment Location"}, required=False, capture_modes=["PIN_DROP", "CURRENT_LOCATION"], output_format="centroid_lat_lng", accuracy_required_meters=50, canonical_field="farmer.enrollment_gps", hint={"en": "Optional location captured during enrollment", "hi": "Optional location captured during enrollment"}),
    ],
)

PARCEL_REGISTRATION_FORM = FormSchema(
    form_id="parcel_registration",
    version="1.0.0",
    title={"en": "Land Parcel", "hi": "Land Parcel"},
    description={"en": "Register a land parcel with optional GPS", "hi": "Register a land parcel with optional GPS"},
    submit_endpoint="/api/v1/parcels",
    submit_method="POST",
    submit_label={"en": "Save Parcel", "hi": "Save Parcel"},
    fields=[
        FormField(id="farmer_id", type="dropdown", label={"en": "Farmer", "hi": "Farmer"}, required=True, source="local_farmers", canonical_field="parcel.farmer_id"),
        FormField(id="village_id", type="dropdown", label={"en": "Village ID", "hi": "Village ID"}, required=False, source="/api/v1/geography/villages", canonical_field="parcel.village_id", android_hint={"manual_fallback_field": "village_name_manual"}),
        FormField(id="local_name", type="text", label={"en": "Parcel Name", "hi": "Parcel Name"}, required=False, placeholder={"en": "e.g., North field", "hi": "e.g., North field"}, canonical_field="parcel.local_name"),
        FormField(id="village_name_manual", type="text", label={"en": "Village", "hi": "Village"}, required=True, canonical_field="parcel.village_name_manual"),
        FormField(id="survey_number", type="text", label={"en": "Survey/Khasra Number", "hi": "Survey/Khasra Number"}, required=False, canonical_field="parcel.survey_number"),
        FormField(id="reported_area", type="number", label={"en": "Reported Area", "hi": "Reported Area"}, required=True, validation={"min": 0.01}, canonical_field="parcel.reported_area"),
        FormField(id="reported_area_unit", type="single_select", label={"en": "Area Unit", "hi": "Area Unit"}, source="profile_options.land_units", required=True, default_value="BIGHA", options=[FormFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}), FormFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}), FormFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}), FormFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}), FormFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}), FormFieldOption(value="GUNTHA", label={"en": "Guntha", "hi": "Guntha"})], canonical_field="parcel.reported_area_unit"),
        FormField(id="ownership_type", type="single_select", label={"en": "Ownership", "hi": "Ownership"}, source="profile_options.ownership_types", required=False, default_value="OWNED", options=[FormFieldOption(value="OWNED", label={"en": "Owned", "hi": "Owned"}), FormFieldOption(value="PART_OWNER", label={"en": "Part owner", "hi": "Part owner"}), FormFieldOption(value="LEASED", label={"en": "Leased", "hi": "Leased"}), FormFieldOption(value="SHARED", label={"en": "Shared", "hi": "Shared"}), FormFieldOption(value="SHARECROP", label={"en": "Sharecrop", "hi": "Sharecrop"}), FormFieldOption(value="FAMILY", label={"en": "Family", "hi": "Family"})], canonical_field="parcel.ownership_type"),
        FormField(id="share_percentage", type="number", label={"en": "Shared Ownership %", "hi": "Shared Ownership %"}, required=False, depends_on="ownership_type", depends_on_value="SHARED", validation={"min": 1, "max": 100}, canonical_field="parcel.share_percentage"),
        FormField(id="sharecrop_percentage", type="number", label={"en": "Sharecrop Harvest %", "hi": "Sharecrop Harvest %"}, required=False, depends_on="ownership_type", depends_on_value="SHARECROP", validation={"min": 1, "max": 100}, canonical_field="parcel.sharecrop_percentage"),
        FormField(id="annual_rent", type="number", label={"en": "Annual Rent", "hi": "Annual Rent"}, required=False, depends_on="ownership_type", depends_on_value="LEASED", validation={"min": 0, "required_when": {"field": "ownership_type", "value": "LEASED"}}, canonical_field="parcel.annual_rent"),
        FormField(id="irrigation_source", type="single_select", label={"en": "Irrigation Source", "hi": "Irrigation Source"}, source="profile_options.irrigation_sources", required=False, options=[FormFieldOption(value="TUBEWELL_DIESEL", label={"en": "Tubewell (Diesel)", "hi": "Tubewell (Diesel)"}), FormFieldOption(value="TUBEWELL_ELECTRIC", label={"en": "Tubewell (Electric)", "hi": "Tubewell (Electric)"}), FormFieldOption(value="CANAL", label={"en": "Canal", "hi": "Canal"}), FormFieldOption(value="PURCHASED_WATER", label={"en": "Purchased Water", "hi": "Purchased Water"}), FormFieldOption(value="RAIN_FED", label={"en": "Rain-fed", "hi": "Rain-fed"}), FormFieldOption(value="POND_TANK", label={"en": "Pond/Tank", "hi": "Pond/Tank"}), FormFieldOption(value="RIVER_STREAM", label={"en": "River/Stream", "hi": "River/Stream"})], canonical_field="parcel.irrigation_source"),
        FormField(id="current_crop_code", type="dropdown", label={"en": "Current Crop", "hi": "Current Crop"}, required=False, source="/api/v1/master-data/crops", canonical_field="parcel.current_crop_code"),
        FormField(id="kharif_crops", type="multi_select", label={"en": "Kharif Crops", "hi": "Kharif Crops"}, required=False, source="/api/v1/master-data/crops?season=KHARIF", canonical_field="parcel.crops_by_season.KHARIF", android_hint={"payload_container": "crops_by_season", "season_code": "KHARIF"}),
        FormField(id="rabi_crops", type="multi_select", label={"en": "Rabi Crops", "hi": "Rabi Crops"}, required=False, source="/api/v1/master-data/crops?season=RABI", canonical_field="parcel.crops_by_season.RABI", android_hint={"payload_container": "crops_by_season", "season_code": "RABI"}),
        FormField(id="zaid_crops", type="multi_select", label={"en": "Zaid Crops", "hi": "Zaid Crops"}, required=False, source="/api/v1/master-data/crops?season=ZAID", canonical_field="parcel.crops_by_season.ZAID", android_hint={"payload_container": "crops_by_season", "season_code": "ZAID"}),
        FormField(id="soil_type_code", type="dropdown", label={"en": "Soil Type", "hi": "Soil Type"}, required=False, source="profile_options.soil_types", canonical_field="parcel.soil_type_code"),
        FormField(id="soil_texture", type="single_select", label={"en": "Observed Soil Texture", "hi": "Observed Soil Texture"}, source="profile_options.soil_textures", required=False, options=[FormFieldOption(value="SANDY", label={"en": "Sandy", "hi": "Sandy"}), FormFieldOption(value="LOAM", label={"en": "Loam", "hi": "Loam"}), FormFieldOption(value="LOAMY", label={"en": "Loamy", "hi": "Loamy"}), FormFieldOption(value="CLAY", label={"en": "Clay", "hi": "Clay"}), FormFieldOption(value="SANDY_LOAM", label={"en": "Sandy Loam", "hi": "Sandy Loam"}), FormFieldOption(value="CLAY_LOAM", label={"en": "Clay Loam", "hi": "Clay Loam"})], canonical_field="soil_profile.soil_texture", android_hint={"parcel_enrollment_hint": True}),
        FormField(id="soil_color", type="single_select", label={"en": "Observed Soil Color", "hi": "Observed Soil Color"}, source="profile_options.soil_colors", required=False, options=[FormFieldOption(value="BROWN", label={"en": "Brown", "hi": "Brown"}), FormFieldOption(value="DARK_BROWN", label={"en": "Dark brown", "hi": "Dark brown"}), FormFieldOption(value="LIGHT_BROWN", label={"en": "Light brown", "hi": "Light brown"}), FormFieldOption(value="REDDISH", label={"en": "Reddish", "hi": "Reddish"}), FormFieldOption(value="BLACK", label={"en": "Black", "hi": "Black"}), FormFieldOption(value="GREY", label={"en": "Grey", "hi": "Grey"})], canonical_field="soil_profile.soil_color", android_hint={"parcel_enrollment_hint": True}),
        FormField(id="geometry_source", type="single_select", label={"en": "GPS Capture Mode", "hi": "GPS Capture Mode"}, source="profile_options.geometry_sources", required=False, default_value="NONE", options=[FormFieldOption(value="NONE", label={"en": "No GPS", "hi": "No GPS"}), FormFieldOption(value="PIN_DROP", label={"en": "Pin drop", "hi": "Pin drop"}), FormFieldOption(value="PIN_CORNERS", label={"en": "Pin corners", "hi": "Pin corners"}), FormFieldOption(value="GPS_WALK", label={"en": "GPS walk", "hi": "GPS walk"})], canonical_field="parcel.geometry_source"),
        FormField(id="parcel_point", type="GPS_POINT", label={"en": "Pin Location", "hi": "Pin Location"}, required=False, capture_modes=["PIN_DROP", "CURRENT_LOCATION"], output_format="centroid_lat_lng", accuracy_required_meters=50, canonical_field="parcel.centroid", hint={"en": "Optional single GPS point", "hi": "Optional single GPS point"}),
        FormField(id="parcel_boundary", type="GPS_POLYGON", label={"en": "Walk Boundary", "hi": "Walk Boundary"}, required=False, capture_modes=["GPS_WALK", "MANUAL_DRAW"], output_format="geojson_polygon", min_points=3, accuracy_required_meters=10, canonical_field="parcel.geojson", hint={"en": "Optional full boundary; can be captured later", "hi": "Optional full boundary; can be captured later"}),
    ],
)

SOIL_PROFILE_FORM = FormSchema(
    form_id="soil_profile",
    version="1.0.0",
    title={"en": "Soil Profile", "hi": "Soil Profile"},
    description={"en": "Capture observed or lab-tested soil details", "hi": "Capture observed or lab-tested soil details"},
    submit_endpoint="/api/v1/soil-profiles",
    submit_method="POST",
    submit_label={"en": "Save Soil Profile", "hi": "Save Soil Profile"},
    fields=[
        FormField(id="parcel_id", type="dropdown", label={"en": "Parcel", "hi": "Parcel"}, required=True, source="local_parcels", canonical_field="soil_profile.parcel_id"),
        FormField(id="farmer_id", type="dropdown", label={"en": "Farmer", "hi": "Farmer"}, required=True, source="local_farmers", canonical_field="soil_profile.farmer_id"),
        FormField(id="data_source", type="single_select", label={"en": "Data Source", "hi": "Data Source"}, source="profile_options.soil_data_sources", required=True, default_value="MANUAL", options=[FormFieldOption(value="MANUAL", label={"en": "Manual Observation", "hi": "Manual Observation"}), FormFieldOption(value="INFERRED", label={"en": "Inferred", "hi": "Inferred"}), FormFieldOption(value="SHC_CARD", label={"en": "Soil Health Card", "hi": "Soil Health Card"}), FormFieldOption(value="LAB_REPORT", label={"en": "Lab Report", "hi": "Lab Report"})], canonical_field="soil_profile.data_source"),
        FormField(id="inferred_soil_type", type="text", label={"en": "Inferred Soil Type", "hi": "Inferred Soil Type"}, required=False, depends_on="data_source", depends_on_value="INFERRED", canonical_field="soil_profile.soil_type_code", android_hint={"read_only": True, "source": "soil_inference"}),
        FormField(id="inferred_soil_type_name", type="info", label={"en": "Inferred Soil Name", "hi": "Inferred Soil Name"}, required=False, depends_on="data_source", depends_on_value="INFERRED", canonical_field="soil_profile.inferred_name", android_hint={"read_only": True}),
        FormField(id="inferred_description", type="info", label={"en": "Inferred Soil Description", "hi": "Inferred Soil Description"}, required=False, depends_on="data_source", depends_on_value="INFERRED", canonical_field="soil_profile.inferred_description", android_hint={"read_only": True}),
        FormField(id="inferred_ph_range", type="info", label={"en": "Inferred pH Range", "hi": "Inferred pH Range"}, required=False, depends_on="data_source", depends_on_value="INFERRED", canonical_field="soil_profile.inferred_ph_range", android_hint={"read_only": True}),
        FormField(id="soil_type_code", type="dropdown", label={"en": "Soil Type", "hi": "Soil Type"}, required=False, source="profile_options.soil_types", canonical_field="soil_profile.soil_type_code"),
        FormField(id="soil_texture", type="single_select", label={"en": "Texture", "hi": "Texture"}, source="profile_options.soil_textures", required=False, options=[FormFieldOption(value="SANDY", label={"en": "Sandy", "hi": "Sandy"}), FormFieldOption(value="LOAM", label={"en": "Loam", "hi": "Loam"}), FormFieldOption(value="LOAMY", label={"en": "Loamy", "hi": "Loamy"}), FormFieldOption(value="CLAY", label={"en": "Clay", "hi": "Clay"}), FormFieldOption(value="SANDY_LOAM", label={"en": "Sandy Loam", "hi": "Sandy Loam"}), FormFieldOption(value="CLAY_LOAM", label={"en": "Clay Loam", "hi": "Clay Loam"})], canonical_field="soil_profile.soil_texture"),
        FormField(id="soil_color", type="single_select", label={"en": "Soil Color", "hi": "Soil Color"}, source="profile_options.soil_colors", required=False, options=[FormFieldOption(value="BROWN", label={"en": "Brown", "hi": "Brown"}), FormFieldOption(value="DARK_BROWN", label={"en": "Dark brown", "hi": "Dark brown"}), FormFieldOption(value="LIGHT_BROWN", label={"en": "Light brown", "hi": "Light brown"}), FormFieldOption(value="REDDISH", label={"en": "Reddish", "hi": "Reddish"}), FormFieldOption(value="BLACK", label={"en": "Black", "hi": "Black"}), FormFieldOption(value="GREY", label={"en": "Grey", "hi": "Grey"})], canonical_field="soil_profile.soil_color"),
        FormField(id="test_date", type="date", label={"en": "Test Date", "hi": "Test Date"}, required=False, default_value="today", depends_on="data_source", canonical_field="soil_profile.test_date"),
        FormField(id="lab_name", type="text", label={"en": "Lab Name", "hi": "Lab Name"}, required=False, depends_on="data_source", depends_on_value="LAB_REPORT", canonical_field="soil_profile.lab_name"),
        FormField(id="shc_card_number", type="text", label={"en": "SHC Card Number", "hi": "SHC Card Number"}, required=False, depends_on="data_source", depends_on_value="SHC_CARD", canonical_field="soil_profile.shc_card_number"),
        FormField(id="ph", type="number", label={"en": "pH", "hi": "pH"}, required=False, validation={"min": 0, "max": 14}, canonical_field="soil_profile.ph"),
        FormField(id="ec", type="number", label={"en": "EC (dS/m)", "hi": "EC (dS/m)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.ec"),
        FormField(id="organic_carbon_oc", type="number", label={"en": "Organic Carbon (%)", "hi": "Organic Carbon (%)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.organic_carbon_oc"),
        FormField(id="nitrogen_n", type="number", label={"en": "Nitrogen (N)", "hi": "Nitrogen (N)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.nitrogen_n"),
        FormField(id="phosphorus_p", type="number", label={"en": "Phosphorus (P)", "hi": "Phosphorus (P)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.phosphorus_p"),
        FormField(id="potassium_k", type="number", label={"en": "Potassium (K)", "hi": "Potassium (K)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.potassium_k"),
        FormField(id="sulphur_s", type="number", label={"en": "Sulphur (S)", "hi": "Sulphur (S)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.sulphur_s"),
        FormField(id="zinc_zn", type="number", label={"en": "Zinc (Zn)", "hi": "Zinc (Zn)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.zinc_zn"),
        FormField(id="iron_fe", type="number", label={"en": "Iron (Fe)", "hi": "Iron (Fe)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.iron_fe"),
        FormField(id="copper_cu", type="number", label={"en": "Copper (Cu)", "hi": "Copper (Cu)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.copper_cu"),
        FormField(id="manganese_mn", type="number", label={"en": "Manganese (Mn)", "hi": "Manganese (Mn)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.manganese_mn"),
        FormField(id="boron_b", type="number", label={"en": "Boron (B)", "hi": "Boron (B)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.boron_bo", android_hint={"payload_field": "boron_b", "backend_alias": "boron_bo"}),
        FormField(id="notes", type="text", label={"en": "Notes", "hi": "Notes"}, required=False, canonical_field="soil_profile.notes"),
    ],
)


CROP_CYCLE_CREATE_FORM = FormSchema(
    form_id="crop_cycle_create",
    version="1.3.0",
    title={"en": "Start Crop Cycle", "hi": "फसल चक्र शुरू करें"},
    description={"en": "Select your parcel, season, and crop to begin tracking", "hi": "ट्रैकिंग शुरू करने के लिए अपना खेत, मौसम और फसल चुनें"},
    submit_endpoint="/api/v1/crop-cycles",
    submit_method="POST",
    submit_label={"en": "Start Cycle", "hi": "चक्र शुरू करें"},
    fields=[
        FormField(
            id="parcel_id",
            type="dropdown",
            label={"en": "Select Parcel", "hi": "खेत चुनें"},
            required=True,
            source="local_parcels",
            placeholder={"en": "Choose your land parcel", "hi": "अपना खेत चुनें"},
        ),
        FormField(
            id="season_code",
            type="single_select",
            label={"en": "Season", "hi": "मौसम"},
            required=True,
            source="profile_options.seasons",
            options=[
                FormFieldOption(value="KHARIF", label={"en": "Kharif (Jun-Oct)", "hi": "खरीफ (जून-अक्टू)"}),
                FormFieldOption(value="RABI", label={"en": "Rabi (Oct-Mar)", "hi": "रबी (अक्टू-मार्च)"}),
                FormFieldOption(value="ZAID", label={"en": "Zaid (Mar-Jun)", "hi": "जायद (मार्च-जून)"}),
            ],
        ),
        FormField(
            id="crop_code",
            type="dropdown",
            label={"en": "Crop", "hi": "फसल"},
            required=True,
            source="/api/v1/master-data/crops?season={season_code}",
            depends_on="season_code",
            placeholder={"en": "Select crop for this season", "hi": "इस मौसम की फसल चुनें"},
        ),
        FormField(
            id="variety_code",
            type="dropdown",
            label={"en": "Variety (optional)", "hi": "किस्म (वैकल्पिक)"},
            required=False,
            source="/api/v1/master-data/crops/{crop_id}/varieties",
            depends_on="crop_code",
            placeholder={"en": "Select variety if known", "hi": "किस्म चुनें (अगर पता हो)"},
        ),
        FormField(
            id="planned_sowing_date",
            type="date",
            label={"en": "Sowing Date", "hi": "बुवाई की तारीख"},
            required=True,
            default_value="today",
            hint={"en": "When did you sow or plan to sow?", "hi": "कब बुवाई की या करनी है?"},
        ),
        FormField(
            id="seed_source",
            type="single_select",
            label={"en": "Seed Source", "hi": "बीज का स्रोत"},
            required=False,
            options=[
                FormFieldOption(value="OWN_SAVED", label={"en": "Own/Saved Seed", "hi": "अपना/बचाया बीज"}),
                FormFieldOption(value="PURCHASED", label={"en": "Purchased", "hi": "खरीदा"}),
            ],
        ),
        FormField(
            id="purchase_source",
            type="single_select",
            label={"en": "Purchase Source", "hi": "खरीदारी का स्रोत"},
            required=False,
            depends_on="seed_source",
            options=[
                FormFieldOption(value="MARKET", label={"en": "Market/Shop", "hi": "बाजार/दुकान"}),
                FormFieldOption(value="GOVERNMENT", label={"en": "Government Supply", "hi": "सरकारी आपूर्ति"}),
                FormFieldOption(value="COMPANY_DEALER", label={"en": "Company/Dealer", "hi": "कंपनी/डीलर"}),
            ],
        ),
        FormField(
            id="seed_brand",
            type="text",
            label={"en": "Company/Brand", "hi": "कंपनी/ब्रांड"},
            required=False,
            depends_on="seed_source",
            placeholder={"en": "e.g., Syngenta, Pioneer", "hi": "जैसे: सिनजेंटा, पायोनियर"},
        ),
        FormField(
            id="seed_quantity_kg",
            type="number",
            label={"en": "Quantity (kg)", "hi": "मात्रा (किग्रा)"},
            required=False,
            depends_on="seed_source",
            validation={"min": 0},
        ),
        FormField(
            id="seed_price",
            type="number",
            label={"en": "Price (₹)", "hi": "कीमत (₹)"},
            required=False,
            depends_on="seed_source",
            validation={"min": 0},
            placeholder={"en": "Total seed cost", "hi": "बीज की कुल कीमत"},
        ),
        FormField(
            id="receipt_scan",
            type="info",
            label={"en": "Receipt/Bill", "hi": "रसीद/बिल"},
            required=False,
            depends_on="seed_source",
            hint={"en": "Photo of receipt (coming soon)", "hi": "रसीद की फोटो (जल्द उपलब्ध)"},
        ),
    ],
)

ACTIVITY_LOG_FORM = FormSchema(
    form_id="activity_log",
    version="1.2.1",
    title={"en": "Log Activity", "hi": "गतिविधि दर्ज करें"},
    description={"en": "Record input usage or farm operation", "hi": "खाद, दवाई या खेती का काम दर्ज करें"},
    submit_endpoint="/api/v1/crop-cycles/{crop_cycle_id}/activities",
    submit_method="POST",
    submit_label={"en": "Save Activity", "hi": "गतिविधि सेव करें"},
    fields=[
        FormField(
            id="activity_type",
            type="single_select",
            label={"en": "Activity Type", "hi": "गतिविधि का प्रकार"},
            required=True,
            options=[
                FormFieldOption(value="FERTILIZER", label={"en": "Fertilizer", "hi": "खाद/उर्वरक"}),
                FormFieldOption(value="PESTICIDE", label={"en": "Pesticide/Spray", "hi": "कीटनाशक/स्प्रे"}),
                FormFieldOption(value="IRRIGATION", label={"en": "Irrigation", "hi": "सिंचाई"}),
                FormFieldOption(value="LABOR", label={"en": "Labor/Labour", "hi": "मजदूरी"}),
                FormFieldOption(value="MACHINERY", label={"en": "Machinery", "hi": "मशीनरी"}),
                FormFieldOption(value="SEED", label={"en": "Seed Purchase", "hi": "बीज खरीद"}),
                FormFieldOption(value="HARVEST", label={"en": "Harvest", "hi": "कटाई"}),
                FormFieldOption(value="OTHER", label={"en": "Other", "hi": "अन्य"}),
            ],
        ),
        FormField(
            id="input_name",
            type="text",
            label={"en": "Product/Input Name", "hi": "उत्पाद/इनपुट का नाम"},
            required=False,
            placeholder={"en": "e.g., DAP, Urea, Chlorpyrifos", "hi": "जैसे: DAP, यूरिया, क्लोरपायरीफॉस"},
            depends_on="activity_type",
        ),
        FormField(
            id="quantity",
            type="number",
            label={"en": "Quantity", "hi": "मात्रा"},
            required=False,
            validation={"min": 0},
        ),
        FormField(
            id="quantity_unit",
            type="single_select",
            label={"en": "Unit", "hi": "इकाई"},
            required=False,
            depends_on="quantity",
            options=[
                FormFieldOption(value="KG", label={"en": "Kg", "hi": "किलो"}),
                FormFieldOption(value="LITRE", label={"en": "Litre", "hi": "लीटर"}),
                FormFieldOption(value="BAG", label={"en": "Bag (50kg)", "hi": "बोरी (50kg)"}),
                FormFieldOption(value="PACKET", label={"en": "Packet", "hi": "पैकेट"}),
                FormFieldOption(value="HOURS", label={"en": "Hours", "hi": "घंटे"}),
                FormFieldOption(value="DAYS", label={"en": "Days", "hi": "दिन"}),
                FormFieldOption(value="SESSION", label={"en": "Session", "hi": "बार"}),
            ],
        ),
        FormField(
            id="irrigation_source",
            type="single_select",
            label={"en": "Irrigation Source", "hi": "सिंचाई का स्रोत"},
            required=False,
            depends_on="activity_type",
            depends_on_value="IRRIGATION",
            options=[
                FormFieldOption(value="TUBEWELL_DIESEL", label={"en": "Tubewell (Diesel)", "hi": "ट्यूबवेल (डीज़ल)"}),
                FormFieldOption(value="TUBEWELL_ELECTRIC", label={"en": "Tubewell (Electric)", "hi": "ट्यूबवेल (बिजली)"}),
                FormFieldOption(value="CANAL", label={"en": "Canal", "hi": "नहर"}),
                FormFieldOption(value="PURCHASED_WATER", label={"en": "Purchased Water", "hi": "खरीदा पानी"}),
                FormFieldOption(value="RAIN_FED", label={"en": "Rain-fed", "hi": "बारिश से"}),
            ],
            hint={"en": "Pre-filled from parcel data if available", "hi": "पार्सल डेटा से स्वतः भरा"},
        ),
        FormField(
            id="duration_hours",
            type="number",
            label={"en": "Duration (hours)", "hi": "अवधि (घंटे)"},
            required=False,
            depends_on="activity_type",
            depends_on_value="IRRIGATION",
            validation={"min": 0},
            hint={"en": "How long did pump/canal run?", "hi": "पंप/नहर कितनी देर चला?"},
        ),
        FormField(
            id="cost_amount",
            type="number",
            label={"en": "Cost (₹)", "hi": "लागत (₹)"},
            required=False,
            validation={"min": 0},
            placeholder={"en": "Total cost in rupees", "hi": "कुल खर्चा (रुपये में)"},
        ),
        FormField(
            id="activity_date",
            type="date",
            label={"en": "Date", "hi": "तारीख"},
            required=True,
            default_value="today",
        ),
        FormField(
            id="notes",
            type="text",
            label={"en": "Notes (optional)", "hi": "टिप्पणी (वैकल्पिक)"},
            required=False,
        ),
    ],
)

FORM_REGISTRY = {
    "farmer_registration": FARMER_REGISTRATION_FORM,
    "parcel_registration": PARCEL_REGISTRATION_FORM,
    "soil_profile": SOIL_PROFILE_FORM,
    "crop_cycle_create": CROP_CYCLE_CREATE_FORM,
    "activity_log": ACTIVITY_LOG_FORM,
}

PROFILE_FORM_IDS = ["farmer_registration", "parcel_registration", "soil_profile"]


def _field_payload(field: FormField) -> dict:
    return field.model_dump() if hasattr(field, "model_dump") else field.dict()


def _profile_contract_android_handoff() -> dict:
    return {
        "schema_version": "profile_contract_android_handoff.v1",
        "mode_bootstrap_endpoint": "/api/v1/auth/mode-bootstrap",
        "agent_worklist_endpoint": "/api/v1/field-agent/worklist",
        "assignment_endpoint": "/api/v1/farmers/{farmer_id}/project-agent-assignment",
        "forms_endpoint_template": "/api/v1/forms/{form_id}",
        "option_endpoint_template": "/api/v1/forms/options/{option_set}?project_id={project_id}",
        "screen_groups": {
            "farmer_registration": {
                "identity": ["display_name", "mobile_number", "father_name", "age", "gender"],
                "location": ["village_id", "village_name_manual", "pin_code", "enrollment_location"],
                "crop_and_language": ["primary_crop_code", "total_land_area", "total_land_unit", "language_preference"],
                "assistance": ["assistance_mode"],
            },
            "parcel_registration": {
                "location": ["pin_code", "village_id", "village_name_manual", "parcel_location", "parcel_boundary", "location_scope"],
                "land_holding": ["reported_area", "reported_area_unit", "ownership_type", "share_percentage", "sharecrop_percentage", "annual_rent"],
                "water_and_crops": ["irrigation_source", "kharif_crops", "rabi_crops", "zaid_crops"],
                "identity": ["local_name", "survey_number"],
            },
            "soil_profile": {
                "observation": ["soil_type_code", "soil_texture", "soil_color", "data_source"],
                "lab_or_shc": ["test_date", "lab_name", "shc_card_number", "nitrogen_n", "phosphorus_p", "potassium_k", "sulphur_s", "zinc_zn", "iron_fe", "copper_cu", "manganese_mn", "boron_b", "ph", "ec", "organic_carbon_oc"],
                "backend_enrichment": ["SOILGRIDS", "SHC_SLUSI", "OPEN_METEO", "IN_HOUSE_SATELLITE"],
            },
        },
        "agent_assisted_capture": {
            "supported": True,
            "actor_header": "X-Actor-ID",
            "assignment_source": "farmer_project_enrollments.assigned_user_ids",
            "dual_mode_supported": True,
            "dual_mode_rule": "A user can have an AgentProfile and a linked Farmer profile; Android should use mode-bootstrap first_screen_hint.",
        },
        "offline_sync": {
            "forms_cacheable": True,
            "option_sets_cacheable": True,
            "queue_mutations_when_offline": True,
            "replay_order": ["farmer_registration", "parcel_registration", "soil_profile", "soil_enrichment_snapshot", "field_event", "query_thread"],
            "idempotency_hint": "Use client-generated UUIDs where endpoint accepts ids; otherwise replay by stable local entity linkage and sync conflict rules.",
        },
        "soil_enrichment": {
            "android_calls_external_providers": False,
            "snapshot_endpoint": "/api/v1/soil-profiles/enrichments",
            "summary_endpoint": "/api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}",
            "queue_endpoint": "/api/v1/soil-profiles/enrichments/queue?farmer_id={farmer_id}",
            "latest_snapshot_endpoint": "/api/v1/soil-profiles/enrichments/latest",
            "source_contract_endpoint": "/api/v1/soil-profiles/enrichments/source-contract",
            "baseline_sources": ["SOILGRIDS", "SHC_SLUSI", "IN_HOUSE_SATELLITE"],
            "dynamic_sources": ["OPEN_METEO", "IN_HOUSE_SATELLITE"],
            "manual_import_sources": ["SHC_SLUSI"],
        },
        "location_model": {
            "normal_anchor": "parcel.pin_code",
            "manual_village_supported": True,
            "multi_village_override": "parcel.location_scope",
            "fpo_multi_village_supported": True,
            "gps_progression": ["NONE", "PIN_DROP", "GPS_WALK", "SATELLITE"],
        },
    }


def _profile_contract_payload_mappings() -> dict:
    return {
        "farmer_registration": {
            "mobile_number": "farmer.mobile_number",
            "pin_code": "farmer.pin_code",
            "village_name_manual": "farmer.village_name_manual",
            "primary_crop_code": "farmer.primary_crop_code",
            "language_preference": "farmer.language_preference",
            "assistance_mode": "farmer.enrollment_method",
        },
        "parcel_registration": {
            "pin_code": "parcel.pin_code",
            "location_scope": "parcel.location_scope",
            "reported_area": "parcel.reported_area",
            "reported_area_unit": "parcel.reported_area_unit",
            "ownership_type": "parcel.ownership_type",
            "share_percentage": "parcel.share_percentage",
            "sharecrop_percentage": "parcel.sharecrop_percentage",
            "irrigation_source": "parcel.irrigation_source",
            "parcel_location": "parcel.centroid_lat_lng",
            "parcel_boundary": "parcel.geojson",
            "kharif_crops": "parcel.crops_by_season.KHARIF",
            "rabi_crops": "parcel.crops_by_season.RABI",
            "zaid_crops": "parcel.crops_by_season.ZAID",
        },
        "soil_profile": {
            "soil_type_code": "soil_profile.soil_type_code",
            "soil_texture": "soil_profile.soil_texture",
            "soil_color": "soil_profile.soil_color",
            "data_source": "soil_profile.data_source",
            "boron_b": "soil_profile.boron_bo",
            "organic_carbon_oc": "soil_profile.organic_carbon_oc",
        },
    }


def _profile_contract_form_summary(schema: FormSchema) -> dict:
    fields = [_field_payload(field) for field in schema.fields]
    option_sets = sorted({str(field.get("source", "")).replace("profile_options.", "") for field in fields if str(field.get("source", "")).startswith("profile_options.")})
    gps_fields = [field["id"] for field in fields if str(field.get("type", "")).startswith("GPS")]
    required_fields = [field["id"] for field in fields if field.get("required")]
    recommended_fields = [field["id"] for field in fields if not field.get("required") and field.get("canonical_field")]
    canonical_fields = sorted({field["canonical_field"] for field in fields if field.get("canonical_field")})
    return {
        "form_id": schema.form_id,
        "version": schema.version,
        "title": schema.title,
        "submit_endpoint": schema.submit_endpoint,
        "submit_method": schema.submit_method,
        "field_count": len(fields),
        "required_fields": required_fields,
        "recommended_fields": recommended_fields,
        "canonical_fields": canonical_fields,
        "option_sets": option_sets,
        "gps_fields": gps_fields,
        "offline_supported": all(field.get("allow_offline_capture", True) for field in fields),
    }


# --- Endpoints ---

@router.get("/profile-contract")
def get_profile_contract_summary(
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """Return a compact backend-owned farmer/land/soil profile contract for Android/admin hydration."""
    tenant_id = x_tenant_id or "default"
    registry = _effective_profile_option_registry(db, tenant_id=tenant_id, project_id=project_id)
    forms = [_profile_contract_form_summary(FORM_REGISTRY[form_id]) for form_id in PROFILE_FORM_IDS]
    required_by_form = {form["form_id"]: form["required_fields"] for form in forms}
    option_sets_used = sorted({option_set for form in forms for option_set in form["option_sets"]})
    return {
        "schema_version": "profile_contract.v1",
        "tenant_id": tenant_id,
        "project_id": str(project_id) if project_id else None,
        "forms": forms,
        "required_by_form": required_by_form,
        "option_sets_used": option_sets_used,
        "option_set_sources": {
            key: {"version": value.version, "source": value.metadata.get("source", "default"), "option_count": len(value.options)}
            for key, value in sorted(registry.items())
            if key in option_sets_used
        },
        "backend_owned_contract": {
            "forms": True,
            "option_sets": True,
            "validation": True,
            "readiness": True,
            "soil_enrichment_snapshots": True,
            "agent_assisted_capture": True,
            "mode_bootstrap": True,
            "android_should_hardcode_options": False,
        },
        "android_handoff": _profile_contract_android_handoff(),
        "payload_mappings": _profile_contract_payload_mappings(),
    }


@router.get("/options")
def list_profile_option_sets(
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """List effective backend-owned option sets for forms and offline cache hydration."""
    tenant_id = x_tenant_id or "default"
    registry = _effective_profile_option_registry(db, tenant_id=tenant_id, project_id=project_id)
    return {
        "schema_version": "profile_option_sets.v1",
        "tenant_id": tenant_id,
        "project_id": str(project_id) if project_id else None,
        "count": len(registry),
        "option_sets": [
            {"option_set": key, "version": value.version, "title": value.title, "option_count": len(value.options), "source": value.metadata.get("source", "default")}
            for key, value in sorted(registry.items())
        ],
    }


@router.get("/options/{option_set}", response_model=ProfileOptionSet)
def get_profile_option_set(
    option_set: str,
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """Return one effective backend-owned option set used by profile forms."""
    tenant_id = x_tenant_id or "default"
    registry = _effective_profile_option_registry(db, tenant_id=tenant_id, project_id=project_id)
    resolved = registry.get(option_set)
    if not resolved:
        raise HTTPException(404, f"Option set '{option_set}' not found. Available: {list(registry.keys())}")
    return resolved


@router.get("/{form_id}", response_model=FormSchema)
def get_form_schema(
    form_id: str,
    x_tenant_id: str = Header(None, alias="X-Tenant-ID"),
):
    """Get form schema for client-side rendering.

    All translatable strings are Map<lang_code, text>.
    Android resolves: map[currentLanguageCode] ?: map["en"]
    Cacheable: use version field for invalidation.
    """
    schema = FORM_REGISTRY.get(form_id)
    if not schema:
        raise HTTPException(404, f"Form '{form_id}' not found. Available: {list(FORM_REGISTRY.keys())}")
    return schema


@router.get("", response_model=list[dict])
def list_forms(
    x_tenant_id: str = Header(None, alias="X-Tenant-ID"),
):
    """List all available form schemas with versions."""
    return [
        {
            "form_id": form_id,
            "version": schema.version,
            "title": schema.title,
        }
        for form_id, schema in FORM_REGISTRY.items()
    ]
