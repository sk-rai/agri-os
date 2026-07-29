#!/usr/bin/env python3
"""Regression for Android crop-cycle creation flow.

Uses the deterministic android-dynamic-test crop-cycle fixture:
- reset/reseed farmer + parcel;
- verify eligible parcel picker;
- verify RICE/KHARIF template;
- create crop cycle;
- verify duplicate create is blocked;
- verify eligible-parcels no longer exposes the parcel as eligible.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_android_crop_cycle_test_fixture import (
    CROP_CODE,
    FARMER_ID,
    PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
    main as seed_crop_cycle_fixture_main,
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


def reset_fixture():
    old_argv = list(sys.argv)
    try:
        sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--reset", "--apply"]
        seed_crop_cycle_fixture_main()
        sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--apply"]
        seed_crop_cycle_fixture_main()
    finally:
        sys.argv = old_argv


def get_json(path: str, params=None):
    response = client.get(path, params=params or {}, headers=HEADERS)
    return response, response.json()


def fixture_parcel_row(rows: list[dict]) -> dict | None:
    return next((row for row in rows if row.get("parcel_id") == str(PARCEL_ID)), None)


def main() -> int:
    print("=" * 72)
    print("ANDROID CROP-CYCLE CREATE FLOW REGRESSION")
    print("=" * 72)

    reset_fixture()

    eligible_response, eligible_rows = get_json(
        "/api/v1/crop-cycles/eligible-parcels",
        params={"farmer_id": str(FARMER_ID), "season": SEASON_CODE, "season_year": date.today().year},
    )
    check(eligible_response.status_code == 200, "Eligible parcels returns 200", eligible_response.text[:800])
    check(isinstance(eligible_rows, list), "Eligible parcels response is a list", eligible_rows)
    before_row = fixture_parcel_row(eligible_rows)
    check(bool(before_row), "Fixture parcel appears in eligible-parcels", eligible_rows)
    check(before_row.get("eligible") is True, "Fixture parcel is eligible before crop-cycle create", before_row)

    template_response, template = get_json(f"/api/v1/crop-cycles/templates/{CROP_CODE}", params={"season": SEASON_CODE})
    check(template_response.status_code == 200, "Rice Kharif template returns 200", template_response.text[:800])
    check((template.get("stages") or []), "Rice Kharif template has stages", {"stage_count": len(template.get("stages") or [])})

    planned_sowing_date = date.today() + timedelta(days=7)
    create_payload = {
        "farmer_id": str(FARMER_ID),
        "parcel_id": str(PARCEL_ID),
        "project_id": str(PROJECT_ID),
        "crop_code": CROP_CODE,
        "season_code": SEASON_CODE,
        "planned_sowing_date": planned_sowing_date.isoformat(),
        "seed_source": "OWN_SAVED",
    }
    create_response = client.post("/api/v1/crop-cycles", json=create_payload, headers=HEADERS)
    check(create_response.status_code == 201, "Crop-cycle create accepts Android payload", create_response.text[:1000])
    cycle = create_response.json()
    cycle_id = cycle.get("id")
    check(bool(cycle_id), "Crop-cycle response exposes id", cycle)
    check(cycle.get("status") in {"PLANNED", "ACTIVE"}, "Crop-cycle response exposes Android-safe status", cycle)
    check(cycle.get("parcel_id") == str(PARCEL_ID), "Crop-cycle response parcel_id stable", cycle)
    check(cycle.get("farmer_id") == str(FARMER_ID), "Crop-cycle response farmer_id stable", cycle)
    check(cycle.get("crop_code") == CROP_CODE, "Crop-cycle response crop_code stable", cycle)
    check(cycle.get("season_code") == SEASON_CODE, "Crop-cycle response season_code stable", cycle)
    check((cycle.get("stages") or []), "Crop-cycle response includes stage schedule", {"stage_count": len(cycle.get("stages") or [])})

    duplicate_response = client.post("/api/v1/crop-cycles", json=create_payload, headers=HEADERS)
    check(duplicate_response.status_code == 409, "Duplicate crop-cycle create is blocked", duplicate_response.text[:800])

    cycles_response, cycles = get_json("/api/v1/crop-cycles", params={"farmer_id": str(FARMER_ID)})
    check(cycles_response.status_code == 200, "Crop-cycle list returns 200", cycles_response.text[:800])
    check(any(row.get("id") == cycle_id for row in cycles), "Created crop-cycle appears in list", cycles)

    after_response, after_rows = get_json(
        "/api/v1/crop-cycles/eligible-parcels",
        params={"farmer_id": str(FARMER_ID), "season": SEASON_CODE, "season_year": planned_sowing_date.year},
    )
    check(after_response.status_code == 200, "Eligible parcels after create returns 200", after_response.text[:800])
    after_row = fixture_parcel_row(after_rows)
    check(bool(after_row), "Fixture parcel still appears after create", after_rows)
    check(after_row.get("eligible") is False, "Fixture parcel is no longer eligible after crop-cycle create", after_row)
    check(bool(after_row.get("active_cycle")), "In-progress cycle summary is attached to eligible-parcels row", after_row)

    print("=" * 72)
    print("Android crop-cycle create flow validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())