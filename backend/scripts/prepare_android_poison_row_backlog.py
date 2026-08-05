"""Prepare baseline for Android large backlog with one poison conflict row QA.

Flow 29 uses a 25-row offline backlog under the existing active Android dynamic
Rice/NURSERY cycle:

- rows 1..9: valid crop_activity CREATE;
- row 10: WORKFLOW_INVALID crop_stage START against already ACTIVE NURSERY;
- rows 11..25: valid crop_activity CREATE.

The prep records baseline activity/finance state and writes a canonical sample
manifest that Android may mirror.
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
POISON_INDEX = 10
VALID_COUNT = 24
DEFAULT_AMOUNT = Decimal("20.00")
SOURCE = "android_maestro_poison_row_backlog_test"
NOTE_PREFIX = "Poison backlog valid activity"
BASELINE_PATH = Path("/tmp/android_poison_row_backlog_baseline.json")
MANIFEST_PATH = Path("/tmp/android_poison_row_backlog_sample_events.json")
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


def event_id_for_index(index: int) -> uuid.UUID:
    if index == POISON_INDEX:
        return uuid.uuid5(uuid.NAMESPACE_URL, "farmint-flow29-poison-stage-event")
    return uuid.uuid5(uuid.NAMESPACE_URL, f"farmint-flow29-activity-event-{index}")


def entity_id_for_index(index: int) -> uuid.UUID:
    if index == POISON_INDEX:
        return uuid.uuid5(uuid.NAMESPACE_URL, "farmint-flow29-poison-stage-entity")
    return uuid.uuid5(uuid.NAMESPACE_URL, f"farmint-flow29-activity-entity-{index}")


def valid_indices(count: int) -> list[int]:
    return [index for index in range(1, count + 1) if index != POISON_INDEX]


def delete_prior_indexed_rows(db, stage_id: uuid.UUID, count: int, dry_run: bool) -> dict:
    event_ids = [event_id_for_index(index) for index in range(1, count + 1)]
    activity_entity_ids = [entity_id_for_index(index) for index in valid_indices(count)]
    notes = [note_for_index(index) for index in valid_indices(count)]

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
        CropActivity.id.in_(activity_entity_ids),
    ).all()
    extra_note_activities = db.query(CropActivity).filter(
        CropActivity.tenant_id == TENANT_ID,
        CropActivity.crop_cycle_id == CYCLE_ID,
        CropActivity.stage_instance_id == stage_id,
        CropActivity.notes.in_(notes),
        ~CropActivity.id.in_([row.id for row in activities]),
    ).all()
    activities = activities + extra_note_activities

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


def valid_activity_event(index: int, amount: Decimal, count: int) -> dict:
    return {
        "event_id": str(event_id_for_index(index)),
        "entity_type": "crop_activity",
        "entity_id": str(entity_id_for_index(index)),
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "activity_date": date(2026, 8, 2).isoformat(),
            "activity_type": "LABOR",
            "input_name": "Poison backlog labor log",
            "quantity": 1,
            "quantity_unit": "HOURS",
            "cost_amount": float(amount),
            "currency": "INR",
            "notes": note_for_index(index),
        },
        "metadata": {
            "source": SOURCE,
            "poison_backlog_index": index,
            "poison_backlog_count": count,
            "poison_backlog_role": "VALID_ACTIVITY",
        },
    }


def poison_stage_event(count: int) -> dict:
    return {
        "event_id": str(event_id_for_index(POISON_INDEX)),
        "entity_type": "crop_stage",
        "entity_id": str(entity_id_for_index(POISON_INDEX)),
        "operation": "UPDATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "action": "START",
            "actual_start_date": date(2026, 8, 2).isoformat(),
        },
        "metadata": {
            "source": SOURCE,
            "poison_backlog_index": POISON_INDEX,
            "poison_backlog_count": count,
            "poison_backlog_role": "WORKFLOW_INVALID_STAGE",
        },
    }


def sample_event(index: int, amount: Decimal, count: int) -> dict:
    if index == POISON_INDEX:
        return poison_stage_event(count)
    return valid_activity_event(index, amount, count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--amount", default=str(DEFAULT_AMOUNT))
    parser.add_argument("--reset-indexed", action="store_true", help="Delete prior deterministic Flow 29 rows before baselining.")
    args = parser.parse_args()
    dry_run = not args.apply
    count = int(args.count)
    amount = money(args.amount)
    if count != DEFAULT_COUNT:
        raise ValueError("Flow 29 currently expects count=25 so row 10 is the poison row")

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
        notes = [note_for_index(index) for index in valid_indices(count)]
        existing_indexed_count = activity_query.filter(CropActivity.notes.in_(notes)).count()
        latest = activity_query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()

        stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
        pnl_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
        stage_totals = stage_summary.get("totals") or {}
        pnl_totals = pnl_summary.get("totals") or {}
        expected_delta = amount * VALID_COUNT

        sample_events = [sample_event(index, amount, count) for index in range(1, count + 1)]
        baseline = {
            "schema_version": "android_poison_row_backlog_baseline.v1",
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
            "valid_activity_count": VALID_COUNT,
            "poison_index": POISON_INDEX,
            "amount_per_activity": str(amount),
            "expected_finance_delta": str(expected_delta),
            "source": SOURCE,
            "note_prefix": NOTE_PREFIX,
            "manifest_path": str(MANIFEST_PATH),
            "expected_conflict": {
                "event_id": str(event_id_for_index(POISON_INDEX)),
                "entity_id": str(entity_id_for_index(POISON_INDEX)),
                "entity_type": "crop_stage",
                "conflict_type": "WORKFLOW_INVALID",
                "resolution_strategy": "SERVER_AUTHORITY",
                "android_action": "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE",
            },
        }
        manifest = {
            "schema_version": "android_poison_row_backlog_sample_events.v1",
            "tenant_id": TENANT_ID,
            "headers": {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": "11111111-1111-4111-8111-111111111111"},
            "batch_size_recommendation": 10,
            "poison_index": POISON_INDEX,
            "events": sample_events,
        }

        if dry_run:
            db.rollback()
        else:
            db.commit()
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str))

        print(json.dumps({
            "schema_version": "android_poison_row_backlog_prepare.v1",
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
                "valid_activity_dependency_ids": [],
                "poison_stage_dependency_ids": [],
                "stable_index_field": "metadata.poison_backlog_index and notes suffix 01..N",
            },
        }, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
