"""Regression for backend-driven profile form contracts."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Tenant


REQUIRED_FORMS = {"farmer_registration", "parcel_registration", "soil_profile"}
REQUIRED_FLAGS = {
    "backend_driven_farmer_forms",
    "backend_driven_parcel_forms",
    "backend_driven_soil_forms",
}


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant():
    db = SessionLocal()
    try:
        if not db.query(Tenant).filter(Tenant.id == "default").first():
            db.add(Tenant(id="default", name="Default", type="ENTERPRISE"))
            db.commit()
    finally:
        db.close()


def field_by_id(schema, field_id):
    for field in schema["fields"]:
        if field["id"] == field_id:
            return field
    return None


def main():
    print("=" * 72)
    print("PROFILE FORM CONTRACT REGRESSION")
    print("=" * 72)
    ensure_tenant()
    client = TestClient(app)

    bootstrap = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": "default"})
    check(bootstrap.status_code == 200, "Bootstrap returns 200", bootstrap.text[:400])
    payload = bootstrap.json()
    check(payload["schema_version"] == "app_bootstrap.v1", "Bootstrap schema version is stable")
    check("profile_forms" in payload, "Bootstrap advertises profile_forms")
    check(REQUIRED_FLAGS.issubset(set(payload["feature_flags"].keys())), "Bootstrap exposes profile form feature flags")
    advertised = payload["profile_forms"]
    check(REQUIRED_FORMS.issubset(set(advertised.keys())), "Bootstrap advertises required profile forms", advertised.keys())

    schemas = {}
    for form_id in sorted(REQUIRED_FORMS):
        contract = advertised[form_id]
        check(contract["form_id"] == form_id, f"{form_id} contract echoes form id")
        check(contract["endpoint"] == f"/api/v1/forms/{form_id}", f"{form_id} endpoint is stable")
        check(contract["feature_flag"] in REQUIRED_FLAGS, f"{form_id} references a profile feature flag")
        response = client.get(contract["endpoint"], headers={"X-Tenant-ID": "default"})
        check(response.status_code == 200, f"{form_id} schema endpoint returns 200", response.text[:300])
        schema = response.json()
        schemas[form_id] = schema
        check(schema["form_id"] == form_id, f"{form_id} schema echoes form id")
        check(bool(schema["version"]), f"{form_id} has version")
        check(bool(schema["submit_endpoint"]), f"{form_id} has submit endpoint")
        check(isinstance(schema["fields"], list) and len(schema["fields"]) > 0, f"{form_id} has fields")
        check(all("id" in field and "type" in field and "label" in field for field in schema["fields"]), f"{form_id} fields include id/type/label")

    farmer = schemas["farmer_registration"]
    check(field_by_id(farmer, "mobile_number") is not None, "Farmer form includes mobile_number")
    check(field_by_id(farmer, "mobile_number")["required"] is True, "Farmer mobile_number is required")
    check(field_by_id(farmer, "enrollment_location")["type"] == "GPS_POINT", "Farmer form includes GPS_POINT enrollment location")

    parcel = schemas["parcel_registration"]
    parcel_types = {field["type"] for field in parcel["fields"]}
    check("GPS_POINT" in parcel_types, "Parcel form includes GPS_POINT")
    check("GPS_POLYGON" in parcel_types, "Parcel form includes GPS_POLYGON")
    annual_rent = field_by_id(parcel, "annual_rent")
    check(annual_rent["depends_on"] == "ownership_type", "Parcel annual_rent depends on ownership_type")
    check(annual_rent["depends_on_value"] == "LEASED", "Parcel annual_rent serializes depends_on_value")

    soil = schemas["soil_profile"]
    lab_name = field_by_id(soil, "lab_name")
    shc = field_by_id(soil, "shc_card_number")
    check(lab_name["depends_on"] == "data_source" and lab_name["depends_on_value"] == "LAB_REPORT", "Soil lab_name conditional metadata is serialized")
    check(shc["depends_on"] == "data_source" and shc["depends_on_value"] == "SHC_CARD", "Soil SHC conditional metadata is serialized")

    print("=" * 72)
    print("Profile form contracts validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
