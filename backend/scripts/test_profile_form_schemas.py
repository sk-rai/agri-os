"""Regression for backend-driven profile/parcel/soil form schemas."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def get_form(form_id: str) -> dict:
    response = client.get(f"/api/v1/forms/{form_id}")
    check(response.status_code == 200, f"{form_id} returns 200", response.text[:300])
    payload = response.json()
    check(payload["form_id"] == form_id, f"{form_id} echoes form_id")
    check(payload["version"] == "1.0.0", f"{form_id} has stable initial version")
    check(isinstance(payload["fields"], list) and payload["fields"], f"{form_id} has fields")
    return payload


def by_id(form: dict) -> dict:
    return {field["id"]: field for field in form["fields"]}


def main():
    print("=" * 72)
    print("PROFILE FORM SCHEMA REGRESSION")
    print("=" * 72)

    farmer = get_form("farmer_registration")
    farmer_fields = by_id(farmer)
    for field_id in [
        "mobile_number",
        "village_id",
        "village_name_manual",
        "pin_code",
        "display_name",
        "primary_crop_code",
        "total_land_area",
        "total_land_unit",
        "aadhaar_number",
        "language_preference",
        "assistance_mode",
        "enrollment_location",
    ]:
        check(field_id in farmer_fields, f"farmer_registration includes {field_id}")
    check(farmer_fields["mobile_number"]["required"] is True, "mobile number is required")
    check(farmer_fields["mobile_number"]["type"] == "phone", "mobile number uses phone input")
    check(farmer_fields["mobile_number"]["canonical_field"] == "farmer.mobile_number", "mobile number canonical field")
    check(farmer_fields["assistance_mode"]["android_hint"]["payload_field"] == "assistance_mode", "assistance mode preserves Android payload name")
    check(farmer_fields["enrollment_location"]["type"] == "GPS_POINT", "farmer enrollment location uses GPS_POINT")

    parcel = get_form("parcel_registration")
    parcel_fields = by_id(parcel)
    for field_id in [
        "farmer_id",
        "village_id",
        "village_name_manual",
        "reported_area",
        "reported_area_unit",
        "ownership_type",
        "share_percentage",
        "sharecrop_percentage",
        "annual_rent",
        "irrigation_source",
        "geometry_source",
        "kharif_crops",
        "rabi_crops",
        "zaid_crops",
        "soil_texture",
        "soil_color",
        "parcel_point",
        "parcel_boundary",
    ]:
        check(field_id in parcel_fields, f"parcel_registration includes {field_id}")
    check(parcel_fields["annual_rent"]["depends_on"] == "ownership_type", "annual rent depends on ownership")
    check(parcel_fields["annual_rent"]["depends_on_value"] == "LEASED", "annual rent only visible for leased parcels")
    check(parcel_fields["share_percentage"]["depends_on_value"] == "SHARED", "share percentage only visible for shared parcels")
    check(parcel_fields["sharecrop_percentage"]["depends_on_value"] == "SHARECROP", "sharecrop percentage only visible for sharecrop parcels")
    check(parcel_fields["geometry_source"]["default_value"] == "NONE", "geometry source defaults to NONE")
    check(parcel_fields["parcel_point"]["type"] == "GPS_POINT", "parcel point uses GPS_POINT")
    check(parcel_fields["parcel_boundary"]["type"] == "GPS_POLYGON", "parcel boundary uses GPS_POLYGON")
    check(parcel_fields["parcel_boundary"]["output_format"] == "geojson_polygon", "parcel boundary outputs polygon GeoJSON")

    soil = get_form("soil_profile")
    soil_fields = by_id(soil)
    for field_id in [
        "parcel_id",
        "farmer_id",
        "data_source",
        "soil_type_code",
        "soil_texture",
        "soil_color",
        "inferred_soil_type",
        "test_date",
        "ph",
        "nitrogen_n",
        "phosphorus_p",
        "potassium_k",
        "organic_carbon_oc",
        "boron_b",
        "notes",
    ]:
        check(field_id in soil_fields, f"soil_profile includes {field_id}")
    check(soil_fields["lab_name"]["depends_on_value"] == "LAB_REPORT", "lab name only visible for lab reports")
    check(soil_fields["shc_card_number"]["depends_on_value"] == "SHC_CARD", "SHC card only visible for SHC source")
    check(soil_fields["ph"]["validation"]["max"] == 14, "pH validation max is 14")
    check(soil_fields["boron_b"]["canonical_field"] == "soil_profile.boron_bo", "Android boron_b maps to backend boron_bo")

    forms_response = client.get("/api/v1/forms")
    check(forms_response.status_code == 200, "form list returns 200", forms_response.text[:300])
    listed = {item["form_id"] for item in forms_response.json()}
    check({"farmer_registration", "parcel_registration", "soil_profile"}.issubset(listed), "form list includes profile forms")

    print("=" * 72)
    print("Profile form schemas validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
