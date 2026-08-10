"""Prepare Android VERSION_MISMATCH conflict fixture.

This creates a committed sync/audit server version for one fixed crop_activity
entity id. Android can then queue a different offline payload for the same
entity id and version=1. On Sync Now, backend should return:

    conflicts[].conflict_type = VERSION_MISMATCH

and no failed[] row.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.sync.models import SyncConflict, SyncProcessedEvent
from app.modules.sync.service import append_audit
from android_dynamic_sync_baseline import ensure_android_baseline


TENANT_ID = "android-dynamic-test"
ACTOR_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SERVER_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000110")
ANDROID_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000111")
ACTIVITY_ENTITY_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000112")

CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")



SERVER_PAYLOAD = {
    "crop_cycle_id": str(CYCLE_ID),
    "stage_code": "NURSERY",
    "activity_date": "2026-08-02",
    "activity_type": "IRRIGATION",
    "description": "Server committed test activity payload",
    "cost_amount": 125.0,
    "currency": "INR",
}

ANDROID_CONFLICT_PAYLOAD = {
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


def ensure_committed_server_payload(db, dry_run: bool) -> str:
    existing = (
        db.query(SyncProcessedEvent)
        .filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == SERVER_EVENT_ID,
        )
        .first()
    )
    if existing and existing.status == "COMMITTED":
        return "EXISTS"
    if dry_run:
        return "WOULD_CREATE"

    if not existing:
        existing = SyncProcessedEvent(
            event_id=SERVER_EVENT_ID,
            tenant_id=TENANT_ID,
        )
        db.add(existing)

    existing.actor_id = ACTOR_ID
    existing.entity_type = "crop_activity"
    existing.entity_id = ACTIVITY_ENTITY_ID
    existing.operation = "CREATE"
    existing.server_version = 1
    existing.status = "COMMITTED"
    existing.processed_at = datetime.now(timezone.utc)

    append_audit(
        db=db,
        tenant_id=TENANT_ID,
        actor_id=str(ACTOR_ID),
        correlation_id=str(SERVER_EVENT_ID),
        entity_type="crop_activity",
        entity_id=str(ACTIVITY_ENTITY_ID),
        action="SYNC_COMMIT",
        payload=SERVER_PAYLOAD,
        metadata={
            "source": "ANDROID_VERSION_MISMATCH_FIXTURE",
            "sync_event_id": str(SERVER_EVENT_ID),
            "fixture_role": "server_committed_payload",
        },
    )
    return "CREATED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Delete fixture processed/conflict rows before prepare.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        result = {
            "schema_version": "android_version_mismatch_conflict_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "tenant_id": TENANT_ID,
            "actor_id_header": {"X-Actor-ID": str(ACTOR_ID)},
            "fixture": {
                "entity_type": "crop_activity",
                "android_event_id": str(ANDROID_EVENT_ID),
                "activity_entity_id": str(ACTIVITY_ENTITY_ID),
                "server_event_id": str(SERVER_EVENT_ID),
                "server_version": 1,
                "cycle_id": str(CYCLE_ID),
                "farmer_id": str(FARMER_ID),
                "parcel_id": str(PARCEL_ID),
                "project_id": str(PROJECT_ID),
            },
            "reset": {
                "requested": args.reset,
                "deleted_counts": {},
            },
            "baseline": None,
            "server_payload_status": None,
            "android_payload_shape": {
                "event_id": str(ANDROID_EVENT_ID),
                "entity_type": "crop_activity",
                "entity_id": str(ACTIVITY_ENTITY_ID),
                "operation": "CREATE",
                "version": 1,
                "dependency_ids": [],
                "payload": ANDROID_CONFLICT_PAYLOAD,
                "metadata": {"source": "android_maestro_version_mismatch_test"},
            },
            "expected_sync_response": {
                "accepted": [],
                "failed": [],
                "conflicts": [
                    {
                        "event_id": str(ANDROID_EVENT_ID),
                        "conflict_type": "VERSION_MISMATCH",
                        "resolution_strategy": "MANUAL_REVIEW",
                    }
                ],
            },
        }

        if args.reset:
            result["reset"]["deleted_counts"] = delete_fixture_rows(db, dry_run)

        result["baseline"] = ensure_android_baseline(db, dry_run)
        result["server_payload_status"] = ensure_committed_server_payload(db, dry_run)

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
