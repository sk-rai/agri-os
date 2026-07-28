#!/usr/bin/env python3
"""Regression for Android dynamic profile submit flow.

Uses the dedicated android-dynamic-test context:
- reset test mobile;
- verify bootstrap dynamic form flags;
- submit farmer;
- submit parcel;
- fetch land intelligence;
- submit soil profile;
- verify hydration/readiness endpoints remain Android-safe.

This script mutates only the dedicated test mobile/tenant and cleans it first.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_android_dynamic_profile_test_context import (
    PROJECT_ID,
    TENANT_ID,
    TEST_MOBILE,
    main as seed_dynamic_context_main,
)

client = TestClient(app)
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": str(uuid.uuid4())}


def check(condition, label, detail=None):
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str) if isinstance(detail, (dict, list)) else detail)
        raise AssertionError(label)
    print(f"PASS {label}")
    if detail is not None:
        print("     ", detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True, default=str)[:800])


def reset_context():
    old_argv = list(sys.argv)
    try:
        sys.argv = ["seed_android_dynamic_profile_test_context.py", "--reset", "--apply"]
        seed_dynamic_context_main()
    finally:
        sys.argv = old_argv


def get_json(path: str, params=None, headers=None):
    response = client.get(path, params=params or {}, headers=headers or HEADERS)
    return response, response.json()


def main() -> int:
    print("=" * 72)
    print("ANDROID DYNAMIC PROFILE SUBMIT FLOW REGRESSION")
    print("=" * 72)

    reset_context()

    bootstrap_response, bootstrap = get_json(
        "/api/v1/app-config/bootstrap",
        params={"project_id": str(PROJECT_ID)},
    )
    check(bootstrap_response.status_code == 200, "Bootstrap returns 200", bootstrap_response.text[:500])
    flags = bootstrap.get("feature_flags") or {}
    forms = bootstrap.get("profile_forms") or {}

    for flag in ["backend_driven_farmer_forms", "backend_driven_parcel_forms", "backend_driven_soil_forms"]:
        check(flags.get(flag) is True, f"{flag} true", flags)

    for form_id in ["farmer_registration", "parcel_registration", "soil_profile"]:
        check((forms.get(form_id) or {}).get("enabled") is True, f"{form_id} enabled", forms.get(form_id))

    for form_id in ["farmer_registration", "parcel_registration", "soil_profile"]:
        response, form = get_json(f"/api/v1/forms/{form_id}", params={"project_id": str(PROJECT_ID)})
        check(response.status_code == 200, f"{form_id} form returns 200", response.text[:500])
        check(bool(form.get("submit_endpoint")), f"{form_id} submit endpoint present", form.get("submit_endpoint"))

    farmer_payload = {
        "mobile_number": TEST_MOBILE,
        "display_name": "Android Dynamic Test Farmer",
        "father_name": "Dynamic Test Father",
        "age": 39,
        "gender": "MALE",
        "pin_code": "560001",
        "village_name_manual": "Android Dynamic Test Village",
        "primary_crop_code": "RICE",
        "assistance_mode": "SELF_SERVICE",
        "consent": {
            "profile_data": True,
            "location": True,
            "advisories": True,
        },
    }
    farmer_response = client.post("/api/v1/farmers", json=farmer_payload, headers=HEADERS)
    check(farmer_response.status_code in {200, 201}, "Farmer create accepts Android payload", farmer_response.text[:800])
    farmer = farmer_response.json()
    farmer_id = farmer.get("id") or farmer.get("farmer_id")
    check(bool(farmer_id), "Farmer response exposes id", farmer)

    parcel_payload = {
        "farmer_id": farmer_id,
        "project_id": str(PROJECT_ID),
        "area": "1.25",
        "area_unit": "ACRE",
        "reported_area": "1.25",
        "reported_area_unit": "ACRE",
        "ownership_type": "OWNED",
        "pin_code": "560001",
        "village_name_manual": "Android Dynamic Test Village",
        "location_scope": {
            "scope_type": "SINGLE_VILLAGE",
            "village_name_manual": "Android Dynamic Test Village",
            "pin_code": "560001",
        },
        "geometry_source": "PIN_DROP",
        "centroid_lat": "15.4589",
        "centroid_lng": "75.0078",
    }
    parcel_response = client.post("/api/v1/parcels", json=parcel_payload, headers=HEADERS)
    check(parcel_response.status_code in {200, 201}, "Parcel create accepts Android payload", parcel_response.text[:800])
    parcel = parcel_response.json()
    parcel_id = parcel.get("id") or parcel.get("parcel_id")
    check(bool(parcel_id), "Parcel response exposes id", parcel)

    land_response, land = get_json(
        "/api/v1/profile/land-intelligence-context",
        params={"pin_code": "560001", "crop_code": "RICE", "season_code": "KHARIF"},
    )
    check(land_response.status_code == 200, "Land intelligence returns 200", land_response.text[:800])
    check(bool(land.get("climate_context")), "Land intelligence has climate_context")
    check(bool(land.get("soil_capture_guidance")), "Land intelligence has soil_capture_guidance")
    check(bool(land.get("crop_suitability")), "Land intelligence has crop_suitability")

    soil_payload = {
        "farmer_id": farmer_id,
        "parcel_id": parcel_id,
        "project_id": str(PROJECT_ID),
        "data_source": "MANUAL",
        "test_date": str(date.today()),
        "soil_texture": "LOAM",
        "ph": "7.1",
        "organic_carbon": "0.60",
        "nitrogen_level": "MEDIUM",
        "phosphorus_level": "MEDIUM",
        "potassium_level": "MEDIUM",
        "boron_b": "0.45",
    }
    soil_response = client.post("/api/v1/soil-profiles", json=soil_payload, headers=HEADERS)
    check(soil_response.status_code in {200, 201}, "Soil profile create accepts Android payload", soil_response.text[:800])
    soil = soil_response.json()
    check(bool(soil.get("id") or soil.get("profile_id")), "Soil response exposes id", soil)

    hydration_response, hydration = get_json(f"/api/v1/farmers/by-mobile/{TEST_MOBILE}")
    check(hydration_response.status_code == 200, "Hydration by mobile returns 200", hydration_response.text[:800])
    check(bool(hydration.get("farmer") or hydration.get("farmers") or hydration.get("profile")), "Hydration returns profile payload")

    readiness_response, readiness = get_json("/api/v1/farmers/profile-readiness", params={"project_id": str(PROJECT_ID)})
    check(readiness_response.status_code == 200, "Profile readiness returns 200", readiness_response.text[:800])
    check(readiness.get("schema_version") == "farmer_profile_readiness.v1", "Profile readiness schema stable", readiness.get("schema_version"))

    print("=" * 72)
    print("Android dynamic profile submit flow validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
