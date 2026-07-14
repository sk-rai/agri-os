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

from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

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
    source: Optional[str] = None  # API endpoint or "local_*" for Room data
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
        FormField(id="mobile_number", type="text", label={"en": "Mobile Number", "hi": "Mobile Number"}, required=True, placeholder={"en": "+919900000001 or 9900000001", "hi": "+919900000001 or 9900000001"}, validation={"pattern": "^\\+?[0-9]{10,15}$"}, canonical_field="farmer.mobile_number", android_hint={"keyboard": "phone"}),
        FormField(id="village_name_manual", type="text", label={"en": "Village", "hi": "Village"}, required=True, placeholder={"en": "Village name", "hi": "Village name"}, canonical_field="farmer.village_name_manual"),
        FormField(id="primary_crop_code", type="dropdown", label={"en": "Primary Crop", "hi": "Primary Crop"}, required=False, source="/api/v1/master-data/crops", placeholder={"en": "Select primary crop", "hi": "Select primary crop"}, canonical_field="farmer.primary_crop_code"),
        FormField(id="father_name", type="text", label={"en": "Father/Guardian Name", "hi": "Father/Guardian Name"}, required=False, canonical_field="farmer.father_name"),
        FormField(id="age", type="number", label={"en": "Age", "hi": "Age"}, required=False, validation={"min": 1, "max": 120}, canonical_field="farmer.age"),
        FormField(id="gender", type="single_select", label={"en": "Gender", "hi": "Gender"}, required=False, options=[FormFieldOption(value="MALE", label={"en": "Male", "hi": "Male"}), FormFieldOption(value="FEMALE", label={"en": "Female", "hi": "Female"}), FormFieldOption(value="OTHER", label={"en": "Other", "hi": "Other"})], canonical_field="farmer.gender"),
        FormField(id="total_land_area", type="number", label={"en": "Total Land Area", "hi": "Total Land Area"}, required=False, validation={"min": 0}, canonical_field="farmer.total_land_area"),
        FormField(id="total_land_unit", type="single_select", label={"en": "Land Unit", "hi": "Land Unit"}, required=False, default_value="BIGHA", options=[FormFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}), FormFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}), FormFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}), FormFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}), FormFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}), FormFieldOption(value="GUNTHA", label={"en": "Guntha", "hi": "Guntha"})], canonical_field="farmer.total_land_unit"),
        FormField(id="language_preference", type="single_select", label={"en": "Preferred Language", "hi": "Preferred Language"}, required=False, default_value="hi", options=[FormFieldOption(value="en", label={"en": "English", "hi": "English"}), FormFieldOption(value="hi", label={"en": "Hindi", "hi": "Hindi"})], canonical_field="farmer.language_preference"),
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
        FormField(id="local_name", type="text", label={"en": "Parcel Name", "hi": "Parcel Name"}, required=False, placeholder={"en": "e.g., North field", "hi": "e.g., North field"}, canonical_field="parcel.local_name"),
        FormField(id="village_name_manual", type="text", label={"en": "Village", "hi": "Village"}, required=True, canonical_field="parcel.village_name_manual"),
        FormField(id="survey_number", type="text", label={"en": "Survey/Khasra Number", "hi": "Survey/Khasra Number"}, required=False, canonical_field="parcel.survey_number"),
        FormField(id="reported_area", type="number", label={"en": "Reported Area", "hi": "Reported Area"}, required=True, validation={"min": 0.01}, canonical_field="parcel.reported_area"),
        FormField(id="reported_area_unit", type="single_select", label={"en": "Area Unit", "hi": "Area Unit"}, required=True, default_value="BIGHA", options=[FormFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}), FormFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}), FormFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}), FormFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}), FormFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}), FormFieldOption(value="GUNTHA", label={"en": "Guntha", "hi": "Guntha"})], canonical_field="parcel.reported_area_unit"),
        FormField(id="ownership_type", type="single_select", label={"en": "Ownership", "hi": "Ownership"}, required=False, default_value="OWNED", options=[FormFieldOption(value="OWNED", label={"en": "Owned", "hi": "Owned"}), FormFieldOption(value="LEASED", label={"en": "Leased", "hi": "Leased"}), FormFieldOption(value="SHARED", label={"en": "Shared", "hi": "Shared"}), FormFieldOption(value="SHARECROP", label={"en": "Sharecrop", "hi": "Sharecrop"}), FormFieldOption(value="FAMILY", label={"en": "Family", "hi": "Family"})], canonical_field="parcel.ownership_type"),
        FormField(id="annual_rent", type="number", label={"en": "Annual Rent", "hi": "Annual Rent"}, required=False, depends_on="ownership_type", depends_on_value="LEASED", validation={"min": 0}, canonical_field="parcel.annual_rent"),
        FormField(id="irrigation_source", type="single_select", label={"en": "Irrigation Source", "hi": "Irrigation Source"}, required=False, options=[FormFieldOption(value="TUBEWELL_DIESEL", label={"en": "Tubewell (Diesel)", "hi": "Tubewell (Diesel)"}), FormFieldOption(value="TUBEWELL_ELECTRIC", label={"en": "Tubewell (Electric)", "hi": "Tubewell (Electric)"}), FormFieldOption(value="CANAL", label={"en": "Canal", "hi": "Canal"}), FormFieldOption(value="POND_TANK", label={"en": "Pond/Tank", "hi": "Pond/Tank"}), FormFieldOption(value="RAIN_FED", label={"en": "Rain-fed", "hi": "Rain-fed"})], canonical_field="parcel.irrigation_source"),
        FormField(id="current_crop_code", type="dropdown", label={"en": "Current Crop", "hi": "Current Crop"}, required=False, source="/api/v1/master-data/crops", canonical_field="parcel.current_crop_code"),
        FormField(id="soil_type_code", type="dropdown", label={"en": "Soil Type", "hi": "Soil Type"}, required=False, source="local_soil_types", canonical_field="parcel.soil_type_code"),
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
        FormField(id="data_source", type="single_select", label={"en": "Data Source", "hi": "Data Source"}, required=True, default_value="MANUAL", options=[FormFieldOption(value="MANUAL", label={"en": "Manual Observation", "hi": "Manual Observation"}), FormFieldOption(value="INFERRED", label={"en": "Inferred", "hi": "Inferred"}), FormFieldOption(value="SHC_CARD", label={"en": "Soil Health Card", "hi": "Soil Health Card"}), FormFieldOption(value="LAB_REPORT", label={"en": "Lab Report", "hi": "Lab Report"})], canonical_field="soil_profile.data_source"),
        FormField(id="soil_type_code", type="dropdown", label={"en": "Soil Type", "hi": "Soil Type"}, required=False, source="local_soil_types", canonical_field="soil_profile.soil_type_code"),
        FormField(id="soil_texture", type="single_select", label={"en": "Texture", "hi": "Texture"}, required=False, options=[FormFieldOption(value="SANDY", label={"en": "Sandy", "hi": "Sandy"}), FormFieldOption(value="LOAMY", label={"en": "Loamy", "hi": "Loamy"}), FormFieldOption(value="CLAY", label={"en": "Clay", "hi": "Clay"}), FormFieldOption(value="SANDY_LOAM", label={"en": "Sandy Loam", "hi": "Sandy Loam"}), FormFieldOption(value="CLAY_LOAM", label={"en": "Clay Loam", "hi": "Clay Loam"})], canonical_field="soil_profile.soil_texture"),
        FormField(id="soil_color", type="text", label={"en": "Soil Color", "hi": "Soil Color"}, required=False, canonical_field="soil_profile.soil_color"),
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
        FormField(id="boron_bo", type="number", label={"en": "Boron (B)", "hi": "Boron (B)"}, required=False, validation={"min": 0}, canonical_field="soil_profile.boron_bo"),
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


# --- Endpoints ---

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
