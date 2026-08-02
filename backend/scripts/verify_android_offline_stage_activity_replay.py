#!/usr/bin/env python3
"""Read-only verifier for Android offline stage/activity replay on dynamic test cycle."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app

TENANT_ID = "android-dynamic-test"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
STAGE_EVENT_ID = "9f7df9e8-97f9-4db6-9d3a-fc9bb0e20101"
ACTIVITY_EVENT_ID = "9f7df9e8-97f9-4db6-9d3a-fc9bb0e20102"
ACTIVITY_ID = "9f7df9e8-97f9-4db6-9d3a-fc9bb0e20103"
EXPECTED_COST = "325.50"
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def check(condition, label, detail=None):
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str) if isinstance(detail, (dict, list)) else detail)
        raise AssertionError(label)
    print(f"PASS {label}")
    if detail is not None:
        print("     ", json.dumps(detail, sort_keys=True, default=str)[:900] if isinstance(detail, (dict, list)) else detail)


def get_json(path: str):
    response = client.get(path, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def main() -> int:
    print("=" * 72)
    print("ANDROID OFFLINE STAGE/ACTIVITY REPLAY VERIFIER")
    print("=" * 72)

    cycle_response, cycle = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}")
    check(cycle_response.status_code == 200, "Crop cycle fetch returns 200", cycle_response.text[:900])
    check(cycle.get("id") == CYCLE_ID, "Crop cycle id matches", cycle.get("id"))
    check(cycle.get("status") == "ACTIVE", "Crop cycle is ACTIVE after stage replay", cycle)
    check(cycle.get("inferred_current_stage") == "NURSERY", "Current stage is NURSERY", cycle)
    nursery = next((stage for stage in cycle.get("stages") or [] if stage.get("code") == "NURSERY"), None)
    check(bool(nursery), "NURSERY stage exists", cycle.get("stages"))
    check(nursery.get("status") == "ACTIVE", "NURSERY stage is ACTIVE", nursery)

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:900])
    activity = next((row for row in activities if row.get("id") == ACTIVITY_ID), None)
    check(bool(activity), "Expected offline activity id is present", activities)
    check(activity.get("stage_code") == "NURSERY", "Activity is linked to NURSERY", activity)
    check(activity.get("cost_amount") == EXPECTED_COST, "Activity cost is preserved", activity)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:900])
    totals = stage_summary.get("totals") or {}
    check(totals.get("activity_count") == 1, "Stage-cost summary activity_count is 1", totals)
    check(totals.get("actual_expense") == EXPECTED_COST, "Stage-cost summary actual_expense is 325.50", totals)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:900])
    pnl_totals = pnl.get("totals") or {}
    check(pnl_totals.get("total_expenses") == EXPECTED_COST, "P&L total_expenses is 325.50", pnl_totals)
    check(pnl_totals.get("profit_or_loss") == "-325.50", "P&L profit_or_loss reflects activity expense", pnl_totals)

    print("=" * 72)
    print("Android offline stage/activity replay verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
