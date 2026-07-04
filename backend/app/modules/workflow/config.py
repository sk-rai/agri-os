"""Backend-driven workflow configuration API.

This is the v1 contract Android can render generically. For now the source is
static Python data; later the admin UI can persist the same shape in DB with
DRAFT/PUBLISHED versions and tenant/project overrides.
"""

from copy import deepcopy
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowFieldOption(BaseModel):
    value: str
    label: dict[str, str]


class WorkflowField(BaseModel):
    id: str
    type: str
    label: dict[str, str]
    required: bool = False
    canonical_field: Optional[str] = None
    source: Optional[str] = None
    options: Optional[list[WorkflowFieldOption]] = None
    depends_on: Optional[str] = None
    depends_on_value: Optional[str] = None
    default_value: Optional[str] = None
    placeholder: Optional[dict[str, str]] = None
    hint: Optional[dict[str, str]] = None
    validation: Optional[dict] = None
    android_hint: Optional[dict] = None
    capture_modes: Optional[list[str]] = None
    output_format: Optional[str] = None
    min_points: Optional[int] = None
    accuracy_required_meters: Optional[float] = None
    allow_offline_capture: bool = True


class WorkflowStep(BaseModel):
    step_key: str
    title: dict[str, str]
    description: Optional[dict[str, str]] = None
    order: int
    optional: bool = False
    fields: list[WorkflowField] = Field(default_factory=list)


class WorkflowSchema(BaseModel):
    workflow_key: str
    version: str
    entity_type: str
    title: dict[str, str]
    description: Optional[dict[str, str]] = None
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    submit_endpoint: str
    submit_method: str = "POST"
    field_types_supported: list[str]
    steps: list[WorkflowStep]
    option_sets: dict[str, list[WorkflowFieldOption]] = Field(default_factory=dict)


FIELD_TYPES_SUPPORTED = [
    "TEXT",
    "NUMBER",
    "DATE",
    "SINGLE_SELECT",
    "MULTI_SELECT",
    "BOOLEAN",
    "CURRENCY",
    "QUANTITY",
    "PHOTO",
    "GPS_POINT",
    "GPS_POLYGON",
    "SIGNATURE",
    "SECTION",
]

OWNERSHIP_OPTIONS = [
    WorkflowFieldOption(value="OWNED", label={"en": "Owned", "hi": "Owned"}),
    WorkflowFieldOption(value="LEASED", label={"en": "Leased", "hi": "Leased"}),
    WorkflowFieldOption(value="SHARED", label={"en": "Shared", "hi": "Shared"}),
    WorkflowFieldOption(value="SHARECROP", label={"en": "Sharecrop", "hi": "Sharecrop"}),
    WorkflowFieldOption(value="FAMILY", label={"en": "Family Land", "hi": "Family Land"}),
]

AREA_UNIT_OPTIONS = [
    WorkflowFieldOption(value="BISWA", label={"en": "Biswa", "hi": "Biswa"}),
    WorkflowFieldOption(value="BIGHA", label={"en": "Bigha", "hi": "Bigha"}),
    WorkflowFieldOption(value="ACRE", label={"en": "Acre", "hi": "Acre"}),
    WorkflowFieldOption(value="HECTARE", label={"en": "Hectare", "hi": "Hectare"}),
    WorkflowFieldOption(value="KATHA", label={"en": "Katha", "hi": "Katha"}),
]

IRRIGATION_OPTIONS = [
    WorkflowFieldOption(value="TUBEWELL_DIESEL", label={"en": "Tubewell (Diesel)", "hi": "Tubewell (Diesel)"}),
    WorkflowFieldOption(value="TUBEWELL_ELECTRIC", label={"en": "Tubewell (Electric)", "hi": "Tubewell (Electric)"}),
    WorkflowFieldOption(value="CANAL", label={"en": "Canal", "hi": "Canal"}),
    WorkflowFieldOption(value="PURCHASED_WATER", label={"en": "Purchased Water", "hi": "Purchased Water"}),
    WorkflowFieldOption(value="RAIN_FED", label={"en": "Rain-fed", "hi": "Rain-fed"}),
    WorkflowFieldOption(value="POND_TANK", label={"en": "Pond/Tank", "hi": "Pond/Tank"}),
]

SOIL_TEXTURE_OPTIONS = [
    WorkflowFieldOption(value="SANDY", label={"en": "Sandy", "hi": "Sandy"}),
    WorkflowFieldOption(value="LOAMY", label={"en": "Loamy", "hi": "Loamy"}),
    WorkflowFieldOption(value="CLAY", label={"en": "Clay", "hi": "Clay"}),
    WorkflowFieldOption(value="SILTY", label={"en": "Silty", "hi": "Silty"}),
]

WORKFLOW_REGISTRY: dict[str, WorkflowSchema] = {
    "farmer_enrollment": WorkflowSchema(
        workflow_key="farmer_enrollment",
        version="1.0.0",
        entity_type="FARMER",
        title={"en": "Farmer Enrollment", "hi": "Farmer Enrollment"},
        description={"en": "Progressive farmer profile capture", "hi": "Progressive farmer profile capture"},
        submit_endpoint="/api/v1/farmers",
        field_types_supported=FIELD_TYPES_SUPPORTED,
        steps=[
            WorkflowStep(
                step_key="basic_identity",
                order=1,
                title={"en": "Basic Details", "hi": "Basic Details"},
                fields=[
                    WorkflowField(id="display_name", type="TEXT", label={"en": "Farmer Name", "hi": "Farmer Name"}, required=True, canonical_field="display_name"),
                    WorkflowField(id="mobile_number", type="TEXT", label={"en": "Mobile Number", "hi": "Mobile Number"}, required=True, canonical_field="mobile_number", validation={"pattern": "^\+91[6-9]\d{9}$"}),
                    WorkflowField(id="father_name", type="TEXT", label={"en": "Father/Spouse Name", "hi": "Father/Spouse Name"}, canonical_field="father_name"),
                    WorkflowField(id="language_preference", type="SINGLE_SELECT", label={"en": "Language", "hi": "Language"}, canonical_field="language_preference", default_value="hi", options=[WorkflowFieldOption(value="hi", label={"en": "Hindi", "hi": "Hindi"}), WorkflowFieldOption(value="en", label={"en": "English", "hi": "English"})]),
                ],
            ),
            WorkflowStep(
                step_key="location_and_crops",
                order=2,
                title={"en": "Village & Crops", "hi": "Village & Crops"},
                fields=[
                    WorkflowField(id="village_id", type="SINGLE_SELECT", label={"en": "Village", "hi": "Village"}, canonical_field="village_id", source="/api/v1/master-data/geography/villages"),
                    WorkflowField(id="village_name_manual", type="TEXT", label={"en": "Village Name (manual)", "hi": "Village Name (manual)"}, canonical_field="village_name_manual"),
                    WorkflowField(id="primary_crop_code", type="SINGLE_SELECT", label={"en": "Primary Crop", "hi": "Primary Crop"}, canonical_field="primary_crop_code", source="/api/v1/master-data/crops"),
                    WorkflowField(id="enrollment_location", type="GPS_POINT", label={"en": "Enrollment Location", "hi": "Enrollment Location"}, canonical_field="enrollment_gps", required=False, capture_modes=["PIN_DROP"], output_format="GEOJSON", accuracy_required_meters=50, android_hint={"widget": "gps_point_capture"}),
                ],
            ),
        ],
    ),
    "parcel_registration": WorkflowSchema(
        workflow_key="parcel_registration",
        version="1.0.0",
        entity_type="PARCEL",
        title={"en": "Parcel Registration", "hi": "Parcel Registration"},
        description={"en": "Progressive land parcel capture from reported area to GPS boundary", "hi": "Progressive land parcel capture from reported area to GPS boundary"},
        submit_endpoint="/api/v1/parcels",
        field_types_supported=FIELD_TYPES_SUPPORTED,
        option_sets={"ownership_type": OWNERSHIP_OPTIONS, "area_units": AREA_UNIT_OPTIONS, "irrigation_sources": IRRIGATION_OPTIONS},
        steps=[
            WorkflowStep(
                step_key="basic_land_info",
                order=1,
                title={"en": "Land Details", "hi": "Land Details"},
                fields=[
                    WorkflowField(id="survey_number", type="TEXT", label={"en": "Survey/Khasra Number", "hi": "Survey/Khasra Number"}, canonical_field="survey_number"),
                    WorkflowField(id="local_name", type="TEXT", label={"en": "Local Name", "hi": "Local Name"}, canonical_field="local_name"),
                    WorkflowField(id="reported_area", type="NUMBER", label={"en": "Area", "hi": "Area"}, required=True, canonical_field="reported_area", validation={"min": 0}),
                    WorkflowField(id="reported_area_unit", type="SINGLE_SELECT", label={"en": "Area Unit", "hi": "Area Unit"}, required=True, canonical_field="reported_area_unit", options=AREA_UNIT_OPTIONS, default_value="BISWA"),
                ],
            ),
            WorkflowStep(
                step_key="ownership_and_water",
                order=2,
                title={"en": "Ownership & Water", "hi": "Ownership & Water"},
                fields=[
                    WorkflowField(id="ownership_type", type="SINGLE_SELECT", label={"en": "Ownership Type", "hi": "Ownership Type"}, required=True, canonical_field="ownership_type", options=OWNERSHIP_OPTIONS, default_value="OWNED"),
                    WorkflowField(id="annual_rent", type="CURRENCY", label={"en": "Annual Rent", "hi": "Annual Rent"}, canonical_field="annual_rent", depends_on="ownership_type", depends_on_value="LEASED", validation={"min": 0}),
                    WorkflowField(id="share_percentage", type="NUMBER", label={"en": "Share Percentage", "hi": "Share Percentage"}, canonical_field="share_percentage", depends_on="ownership_type", depends_on_value="SHARED", validation={"min": 1, "max": 100}),
                    WorkflowField(id="irrigation_source", type="SINGLE_SELECT", label={"en": "Irrigation Source", "hi": "Irrigation Source"}, canonical_field="irrigation_source", options=IRRIGATION_OPTIONS),
                ],
            ),
            WorkflowStep(
                step_key="location",
                order=3,
                title={"en": "Location", "hi": "Location"},
                fields=[
                    WorkflowField(id="centroid", type="GPS_POINT", label={"en": "Parcel Pin Drop", "hi": "Parcel Pin Drop"}, canonical_field="centroid", capture_modes=["PIN_DROP"], output_format="GEOJSON", accuracy_required_meters=25, android_hint={"widget": "gps_point_capture"}),
                    WorkflowField(id="boundary_polygon", type="GPS_POLYGON", label={"en": "Field Boundary", "hi": "Field Boundary"}, canonical_field="geometry", required=False, capture_modes=["GPS_WALK", "MANUAL_DRAW"], output_format="GEOJSON", min_points=4, accuracy_required_meters=10, android_hint={"widget": "gps_polygon_capture", "allow_pause_resume": True}),
                ],
            ),
        ],
    ),
    "soil_profile": WorkflowSchema(
        workflow_key="soil_profile",
        version="1.0.0",
        entity_type="SOIL_PROFILE",
        title={"en": "Soil Profile", "hi": "Soil Profile"},
        description={"en": "Progressive soil observation and test capture", "hi": "Progressive soil observation and test capture"},
        submit_endpoint="/api/v1/soil-profiles",
        field_types_supported=FIELD_TYPES_SUPPORTED,
        option_sets={"soil_texture": SOIL_TEXTURE_OPTIONS},
        steps=[
            WorkflowStep(
                step_key="sample_info",
                order=1,
                title={"en": "Sample Details", "hi": "Sample Details"},
                fields=[
                    WorkflowField(id="sample_date", type="DATE", label={"en": "Sample Date", "hi": "Sample Date"}, required=True, canonical_field="sample_date", default_value="today"),
                    WorkflowField(id="sample_location", type="GPS_POINT", label={"en": "Sample Location", "hi": "Sample Location"}, canonical_field="sample_location", capture_modes=["PIN_DROP"], output_format="GEOJSON"),
                    WorkflowField(id="lab_report_photo", type="PHOTO", label={"en": "Soil Health Card / Lab Report", "hi": "Soil Health Card / Lab Report"}, canonical_field="lab_report_photo", required=False, android_hint={"max_photos": 3}),
                ],
            ),
            WorkflowStep(
                step_key="field_observation",
                order=2,
                title={"en": "Field Observation", "hi": "Field Observation"},
                fields=[
                    WorkflowField(id="soil_texture", type="SINGLE_SELECT", label={"en": "Soil Texture", "hi": "Soil Texture"}, canonical_field="soil_texture", options=SOIL_TEXTURE_OPTIONS),
                    WorkflowField(id="soil_color", type="TEXT", label={"en": "Soil Color", "hi": "Soil Color"}, canonical_field="soil_color"),
                    WorkflowField(id="drainage", type="SINGLE_SELECT", label={"en": "Drainage", "hi": "Drainage"}, canonical_field="drainage", options=[WorkflowFieldOption(value="GOOD", label={"en": "Good", "hi": "Good"}), WorkflowFieldOption(value="MODERATE", label={"en": "Moderate", "hi": "Moderate"}), WorkflowFieldOption(value="POOR", label={"en": "Poor", "hi": "Poor"})]),
                ],
            ),
            WorkflowStep(
                step_key="soil_test_values",
                order=3,
                optional=True,
                title={"en": "Soil Test Values", "hi": "Soil Test Values"},
                fields=[
                    WorkflowField(id="ph", type="NUMBER", label={"en": "pH", "hi": "pH"}, canonical_field="ph", validation={"min": 0, "max": 14}),
                    WorkflowField(id="ec", type="NUMBER", label={"en": "EC", "hi": "EC"}, canonical_field="ec", validation={"min": 0}),
                    WorkflowField(id="nitrogen", type="NUMBER", label={"en": "Nitrogen", "hi": "Nitrogen"}, canonical_field="nitrogen"),
                    WorkflowField(id="phosphorus", type="NUMBER", label={"en": "Phosphorus", "hi": "Phosphorus"}, canonical_field="phosphorus"),
                    WorkflowField(id="potassium", type="NUMBER", label={"en": "Potassium", "hi": "Potassium"}, canonical_field="potassium"),
                ],
            ),
        ],
    ),
}


@router.get("/{workflow_key}", response_model=WorkflowSchema)
def get_workflow_schema(
    workflow_key: str,
    x_tenant_id: Optional[str] = Header("default", alias="X-Tenant-ID"),
    x_project_id: Optional[str] = Header(None, alias="X-Project-ID"),
):
    schema = WORKFLOW_REGISTRY.get(workflow_key)
    if not schema:
        raise HTTPException(404, f"Workflow '{workflow_key}' not found. Available: {list(WORKFLOW_REGISTRY.keys())}")

    response = deepcopy(schema)
    response.tenant_id = x_tenant_id
    response.project_id = x_project_id
    return response


@router.get("", response_model=list[dict])
def list_workflows(
    x_tenant_id: Optional[str] = Header("default", alias="X-Tenant-ID"),
):
    return [
        {
            "workflow_key": key,
            "version": schema.version,
            "entity_type": schema.entity_type,
            "title": schema.title,
            "tenant_id": x_tenant_id,
        }
        for key, schema in WORKFLOW_REGISTRY.items()
    ]
