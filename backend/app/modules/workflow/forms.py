"""Schema-driven form API.

GET /api/v1/forms/{form_id} — Returns form schema for client-side rendering.

Form schemas are:
- Flat (list of fields)
- Support depends_on relationships (cascading dropdowns)
- Support dynamic source with {field_id} variable substitution
- Cacheable with version field for invalidation
- Bilingual labels (en + hi)

Android renders forms progressively: fields appear as dependencies are satisfied.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/forms", tags=["forms"])


class FormFieldOption(BaseModel):
    value: str
    label_en: str
    label_hi: str


class FormField(BaseModel):
    id: str
    type: str  # text, number, date, dropdown, single_select, multi_select
    label_en: str
    label_hi: str
    required: bool = False
    source: Optional[str] = None  # API endpoint or "local_*" for Room data
    options: Optional[list[FormFieldOption]] = None  # For static single_select
    depends_on: Optional[str] = None  # Field ID this depends on
    default_value: Optional[str] = None
    placeholder_en: Optional[str] = None
    placeholder_hi: Optional[str] = None
    validation: Optional[dict] = None  # {"min": 0, "max": 100, "pattern": "..."}
    hint_en: Optional[str] = None
    hint_hi: Optional[str] = None


class FormSchema(BaseModel):
    form_id: str
    version: str  # For cache invalidation
    title_en: str
    title_hi: str
    description_en: Optional[str] = None
    description_hi: Optional[str] = None
    fields: list[FormField]
    submit_endpoint: str  # POST endpoint to submit form data
    submit_method: str = "POST"


# --- Form Definitions ---

CROP_CYCLE_CREATE_FORM = FormSchema(
    form_id="crop_cycle_create",
    version="1.0.0",
    title_en="Start Crop Cycle",
    title_hi="फसल चक्र शुरू करें",
    description_en="Select your parcel, season, and crop to begin tracking",
    description_hi="ट्रैकिंग शुरू करने के लिए अपना खेत, मौसम और फसल चुनें",
    submit_endpoint="/api/v1/crop-cycles",
    submit_method="POST",
    fields=[
        FormField(
            id="parcel_id",
            type="dropdown",
            label_en="Select Parcel",
            label_hi="खेत चुनें",
            required=True,
            source="local_parcels",  # Android loads from local Room DB
            placeholder_en="Choose your land parcel",
            placeholder_hi="अपना खेत चुनें",
        ),
        FormField(
            id="season_code",
            type="single_select",
            label_en="Season",
            label_hi="मौसम",
            required=True,
            options=[
                FormFieldOption(value="KHARIF", label_en="Kharif (Jun-Oct)", label_hi="खरीफ (जून-अक्टू)"),
                FormFieldOption(value="RABI", label_en="Rabi (Oct-Mar)", label_hi="रबी (अक्टू-मार्च)"),
                FormFieldOption(value="ZAID", label_en="Zaid (Mar-Jun)", label_hi="जायद (मार्च-जून)"),
            ],
        ),
        FormField(
            id="crop_code",
            type="dropdown",
            label_en="Crop",
            label_hi="फसल",
            required=True,
            source="/api/v1/master-data/crops?season={season_code}",
            depends_on="season_code",
            placeholder_en="Select crop for this season",
            placeholder_hi="इस मौसम की फसल चुनें",
        ),
        FormField(
            id="variety_code",
            type="dropdown",
            label_en="Variety (optional)",
            label_hi="किस्म (वैकल्पिक)",
            required=False,
            source="/api/v1/master-data/crops/{crop_id}/varieties",
            depends_on="crop_code",
            placeholder_en="Select variety if known",
            placeholder_hi="किस्म चुनें (अगर पता हो)",
        ),
        FormField(
            id="planned_sowing_date",
            type="date",
            label_en="Sowing Date",
            label_hi="बुवाई की तारीख",
            required=True,
            default_value="today",
            hint_en="When did you sow or plan to sow?",
            hint_hi="कब बुवाई की या करनी है?",
        ),
        FormField(
            id="expected_harvest_date",
            type="date",
            label_en="Expected Harvest Date",
            label_hi="कटाई की अनुमानित तारीख",
            required=False,
            hint_en="Approximate harvest month",
            hint_hi="अनुमानित कटाई का महीना",
        ),
        FormField(
            id="seed_source",
            type="single_select",
            label_en="Seed Source",
            label_hi="बीज का स्रोत",
            required=False,
            options=[
                FormFieldOption(value="OWN_SAVED", label_en="Own Saved", label_hi="अपना बचाया हुआ"),
                FormFieldOption(value="PURCHASED_MARKET", label_en="Purchased (Market)", label_hi="खरीदा (बाजार)"),
                FormFieldOption(value="PURCHASED_GOVT", label_en="Government Supply", label_hi="सरकारी आपूर्ति"),
                FormFieldOption(value="PURCHASED_COMPANY", label_en="Company/Dealer", label_hi="कंपनी/डीलर"),
                FormFieldOption(value="EXCHANGE", label_en="Exchange with farmer", label_hi="किसान से अदला-बदली"),
            ],
        ),
    ],
)

ACTIVITY_LOG_FORM = FormSchema(
    form_id="activity_log",
    version="1.0.0",
    title_en="Log Activity",
    title_hi="गतिविधि दर्ज करें",
    description_en="Record input usage or farm operation",
    description_hi="खाद, दवाई या खेती का काम दर्ज करें",
    submit_endpoint="/api/v1/crop-cycles/{crop_cycle_id}/activities",
    submit_method="POST",
    fields=[
        FormField(
            id="activity_type",
            type="single_select",
            label_en="Activity Type",
            label_hi="गतिविधि का प्रकार",
            required=True,
            options=[
                FormFieldOption(value="FERTILIZER", label_en="Fertilizer", label_hi="खाद/उर्वरक"),
                FormFieldOption(value="PESTICIDE", label_en="Pesticide/Spray", label_hi="कीटनाशक/स्प्रे"),
                FormFieldOption(value="IRRIGATION", label_en="Irrigation", label_hi="सिंचाई"),
                FormFieldOption(value="LABOR", label_en="Labor/Labour", label_hi="मजदूरी"),
                FormFieldOption(value="MACHINERY", label_en="Machinery", label_hi="मशीनरी"),
                FormFieldOption(value="SEED", label_en="Seed Purchase", label_hi="बीज खरीद"),
                FormFieldOption(value="HARVEST", label_en="Harvest", label_hi="कटाई"),
                FormFieldOption(value="OTHER", label_en="Other", label_hi="अन्य"),
            ],
        ),
        FormField(
            id="input_name",
            type="text",
            label_en="Product/Input Name",
            label_hi="उत्पाद/इनपुट का नाम",
            required=False,
            placeholder_en="e.g., DAP, Urea, Chlorpyrifos",
            placeholder_hi="जैसे: DAP, यूरिया, क्लोरपायरीफॉस",
            depends_on="activity_type",
        ),
        FormField(
            id="quantity",
            type="number",
            label_en="Quantity",
            label_hi="मात्रा",
            required=False,
            validation={"min": 0},
        ),
        FormField(
            id="quantity_unit",
            type="single_select",
            label_en="Unit",
            label_hi="इकाई",
            required=False,
            depends_on="quantity",
            options=[
                FormFieldOption(value="KG", label_en="Kg", label_hi="किलो"),
                FormFieldOption(value="LITRE", label_en="Litre", label_hi="लीटर"),
                FormFieldOption(value="BAG", label_en="Bag (50kg)", label_hi="बोरी (50kg)"),
                FormFieldOption(value="PACKET", label_en="Packet", label_hi="पैकेट"),
                FormFieldOption(value="HOURS", label_en="Hours", label_hi="घंटे"),
                FormFieldOption(value="DAYS", label_en="Days", label_hi="दिन"),
                FormFieldOption(value="SESSION", label_en="Session", label_hi="बार"),
            ],
        ),
        FormField(
            id="cost_amount",
            type="number",
            label_en="Cost (₹)",
            label_hi="लागत (₹)",
            required=False,
            validation={"min": 0},
            placeholder_en="Total cost in rupees",
            placeholder_hi="कुल खर्चा (रुपये में)",
        ),
        FormField(
            id="activity_date",
            type="date",
            label_en="Date",
            label_hi="तारीख",
            required=True,
            default_value="today",
        ),
        FormField(
            id="notes",
            type="text",
            label_en="Notes (optional)",
            label_hi="टिप्पणी (वैकल्पिक)",
            required=False,
        ),
    ],
)

# Registry of all forms
FORM_REGISTRY = {
    "crop_cycle_create": CROP_CYCLE_CREATE_FORM,
    "activity_log": ACTIVITY_LOG_FORM,
}


# --- Endpoint ---

@router.get("/{form_id}", response_model=FormSchema)
def get_form_schema(
    form_id: str,
    x_tenant_id: str = Header(None, alias="X-Tenant-ID"),
):
    """Get form schema for client-side rendering.

    Cacheable: use the version field for cache invalidation.
    Android should download form schemas on login and use offline.
    """
    schema = FORM_REGISTRY.get(form_id)
    if not schema:
        raise HTTPException(404, f"Form '{form_id}' not found. Available: {list(FORM_REGISTRY.keys())}")
    return schema


@router.get("", response_model=list[dict])
def list_forms(
    x_tenant_id: str = Header(None, alias="X-Tenant-ID"),
):
    """List all available form schemas with their versions."""
    return [
        {
            "form_id": form_id,
            "version": schema.version,
            "title_en": schema.title_en,
            "title_hi": schema.title_hi,
        }
        for form_id, schema in FORM_REGISTRY.items()
    ]
