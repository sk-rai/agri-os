"""Prepare Android multi-conflict pending drawer fixture.

This resets deterministic VERSION_MISMATCH and WORKFLOW_INVALID conflict event
rows, ensures their backend preconditions, and writes an Android-readable
baseline/contract file.
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
from app.modules.sync.service import append_audit
from app.modules.workflow.models import CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
ACTOR_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")

VERSION_SERVER_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000110")
VERSION_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000111")
VERSION_ACTIVITY_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000112")

WORKFLOW_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000121")
WORKFLOW_ENTITY_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000122")

BASELINE_PATH = Path("/tmp/android_multi_conflict_pending_drawer_baseline.json")

VERSION_SERVER_PAYLOAD = {
    "crop_cycle_id": str(CYCLE_ID),
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "IRRIGATION",
    "description": "Server committed test activity payload",
    "cost_amount": 125.0,
    "currency": "INR",
}

VERSION_ANDROID_PAYLOAD = {
    "crop_cycle_id": str(CYCLE_ID),
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "FERTILIZER",
    "input_code": "DAP_18_46_0",
    "description": "Android offline changed activity payload",
    "quantity": 1,
    "quantity_unit": "KG",
    "cost_amount": 325.5,
    "currency": "INR",
}

WORKFLOW_PAYLOAD = {
    "crop_cycle_id": str(CYCLE_ID),
    "stage_code": "NURSERY",
    "action": "START",
    "actual_start_date": "2026-08-02",
}


def delete_event_rows(db, event_ids: list[uuid.UUID], dry_run: bool) -> dict:
    counts = {"sync_conflicts": 0, "sync_processed_events": 0}
    conflicts = db.query(SyncConflict).filter(
        SyncConflict.tenant_id == TENANT_ID,
        SyncConflict.event_id.in_(event_ids),
    ).all()
    counts["sync_conflicts"] = len(conflicts)
    if not dry_run:
        for row in conflicts:
            db.delete(row)

    processed = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.tenant_id == TENANT_ID,
        SyncProcessedEvent.event_id.in_(event_ids),
    ).all()
    counts["sync_processed_events"] = len(processed)
    if not dry_run:
        for row in processed:
            db.delete(row)
    return counts


def ensure_committed_server_payload(db, dry_run: bool) -> str:
    existing = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.tenant_id == TENANT_ID,
        SyncProcessedEvent.event_id == VERSION_SERVER_EVENT_ID,
    ).first()
    if existing and existing.status == "COMMITTED":
        return "EXISTS"
    if dry_run:
        return "WOULD_CREATE"

    if not existing:
        existing = SyncProcessedEvent(event_id=VERSION_SERVER_EVENT_ID, tenant_id=TENANT_ID)
        db.add(existing)

    existing.actor_id = ACTOR_ID
    existing.entity_type = "crop_activity"
    existing.entity_id = VERSION_ACTIVITY_ID
    existing.operation = "CREATE"
    existing.server_version = 1
    existing.status = "COMMITTED"
    existing.processed_at = datetime.now(timezone.utc)

    append_audit(
        db=db,
        tenant_id=TENANT_ID,
        actor_id=str(ACTOR_ID),
        correlation_id=str(VERSION_SERVER_EVENT_ID),
        entity_type="crop_activity",
        entity_id=str(VERSION_ACTIVITY_ID),
        action="SYNC_COMMIT",
        payload=VERSION_SERVER_PAYLOAD,
        metadata={
            "source": "ANDROID_MULTI_CONFLICT_DRAWER_FIXTURE",
            "sync_event_id": str(VERSION_SERVER_EVENT_ID),
            "fixture_role": "server_committed_payload_for_version_mismatch",
        },
    )
    return "CREATED"


def prepare_workflow_state(db, dry_run: bool) -> dict:
    cycle = db.query(CropCycle).filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID).first()
    if not cycle:
        raise RuntimeError(f"crop cycle {CYCLE_ID} not found; run Android dynamic crop-cycle fixture first")

    stage = db.query(CropStageInstance).filter(
        CropStageInstance.crop_cycle_id == CYCLE_ID,
        CropStageInstance.tenant_id == TENANT_ID,
        CropStageInstance.stage_code == "NURSERY",
    ).first()
    if not stage:
        raise RuntimeError(f"NURSERY stage not found for crop cycle {CYCLE_ID}")

    before = {
        "cycle_status": cycle.status,
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
    after = {
        "cycle_status": "ACTIVE" if dry_run else cycle.status,
        "stage_id": str(stage.id),
        "stage_status": "ACTIVE" if dry_run else stage.status,
        "stage_actual_start_date": stage.actual_start_date or date(2026, 8, 2),
    }
    return {"before": before, "after": after}


def android_version_event() -> dict:
    return {
        "event_id": str(VERSION_EVENT_ID),
        "entity_type": "crop_activity",
        "entity_id": str(VERSION_ACTIVITY_ID),
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": VERSION_ANDROID_PAYLOAD,
        "metadata": {"source": "android_maestro_multi_conflict_pending_drawer_test"},
    }


def android_workflow_event() -> dict:
    return {
        "event_id": str(WORKFLOW_EVENT_ID),
        "entity_type": "crop_stage",
        "entity_id": str(WORKFLOW_ENTITY_ID),
        "operation": "UPDATE",
        "version": 1,
        "dependency_ids": [],
        "payload": WORKFLOW_PAYLOAD,
        "metadata": {"source": "android_maestro_multi_conflict_pending_drawer_test"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Delete deterministic Android conflict rows first.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        result = {
            "schema_version": "android_multi_conflict_pending_drawer_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "actor_id_header": {"X-Actor-ID": str(ACTOR_ID)},
            "baseline_path": str(BASELINE_PATH),
            "reset": {"requested": args.reset, "deleted_counts": {}},
            "server_payload_status": None,
            "workflow_state": None,
            "events": {
                "version_mismatch": android_version_event(),
                "workflow_invalid": android_workflow_event(),
            },
            "expected_response": {
                "accepted": [],
                "failed": [],
                "conflicts": [
                    {
                        "event_id": str(VERSION_EVENT_ID),
                        "conflict_type": "VERSION_MISMATCH",
                        "resolution_strategy": "MANUAL_REVIEW",
                    },
                    {
                        "event_id": str(WORKFLOW_EVENT_ID),
                        "conflict_type": "WORKFLOW_INVALID",
                        "resolution_strategy": "SERVER_AUTHORITY",
                    },
                ],
                "total_processed": 2,
            },
            "pending_endpoint_ordering": "created_at desc; one visible row per unresolved event_id",
            "android_actions": {
                "VERSION_MISMATCH": "SHOW_MANUAL_REVIEW_CONFLICT",
                "WORKFLOW_INVALID": "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE",
            },
        }

        if args.reset:
            result["reset"]["deleted_counts"] = delete_event_rows(db, [VERSION_EVENT_ID, WORKFLOW_EVENT_ID], dry_run)

        result["server_payload_status"] = ensure_committed_server_payload(db, dry_run)
        result["workflow_state"] = prepare_workflow_state(db, dry_run)

        if dry_run:
            db.rollback()
        else:
            db.commit()
            BASELINE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())