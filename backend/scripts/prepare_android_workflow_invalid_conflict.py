"""Prepare Android WORKFLOW_INVALID conflict fixture.

The fixture targets the existing Android dynamic crop cycle and ensures the
NURSERY stage is ACTIVE. Android then queues a crop_stage UPDATE with
action=START. START from ACTIVE is invalid, so backend conflict detection
returns:

    conflicts[].conflict_type = WORKFLOW_INVALID

and no failed[] row.
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
from app.modules.sync.models import SyncConflict, SyncProcessedEvent
from app.modules.workflow.models import CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")

ANDROID_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000121")
CONFLICT_ENTITY_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000122")
ACTOR_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def delete_fixture_rows(db, dry_run: bool) -> dict:
    counts: dict[str, int] = {}
    conflicts = (
        db.query(SyncConflict)
        .filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id == ANDROID_EVENT_ID,
        )
        .all()
    )
    counts["sync_conflicts"] = len(conflicts)
    if not dry_run:
        for row in conflicts:
            db.delete(row)

    processed = (
        db.query(SyncProcessedEvent)
        .filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == ANDROID_EVENT_ID,
        )
        .all()
    )
    counts["sync_processed_events"] = len(processed)
    if not dry_run:
        for row in processed:
            db.delete(row)
    return counts


def prepare_stage_state(db, dry_run: bool) -> dict:
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID)
        .first()
    )
    if not cycle:
        raise RuntimeError(f"crop cycle {CYCLE_ID} not found; run android crop-cycle fixture first")

    stage = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == CYCLE_ID,
            CropStageInstance.tenant_id == TENANT_ID,
            CropStageInstance.stage_code == "NURSERY",
        )
        .first()
    )
    if not stage:
        raise RuntimeError(f"NURSERY stage not found for crop cycle {CYCLE_ID}")

    before = {
        "cycle_status": cycle.status,
        "stage_id": str(stage.id),
        "stage_code": stage.stage_code,
        "stage_status": stage.status,
        "actual_start_date": stage.actual_start_date,
    }

    if not dry_run:
        cycle.status = "ACTIVE"
        cycle.actual_sowing_date = cycle.actual_sowing_date or date(2026, 8, 2)
        cycle.updated_at = datetime.now(timezone.utc)
        stage.status = "ACTIVE"
        stage.actual_start_date = stage.actual_start_date or date(2026, 8, 2)
        stage.actual_end_date = None
        stage.updated_at = datetime.now(timezone.utc)

    after = {
        "cycle_status": "ACTIVE" if dry_run else cycle.status,
        "stage_id": str(stage.id),
        "stage_code": stage.stage_code,
        "stage_status": "ACTIVE" if dry_run else stage.status,
        "actual_start_date": stage.actual_start_date or date(2026, 8, 2),
    }
    return {"before": before, "after": after}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Delete prior deterministic conflict rows.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        result = {
            "schema_version": "android_workflow_invalid_conflict_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "tenant_id": TENANT_ID,
            "actor_id_header": {"X-Actor-ID": str(ACTOR_ID)},
            "fixture": {
                "entity_type": "crop_stage",
                "operation": "UPDATE",
                "android_event_id": str(ANDROID_EVENT_ID),
                "sync_entity_id": str(CONFLICT_ENTITY_ID),
                "cycle_id": str(CYCLE_ID),
                "farmer_id": str(FARMER_ID),
                "parcel_id": str(PARCEL_ID),
                "project_id": str(PROJECT_ID),
                "stage_code": "NURSERY",
                "invalid_action": "START",
            },
            "reset": {
                "requested": args.reset,
                "deleted_counts": {},
            },
            "stage_state": None,
            "android_payload_shape": {
                "event_id": str(ANDROID_EVENT_ID),
                "entity_type": "crop_stage",
                "entity_id": str(CONFLICT_ENTITY_ID),
                "operation": "UPDATE",
                "version": 1,
                "dependency_ids": [],
                "payload": {
                    "crop_cycle_id": str(CYCLE_ID),
                    "stage_code": "NURSERY",
                    "action": "START",
                    "actual_start_date": "2026-08-02",
                },
                "metadata": {"source": "android_maestro_workflow_invalid_test"},
            },
            "expected_sync_response": {
                "accepted": [],
                "failed": [],
                "conflicts": [
                    {
                        "event_id": str(ANDROID_EVENT_ID),
                        "conflict_type": "WORKFLOW_INVALID",
                        "resolution_strategy": "SERVER_AUTHORITY",
                        "detail": "Invalid stage transition: cannot START from ACTIVE",
                    }
                ],
            },
            "restore_command": (
                "No separate restore is required. Re-run with --reset --apply before each test."
            ),
        }

        if args.reset:
            result["reset"]["deleted_counts"] = delete_fixture_rows(db, dry_run)

        result["stage_state"] = prepare_stage_state(db, dry_run)

        if dry_run:
            db.rollback()
        else:
            db.commit()

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
