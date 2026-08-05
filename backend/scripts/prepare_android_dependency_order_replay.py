"""Prepare baseline for Android dependency-ordered offline replay QA.

This creates a clean eligible farmer/parcel fixture for Android to queue:

1. crop_cycle CREATE
2. crop_stage START
3. crop_activity CREATE

Android owns the local queue and generated IDs. This script only resets the
dedicated crop-cycle fixture and records a baseline so the verifier can prove
one materialized offline story after app/device restart.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.workflow.models import CropActivity, CropCycle
from scripts.seed_android_crop_cycle_test_fixture import (
    CROP_CODE,
    FARMER_ID,
    PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
    main as seed_crop_cycle_fixture_main,
)


BASELINE_PATH = Path("/tmp/android_dependency_order_replay_baseline.json")
EXPECTED_COST = Decimal("325.50")
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def run_seed(reset: bool) -> None:
    old_argv = list(sys.argv)
    try:
        sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--apply"]
        if reset:
            sys.argv.insert(1, "--reset")
        seed_crop_cycle_fixture_main()
    finally:
        sys.argv = old_argv


def get_json(path: str) -> dict:
    response = client.get(path, headers=HEADERS)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Reset/create fixture and write baseline.")
    args = parser.parse_args()
    dry_run = not args.apply

    if not dry_run:
        run_seed(reset=True)
        run_seed(reset=False)

    db = SessionLocal()
    try:
        existing_cycles = (
            db.query(CropCycle)
            .filter(
                CropCycle.tenant_id == TENANT_ID,
                CropCycle.farmer_id == FARMER_ID,
                CropCycle.parcel_id == PARCEL_ID,
                CropCycle.crop_code == CROP_CODE,
                CropCycle.season_code == SEASON_CODE,
                CropCycle.is_active == True,
            )
            .all()
        )
        existing_cycle_ids = [str(row.id) for row in existing_cycles]
        existing_activity_count = (
            db.query(CropActivity)
            .filter(
                CropActivity.tenant_id == TENANT_ID,
                CropActivity.crop_cycle_id.in_([row.id for row in existing_cycles]),
            )
            .count()
            if existing_cycles
            else 0
        )
    finally:
        db.close()

    eligible = get_json(f"/api/v1/crop-cycles/eligible-parcels?farmer_id={FARMER_ID}&season={SEASON_CODE}")
    eligible_rows = eligible if isinstance(eligible, list) else eligible.get("parcels") or []
    fixture_parcel = next((row for row in eligible_rows if str(row.get("parcel_id")) == str(PARCEL_ID)), None)

    baseline = {
        "schema_version": "android_dependency_order_replay_baseline.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "farmer_id": str(FARMER_ID),
        "parcel_id": str(PARCEL_ID),
        "crop_code": CROP_CODE,
        "season_code": SEASON_CODE,
        "existing_cycle_ids": existing_cycle_ids,
        "existing_cycle_count": len(existing_cycle_ids),
        "existing_activity_count": existing_activity_count,
        "eligible_parcel": fixture_parcel,
        "expected_new_activity_cost": str(EXPECTED_COST),
        "expected_new_cycle_stage_cost_baseline": "0",
        "expected_new_cycle_pnl_baseline": "0",
        "dependency_id_contract": "Use sync event IDs. Backend currently accepts committed event IDs or committed entity IDs, but Android should use event IDs for queue ordering.",
    }

    if not dry_run:
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))

    result = {
        "schema_version": "android_dependency_order_replay_prepare.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "baseline_path": str(BASELINE_PATH),
        "baseline": baseline,
        "ready": bool(fixture_parcel and fixture_parcel.get("eligible") is True and not existing_cycle_ids),
        "android_payload_notes": {
            "crop_cycle_dependency_ids": [],
            "crop_stage_dependency_ids": ["{cycle_event_id}"],
            "crop_activity_dependency_ids": ["{cycle_event_id}", "{stage_event_id}"],
            "dependency_ids_are_event_ids": True,
            "random_android_ids_supported": True,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["ready"] or dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
