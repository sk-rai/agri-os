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
    type: str  # text, number, date, dropdown, single_select, multi_select
    label: dict[str, str]
    required: bool = False
    source: Optional[str] = None  # API endpoint or "local_*" for Room data
    options: Optional[list[FormFieldOption]] = None
    depends_on: Optional[str] = None
    default_value: Optional[str] = None
    placeholder: Optional[dict[str, str]] = None
    validation: Optional[dict] = None
    hint: Optional[dict[str, str]] = None


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
    version="1.2.0",
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
