"""Prepare backend baseline for Android cold-start offline sync persistence QA.

This does not create a pending sync row. Android owns the local queue.

The script ensures the known Android dynamic Rice cycle and NURSERY stage are
ACTIVE, records the current NURSERY activity count/timestamp baseline, and
writes that baseline to /tmp so the verifier can prove a new activity appeared
after Android app relaunch + Sync Now.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = "325.50"
BASELINE_PATH = Path("/tmp/android_cold_start_activity_persistence_baseline.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist ACTIVE cycle/stage normalization and baseline file.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        cycle = (
            db.query(CropCycle)
            .filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID)
            .first()
        )
        if not cycle:
            raise RuntimeError(f"crop cycle {CYCLE_ID} not found; run prior Android fixture setup first")

        stage = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == CYCLE_ID,
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
            )
            .first()
        )
        if not stage:
            raise RuntimeError(f"{EXPECTED_STAGE_CODE} stage not found for cycle {CYCLE_ID}")

        before = {
            "cycle_status": cycle.status,
            "cycle_actual_sowing_date": cycle.actual_sowing_date,
            "stage_id": str(stage.id),
            "stage_status": stage.status,
            "stage_actual_start_date": stage.actual_start_date,
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

        query = (
            db.query(CropActivity)
            .filter(
                CropActivity.tenant_id == TENANT_ID,
                CropActivity.crop_cycle_id == CYCLE_ID,
                CropActivity.stage_instance_id == stage.id,
            )
        )
        activity_count = query.count()
        latest = query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()
        baseline = {
            "schema_version": "android_cold_start_activity_persistence_baseline.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "stage_id": str(stage.id),
            "activity_count": activity_count,
            "latest_activity_id": str(latest.id) if latest else None,
            "latest_activity_created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "expected_new_activity_cost": EXPECTED_COST,
        }

        if dry_run:
            db.rollback()
        else:
            db.commit()
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))

        result = {
            "schema_version": "android_cold_start_activity_persistence_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "baseline_path": str(BASELINE_PATH),
            "before": before,
            "after": {
                "cycle_status": "ACTIVE" if dry_run else cycle.status,
                "stage_status": "ACTIVE" if dry_run else stage.status,
                "stage_id": str(stage.id),
            },
            "baseline": baseline,
            "android_payload_notes": {
                "entity_type": "crop_activity",
                "operation": "CREATE",
                "android_may_generate_random_event_id": True,
                "android_may_generate_random_activity_id": True,
                "required_cost_amount": EXPECTED_COST,
                "dependency_ids": [],
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
