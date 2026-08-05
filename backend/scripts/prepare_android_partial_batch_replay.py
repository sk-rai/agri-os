"""Prepare baseline for Android partial-batch offline sync replay QA.

Flow 24 uses two deterministic contexts:

A. Existing dynamic Rice/NURSERY cycle for a valid crop_activity CREATE.
B. Dedicated crop-cycle fixture farmer/parcel for a dependency-missing
   crop_stage START that can later be retried after its crop_cycle dependency
   is committed.

Android owns the local queue and generated event/entity IDs.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance
from scripts.seed_android_crop_cycle_test_fixture import (
    FARMER_ID as DEP_FARMER_ID,
    PARCEL_ID as DEP_PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
    main as seed_crop_cycle_fixture_main,
)


VALID_FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
VALID_PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
VALID_CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_partial_batch_replay_baseline.json")
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def run_dependency_fixture_seed(reset: bool) -> None:
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
    parser.add_argument("--apply", action="store_true", help="Persist fixture normalization and baseline file.")
    args = parser.parse_args()
    dry_run = not args.apply

    if not dry_run:
        run_dependency_fixture_seed(reset=True)
        run_dependency_fixture_seed(reset=False)

    db = SessionLocal()
    try:
        cycle = (
            db.query(CropCycle)
            .filter(CropCycle.id == VALID_CYCLE_ID, CropCycle.tenant_id == TENANT_ID)
            .first()
        )
        if not cycle:
            raise RuntimeError(f"valid crop cycle {VALID_CYCLE_ID} not found; run prior Android fixture setup first")

        stage = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == VALID_CYCLE_ID,
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
            )
            .first()
        )
        if not stage:
            raise RuntimeError(f"{EXPECTED_STAGE_CODE} stage not found for valid cycle {VALID_CYCLE_ID}")

        before = {
            "valid_cycle_status": cycle.status,
            "valid_cycle_actual_sowing_date": cycle.actual_sowing_date,
            "valid_stage_id": str(stage.id),
            "valid_stage_status": stage.status,
            "valid_stage_actual_start_date": stage.actual_start_date,
        }

        if not dry_run:
            cycle.status = "ACTIVE"
            cycle.actual_sowing_date = cycle.actual_sowing_date or date(2026, 8, 2)
            cycle.updated_at = datetime.now(timezone.utc)
            stage.status = "ACTIVE"
            stage.actual_start_date = stage.actual_start_date or date(2026, 8, 2)
            stage.actual_end_date = None
            stage.updated_at = datetime.now(timezone.utc)
            db.flush()

        activity_query = (
            db.query(CropActivity)
            .filter(
                CropActivity.tenant_id == TENANT_ID,
                CropActivity.crop_cycle_id == VALID_CYCLE_ID,
                CropActivity.stage_instance_id == stage.id,
            )
        )
        valid_activity_count = activity_query.count()
        latest = activity_query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()

        dep_cycles = (
            db.query(CropCycle)
            .filter(
                CropCycle.tenant_id == TENANT_ID,
                CropCycle.farmer_id == DEP_FARMER_ID,
                CropCycle.parcel_id == DEP_PARCEL_ID,
                CropCycle.season_code == SEASON_CODE,
                CropCycle.is_active == True,
            )
            .all()
        )
        dependency_existing_cycle_ids = [str(row.id) for row in dep_cycles]
    finally:
        db.close()

    stage_summary = get_json(f"/api/v1/crop-cycles/{VALID_CYCLE_ID}/stage-cost-summary")
    pnl_summary = get_json(f"/api/v1/crop-cycles/{VALID_CYCLE_ID}/profit-loss-summary")
    stage_totals = stage_summary.get("totals") or {}
    pnl_totals = pnl_summary.get("totals") or {}

    eligible = get_json(f"/api/v1/crop-cycles/eligible-parcels?farmer_id={DEP_FARMER_ID}&season={SEASON_CODE}")
    eligible_rows = eligible if isinstance(eligible, list) else eligible.get("parcels") or []
    dependency_parcel = next((row for row in eligible_rows if str(row.get("parcel_id")) == str(DEP_PARCEL_ID)), None)

    baseline = {
        "schema_version": "android_partial_batch_replay_baseline.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "valid_context": {
            "farmer_id": str(VALID_FARMER_ID),
            "parcel_id": str(VALID_PARCEL_ID),
            "cycle_id": str(VALID_CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "stage_id": str(stage.id),
            "activity_count": valid_activity_count,
            "latest_activity_id": str(latest.id) if latest else None,
            "latest_activity_created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "stage_summary_actual_expense": str(money(stage_totals.get("actual_expense"))),
            "pnl_total_expenses": str(money(pnl_totals.get("total_expenses"))),
        },
        "dependency_context": {
            "farmer_id": str(DEP_FARMER_ID),
            "parcel_id": str(DEP_PARCEL_ID),
            "season_code": SEASON_CODE,
            "existing_cycle_ids": dependency_existing_cycle_ids,
            "eligible_parcel": dependency_parcel,
        },
        "expected_valid_activity_cost": str(EXPECTED_COST),
        "dependency_id_contract": "Use sync event IDs. DEPENDENCY_MISSING is retryable and should remain pending/retryable on Android.",
    }

    if not dry_run:
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))

    result = {
        "schema_version": "android_partial_batch_replay_prepare.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "baseline_path": str(BASELINE_PATH),
        "before": before,
        "baseline": baseline,
        "ready": bool(
            cycle
            and stage
            and (stage.status == "ACTIVE" if dry_run else True)
            and dependency_parcel
            and dependency_parcel.get("eligible") is True
            and not dependency_existing_cycle_ids
        ),
        "android_payload_notes": {
            "valid_activity_dependency_ids": [],
            "missing_stage_dependency_ids": ["{missing_cycle_event_id}"],
            "dependency_ids_are_event_ids": True,
            "random_android_ids_supported": True,
            "retryable_failed_error_code": "DEPENDENCY_MISSING",
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["ready"] or dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
