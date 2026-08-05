"""Prepare baseline for Android partial-batch success + conflict QA.

Flow 25 sends one batch containing:

1. a valid crop_activity CREATE under the existing active Rice/NURSERY cycle;
2. a deterministic WORKFLOW_INVALID crop_stage START against already ACTIVE
   NURSERY.

The backend should commit the activity and return the stage event unde
conflicts[] in the same HTTP 200 sync response.
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
from app.modules.sync.models import SyncConflict, SyncProcessedEvent
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_partial_batch_conflict_baseline.json")
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def get_json(path: str) -> dict:
    response = client.get(path, headers=HEADERS)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def delete_prior_rows(db, dry_run: bool, event_ids: list[str], entity_ids: list[str]) -> dict:
    counts: dict[str, int] = {}
    event_uuids = [uuid.UUID(str(item)) for item in event_ids if item]
    entity_uuids = [uuid.UUID(str(item)) for item in entity_ids if item]

    if event_uuids:
        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id.in_(event_uuids),
        ).all()
        counts["sync_conflicts"] = len(conflicts)
        if not dry_run:
            for row in conflicts:
                db.delete(row)

        processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id.in_(event_uuids),
        ).all()
        counts["sync_processed_events"] = len(processed)
        if not dry_run:
            for row in processed:
                db.delete(row)
    else:
        counts["sync_conflicts"] = 0
        counts["sync_processed_events"] = 0

    if entity_uuids:
        activities = db.query(CropActivity).filter(
            CropActivity.tenant_id == TENANT_ID,
            CropActivity.id.in_(entity_uuids),
        ).all()
        counts["crop_activities"] = len(activities)
        if not dry_run:
            for row in activities:
                db.delete(row)
    else:
        counts["crop_activities"] = 0

    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist ACTIVE stage normalization and baseline file.")
    parser.add_argument("--reset-event-id", action="append", default=[], help="Optional Android event id to clear before rerun.")
    parser.add_argument("--reset-entity-id", action="append", default=[], help="Optional Android entity/activity id to clear before rerun.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        reset_counts = delete_prior_rows(db, dry_run, args.reset_event_id, args.reset_entity_id)

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

        activity_query = (
            db.query(CropActivity)
            .filter(
                CropActivity.tenant_id == TENANT_ID,
                CropActivity.crop_cycle_id == CYCLE_ID,
                CropActivity.stage_instance_id == stage.id,
            )
        )
        activity_count = activity_query.count()
        latest = activity_query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()
    finally:
        db.close()

    stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    pnl_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    stage_totals = stage_summary.get("totals") or {}
    pnl_totals = pnl_summary.get("totals") or {}

    baseline = {
        "schema_version": "android_partial_batch_conflict_baseline.v1",
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
        "stage_summary_actual_expense": str(money(stage_totals.get("actual_expense"))),
        "pnl_total_expenses": str(money(pnl_totals.get("total_expenses"))),
        "expected_new_activity_cost": str(EXPECTED_COST),
        "conflict_contract": {
            "entity_type": "crop_stage",
            "operation": "UPDATE",
            "stage_code": EXPECTED_STAGE_CODE,
            "invalid_action": "START",
            "server_stage_status": "ACTIVE",
            "expected_conflict_type": "WORKFLOW_INVALID",
            "expected_resolution_strategy": "SERVER_AUTHORITY",
        },
    }

    if not dry_run:
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))

    result = {
        "schema_version": "android_partial_batch_conflict_prepare.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "baseline_path": str(BASELINE_PATH),
        "before": before,
        "baseline": baseline,
        "reset": {
            "requested_event_ids": args.reset_event_id,
            "requested_entity_ids": args.reset_entity_id,
            "deleted_counts": reset_counts,
        },
        "ready": True,
        "android_payload_notes": {
            "valid_activity_dependency_ids": [],
            "conflict_stage_dependency_ids": [],
            "random_android_ids_supported": True,
            "android_action_for_conflict": "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE",
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
