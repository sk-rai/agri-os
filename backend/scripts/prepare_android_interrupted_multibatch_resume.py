"""Prepare baseline for Android interrupted multi-batch replay resume QA.

Flow 28 uses 25 offline crop_activity CREATE events under the existing active
Android dynamic Rice/NURSERY cycle. Android commits the first bounded batch, is
interrupted, then resumes the remaining queue after app/backend restart.
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
DEFAULT_COUNT = 25
DEFAULT_AMOUNT = Decimal("20.00")
SOURCE = "android_maestro_interrupted_multibatch_resume_test"
NOTE_PREFIX = "Interrupted resume activity"
BASELINE_PATH = Path("/tmp/android_interrupted_multibatch_resume_baseline.json")
MANIFEST_PATH = Path("/tmp/android_interrupted_multibatch_resume_sample_events.json")
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def get_json(path: str) -> dict:
    response = client.get(path, headers=HEADERS)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def note_for_index(index: int) -> str:
    return f"{NOTE_PREFIX} {index:02d} source={SOURCE}"


def delete_prior_indexed_rows(db, stage_id: uuid.UUID, count: int, dry_run: bool) -> dict:
    notes = [note_for_index(index) for index in range(1, count + 1)]
    event_ids = [
        uuid.uuid5(uuid.NAMESPACE_URL, f"farmint-flow28-event-{index}")
        for index in range(1, count + 1)
    ]
    conflicts = db.query(SyncConflict).filter(
        SyncConflict.tenant_id == TENANT_ID,
        SyncConflict.event_id.in_(event_ids),
    ).all()
    processed_events = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.tenant_id == TENANT_ID,
        SyncProcessedEvent.event_id.in_(event_ids),
    ).all()
    activities = db.query(CropActivity).filter(
        CropActivity.tenant_id == TENANT_ID,
        CropActivity.crop_cycle_id == CYCLE_ID,
        CropActivity.stage_instance_id == stage_id,
        CropActivity.notes.in_(notes),
    ).all()
    if not dry_run:
        for row in conflicts:
            db.delete(row)
        for row in processed_events:
            db.delete(row)
        for row in activities:
            db.delete(row)
    return {
        "crop_activities": len(activities),
        "sync_conflicts": len(conflicts),
        "sync_processed_events": len(processed_events),
    }


def sample_event(index: int, amount: Decimal) -> dict:
    event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"farmint-flow28-event-{index}")
    activity_id = uuid.uuid5(uuid.NAMESPACE_URL, f"farmint-flow28-activity-{index}")
    return {
        "event_id": str(event_id),
        "entity_type": "crop_activity",
        "entity_id": str(activity_id),
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "activity_date": date(2026, 8, 2).isoformat(),
            "activity_type": "LABOR",
            "input_name": "Interrupted resume labor log",
            "quantity": 1,
            "quantity_unit": "HOURS",
            "cost_amount": float(amount),
            "currency": "INR",
            "notes": note_for_index(index),
        },
        "metadata": {
            "source": SOURCE,
            "interrupted_resume_index": index,
            "interrupted_resume_count": DEFAULT_COUNT,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--amount", default=str(DEFAULT_AMOUNT))
    parser.add_argument("--reset-indexed", action="store_true", help="Delete prior activities with the canonical Flow 28 notes before baselining.")
    args = parser.parse_args()
    dry_run = not args.apply
    count = int(args.count)
    amount = money(args.amount)
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")

    db = SessionLocal()
    try:
        cycle = db.query(CropCycle).filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID).first()
        if not cycle:
            raise RuntimeError(f"crop cycle {CYCLE_ID} not found; run Android dynamic fixture first")
        stage = db.query(CropStageInstance).filter(
            CropStageInstance.crop_cycle_id == CYCLE_ID,
            CropStageInstance.tenant_id == TENANT_ID,
            CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
        ).first()
        if not stage:
            raise RuntimeError(f"{EXPECTED_STAGE_CODE} stage not found for cycle {CYCLE_ID}")

        before = {
            "cycle_status": cycle.status,
            "cycle_actual_sowing_date": cycle.actual_sowing_date,
            "stage_id": str(stage.id),
            "stage_status": stage.status,
            "stage_actual_start_date": stage.actual_start_date,
        }

        reset_counts = {}
        if args.reset_indexed:
            reset_counts = delete_prior_indexed_rows(db, stage.id, count, dry_run)
            if not dry_run:
                db.flush()

        if not dry_run:
            cycle.status = "ACTIVE"
            cycle.actual_sowing_date = cycle.actual_sowing_date or date(2026, 8, 2)
            cycle.updated_at = datetime.now(timezone.utc)
            stage.status = "ACTIVE"
            stage.actual_start_date = stage.actual_start_date or date(2026, 8, 2)
            stage.actual_end_date = None
            stage.updated_at = datetime.now(timezone.utc)
            db.commit()
            cycle = db.query(CropCycle).filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID).first()
            stage = db.query(CropStageInstance).filter(
                CropStageInstance.crop_cycle_id == CYCLE_ID,
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
            ).first()

        activity_query = db.query(CropActivity).filter(
            CropActivity.tenant_id == TENANT_ID,
            CropActivity.crop_cycle_id == CYCLE_ID,
            CropActivity.stage_instance_id == stage.id,
        )
        activity_count = activity_query.count()
        indexed_notes = [note_for_index(index) for index in range(1, count + 1)]
        existing_indexed_count = activity_query.filter(CropActivity.notes.in_(indexed_notes)).count()
        latest = activity_query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()

        db.flush()
        stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
        pnl_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
        stage_totals = stage_summary.get("totals") or {}
        pnl_totals = pnl_summary.get("totals") or {}
        expected_delta = amount * count

        sample_events = [sample_event(index, amount) for index in range(1, count + 1)]
        baseline = {
            "schema_version": "android_interrupted_multibatch_resume_baseline.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "stage_id": str(stage.id),
            "activity_count": activity_count,
            "existing_indexed_activity_count": existing_indexed_count,
            "stage_summary_actual_expense": str(money(stage_totals.get("actual_expense"))),
            "pnl_total_expenses": str(money(pnl_totals.get("total_expenses"))),
            "latest_activity_id": str(latest.id) if latest else None,
            "latest_activity_created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "expected_count": count,
            "amount_per_activity": str(amount),
            "expected_finance_delta": str(expected_delta),
            "source": SOURCE,
            "note_prefix": NOTE_PREFIX,
            "manifest_path": str(MANIFEST_PATH),
        }
        manifest = {
            "schema_version": "android_interrupted_multibatch_resume_sample_events.v1",
            "tenant_id": TENANT_ID,
            "headers": {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": "11111111-1111-4111-8111-111111111111"},
            "batch_size_recommendation": 10,
            "events": sample_events,
        }

        if dry_run:
            db.rollback()
        else:
            db.commit()
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str))

        result = {
            "schema_version": "android_interrupted_multibatch_resume_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "baseline_path": str(BASELINE_PATH),
            "manifest_path": str(MANIFEST_PATH),
            "before": before,
            "after": {
                "cycle_status": "ACTIVE" if dry_run else cycle.status,
                "stage_status": "ACTIVE" if dry_run else stage.status,
                "stage_id": str(stage.id),
            },
            "reset": {"requested": args.reset_indexed, "deleted_counts": reset_counts},
            "baseline": baseline,
            "android_payload_notes": {
                "random_android_ids_supported": True,
                "exact_id_manifest_optional": True,
                "entity_type": "crop_activity",
                "operation": "CREATE",
                "dependency_ids": [],
                "metadata_source": SOURCE,
                "stable_index_field": "metadata.interrupted_resume_index and notes suffix 01..N",
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())