#!/usr/bin/env python3
"""Regression for Android crop-cycle stage + activity logging flow.

Uses the deterministic android-dynamic-test crop-cycle fixture:
- reset/reseed farmer + parcel;
- create a Rice/Kharif crop cycle;
- start the first stage;
- log a stage-linked activity with cost;
- verify activity list, stage-cost summary, and P&L summary update.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
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
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}
ACTIVITY_COST = Decimal("325.50")


def check(condition, label, detail=None):
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str) if isinstance(detail, (dict, list)) else detail)
        raise AssertionError(label)
    print(f"PASS {label}")
    if detail is not None:
        print("     ", detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True, default=str)[:900])


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


def main() -> int:
    print("=" * 72)
    print("ANDROID CROP-CYCLE ACTIVITY LOGGING FLOW REGRESSION")
    print("=" * 72)

    reset_fixture()

    create_payload = {
        "farmer_id": str(FARMER_ID),
        "parcel_id": str(PARCEL_ID),
        "project_id": str(PROJECT_ID),
        "crop_code": CROP_CODE,
        "season_code": SEASON_CODE,
        "planned_sowing_date": (date.today() + timedelta(days=7)).isoformat(),
        "seed_source": "OWN_SAVED",
    }
    create_response = client.post("/api/v1/crop-cycles", json=create_payload, headers=HEADERS)
    check(create_response.status_code == 201, "Crop-cycle create returns 201", create_response.text[:1000])
    cycle = create_response.json()
    cycle_id = cycle.get("id")
    stages = cycle.get("stages") or []
    check(bool(cycle_id), "Crop-cycle id present", cycle)
    check(bool(stages), "Crop-cycle stages present", {"stage_count": len(stages)})

    first_stage = stages[0]
    stage_id = first_stage["id"]
    stage_code = first_stage["code"]
    start_response = client.patch(
        f"/api/v1/crop-cycles/{cycle_id}/stages/{stage_id}",
        json={"action": "START", "gps_lat": 15.4589, "gps_lng": 75.0078, "notes": "Android regression start first stage"},
        headers=HEADERS,
    )
    check(start_response.status_code == 200, "First stage START transition returns 200", start_response.text[:1000])
    start_payload = start_response.json()
    check(start_payload.get("new_status") == "ACTIVE", "First stage is ACTIVE", start_payload)
    check(start_payload.get("cycle_status") == "ACTIVE", "Crop cycle becomes ACTIVE after first stage START", start_payload)

    activity_payload = {
        "activity_type": "LABOR",
        "input_name": "Nursery bed preparation labor",
        "quantity": "1",
        "quantity_unit": "DAY",
        "area_applied": "1.25",
        "area_unit": "ACRE",
        "cost_amount": str(ACTIVITY_COST),
        "activity_date": date.today().isoformat(),
        "gps_lat": 15.4589,
        "gps_lng": 75.0078,
        "notes": "Android regression activity log",
    }
    activity_response = client.post(f"/api/v1/crop-cycles/{cycle_id}/activities", json=activity_payload, headers=HEADERS)
    check(activity_response.status_code == 201, "Activity log accepts Android payload", activity_response.text[:1000])
    activity = activity_response.json()
    activity_id = activity.get("activity_id")
    check(bool(activity_id), "Activity response exposes activity_id", activity)
    check(activity.get("stage_code") == stage_code, "Activity is linked to active stage", activity)
    check(activity.get("cycle_total_input_cost") == str(ACTIVITY_COST), "Cycle total input cost updated", activity)

    list_response, activities = get_json(f"/api/v1/crop-cycles/{cycle_id}/activities")
    check(list_response.status_code == 200, "Activity list returns 200", list_response.text[:1000])
    logged = next((row for row in activities if row.get("id") == activity_id), None)
    check(bool(logged), "Logged activity appears in activity list", activities)
    check(logged.get("stage_code") == stage_code, "Activity list preserves stage_code", logged)
    check(logged.get("cost_amount") == str(ACTIVITY_COST), "Activity list preserves cost_amount", logged)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    check(stage_summary.get("schema_version") == "crop_cycle_stage_cost_summary.v1", "Stage-cost summary schema stable", stage_summary.get("schema_version"))
    check((stage_summary.get("totals") or {}).get("activity_count") == 1, "Stage-cost summary activity_count updated", stage_summary.get("totals"))
    check((stage_summary.get("totals") or {}).get("actual_expense") == str(ACTIVITY_COST), "Stage-cost summary actual expense updated", stage_summary.get("totals"))
    stage_row = next((row for row in stage_summary.get("stage_summaries") or [] if row.get("stage_code") == stage_code), None)
    check(bool(stage_row), "Stage-cost summary includes active stage row", stage_summary.get("stage_summaries"))
    check(stage_row.get("activity_count") == 1, "Active stage summary activity_count updated", stage_row)
    check(stage_row.get("actual_expense") == str(ACTIVITY_COST), "Active stage actual expense updated", stage_row)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{cycle_id}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    check(pnl.get("schema_version") == "crop_cycle_profit_loss_summary.v1", "P&L summary schema stable", pnl.get("schema_version"))
    check((pnl.get("totals") or {}).get("total_expenses") == str(ACTIVITY_COST), "P&L total expenses updated", pnl.get("totals"))

    print("=" * 72)
    print("Android crop-cycle activity logging flow validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())