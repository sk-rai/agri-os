#!/usr/bin/env python3
"""Regression for Android offline sync crop-cycle activity replay.

Uses android-dynamic-test crop-cycle fixture and validates:
- dependency-missing response is Android-readable and retryable;
- ordered sync batch can create crop cycle, start NURSERY by stage_code, and log activity;
- idempotent replay returns accepted;
- same entity_id with changed stale payload routes to VERSION_MISMATCH conflict;
- invalid stage transition routes to WORKFLOW_INVALID conflict;
- Android-safe pending conflict endpoint exposes both conflict types;
- stage-cost summary reflects replayed activity.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.workflow.models import CropCycle
from scripts.seed_android_crop_cycle_test_fixture import (
    CROP_CODE,
    FARMER_ID,
    PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
    main as seed_crop_cycle_fixture_main,
)

client = TestClient(app)
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}
ACTIVITY_COST = "325.50"


def check(condition, label, detail=None):
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str) if isinstance(detail, (dict, list)) else detail)
        raise AssertionError(label)
    print(f"PASS {label}")
    if detail is not None:
        print("     ", detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True, default=str)[:900])


def reset_fixture():
    old_argv = list(sys.argv)
    try:
        sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--reset", "--apply"]
        seed_crop_cycle_fixture_main()
        sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--apply"]
        seed_crop_cycle_fixture_main()
    finally:
        sys.argv = old_argv


def post_sync(events: list[dict]):
    response = client.post("/api/v1/sync/events", json={"events": events}, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def event(event_id: uuid.UUID, entity_type: str, operation: str, payload: dict, *, entity_id: uuid.UUID | None = None, dependency_ids: list[uuid.UUID] | None = None, version: int = 1) -> dict:
    return {
        "event_id": str(event_id),
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "operation": operation,
        "payload": payload,
        "version": version,
        "dependency_ids": [str(item) for item in dependency_ids or []],
        "metadata": {
            "device_id": "android-maestro-offline-sync",
            "client_created_at": date.today().isoformat(),
        },
    }


def main() -> int:
    print("=" * 72)
    print("ANDROID OFFLINE SYNC CROP-CYCLE ACTIVITY FLOW REGRESSION")
    print("=" * 72)

    reset_fixture()

    missing_dependency_id = uuid.uuid4()
    blocked_activity_id = uuid.uuid4()
    missing_response, missing_payload = post_sync([
        event(
            uuid.uuid4(),
            "crop_activity",
            "CREATE",
            {
                "crop_cycle_id": str(uuid.uuid4()),
                "stage_code": "NURSERY",
                "activity_type": "LABOR",
                "activity_date": date.today().isoformat(),
                "cost_amount": ACTIVITY_COST,
            },
            entity_id=blocked_activity_id,
            dependency_ids=[missing_dependency_id],
        )
    ])
    check(missing_response.status_code == 200, "Missing dependency sync batch returns 200", missing_payload)
    check(len(missing_payload.get("failed") or []) == 1, "Missing dependency appears in failed list", missing_payload)
    check((missing_payload["failed"][0] or {}).get("error_code") == "DEPENDENCY_MISSING", "Missing dependency error code stable", missing_payload)

    other_farmer_event_id = uuid.uuid4()
    other_farmer_id = uuid.uuid4()
    mismatch_cycle_event_id = uuid.uuid4()
    mismatch_response, mismatch_payload = post_sync([
        event(
            other_farmer_event_id,
            "farmer",
            "CREATE",
            {
                "mobile_number": "+9198" + str(other_farmer_id.int)[-8:],
                "project_id": str(PROJECT_ID),
                "display_name": "Android Sync Mismatch Farmer",
                "village_name_manual": "Android Sync Test Village",
                "primary_crop_code": CROP_CODE,
            },
            entity_id=other_farmer_id,
        ),
        event(
            mismatch_cycle_event_id,
            "crop_cycle",
            "CREATE",
            {
                "farmer_id": str(other_farmer_id),
                "parcel_id": str(PARCEL_ID),
                "project_id": str(PROJECT_ID),
                "crop_code": CROP_CODE,
                "season_code": SEASON_CODE,
                "planned_sowing_date": (date.today() + timedelta(days=7)).isoformat(),
            },
            entity_id=uuid.uuid4(),
            dependency_ids=[other_farmer_event_id],
        ),
    ])
    check(mismatch_response.status_code == 200, "Mismatched farmer/parcel crop-cycle sync returns 200", mismatch_payload)
    check(str(other_farmer_event_id) in (mismatch_payload.get("accepted") or []), "Mismatch helper farmer is accepted", mismatch_payload)
    mismatch_failures = mismatch_payload.get("failed") or []
    check(any(row.get("event_id") == str(mismatch_cycle_event_id) for row in mismatch_failures), "Mismatched farmer/parcel crop-cycle appears in failed list", mismatch_payload)
    mismatch_failure = next(row for row in mismatch_failures if row.get("event_id") == str(mismatch_cycle_event_id))
    check("parcel does not belong to farmer" in (mismatch_failure.get("message") or ""), "Mismatched farmer/parcel failure message is explicit", mismatch_failure)

    crop_cycle_event_id = uuid.uuid4()
    stage_event_id = uuid.uuid4()
    activity_event_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    planned_sowing = date.today() + timedelta(days=7)

    events = [
        event(
            crop_cycle_event_id,
            "crop_cycle",
            "CREATE",
            {
                "farmer_id": str(FARMER_ID),
                "parcel_id": str(PARCEL_ID),
                "project_id": str(PROJECT_ID),
                "crop_code": CROP_CODE,
                "season_code": SEASON_CODE,
                "planned_sowing_date": planned_sowing.isoformat(),
            },
            entity_id=cycle_id,
        ),
        event(
            stage_event_id,
            "crop_stage",
            "UPDATE",
            {
                "crop_cycle_id": str(cycle_id),
                "stage_code": "NURSERY",
                "action": "START",
                "actual_start_date": date.today().isoformat(),
                "notes": "Offline sync start stage",
            },
            dependency_ids=[crop_cycle_event_id],
        ),
        event(
            activity_event_id,
            "crop_activity",
            "CREATE",
            {
                "crop_cycle_id": str(cycle_id),
                "stage_code": "NURSERY",
                "activity_type": "LABOR",
                "input_name": "Nursery bed preparation labor",
                "quantity": "1",
                "quantity_unit": "DAY",
                "area_applied": "1.25",
                "area_unit": "ACRE",
                "cost_amount": ACTIVITY_COST,
                "activity_date": date.today().isoformat(),
                "gps_lat": 15.4589,
                "gps_lng": 75.0078,
                "notes": "Offline sync activity log",
            },
            entity_id=activity_id,
            dependency_ids=[stage_event_id],
        ),
    ]

    replay_response, replay_payload = post_sync(events)
    check(replay_response.status_code == 200, "Ordered offline sync batch returns 200", replay_payload)
    check(set(replay_payload.get("accepted") or []) == {str(crop_cycle_event_id), str(stage_event_id), str(activity_event_id)}, "Ordered offline sync batch accepts all events", replay_payload)
    check(not replay_payload.get("failed"), "Ordered offline sync batch has no failures", replay_payload)
    check(not replay_payload.get("conflicts"), "Ordered offline sync batch has no conflicts", replay_payload)

    idempotent_response, idempotent_payload = post_sync(events)
    check(idempotent_response.status_code == 200, "Idempotent replay returns 200", idempotent_payload)
    check(set(idempotent_payload.get("accepted") or []) == {str(crop_cycle_event_id), str(stage_event_id), str(activity_event_id)}, "Idempotent replay returns accepted event IDs", idempotent_payload)

    stale_payload_event_id = uuid.uuid4()
    stale_payload_response, stale_payload = post_sync([
        event(
            stale_payload_event_id,
            "crop_activity",
            "CREATE",
            {
                "crop_cycle_id": str(cycle_id),
                "stage_code": "NURSERY",
                "activity_type": "LABOR",
                "input_name": "Nursery bed preparation labor - changed offline copy",
                "quantity": "1",
                "quantity_unit": "DAY",
                "area_applied": "1.25",
                "area_unit": "ACRE",
                "cost_amount": "999.00",
                "activity_date": date.today().isoformat(),
                "notes": "Changed stale offline payload should conflict",
            },
            entity_id=activity_id,
            dependency_ids=[stage_event_id],
            version=1,
        )
    ])
    check(stale_payload_response.status_code == 200, "Changed stale activity replay returns 200", stale_payload)
    check(len(stale_payload.get("conflicts") or []) == 1, "Changed stale activity replay appears in conflicts list", stale_payload)
    stale_conflict = stale_payload["conflicts"][0]
    check(stale_conflict.get("event_id") == str(stale_payload_event_id), "Changed stale conflict event ID is stable", stale_conflict)
    check(stale_conflict.get("conflict_type") == "VERSION_MISMATCH", "Changed stale conflict type is VERSION_MISMATCH", stale_conflict)
    check(stale_conflict.get("resolution_strategy") == "MANUAL_REVIEW", "Changed stale conflict resolution strategy is MANUAL_REVIEW", stale_conflict)
    check(not stale_payload.get("failed"), "Changed stale conflict has no failed events", stale_payload)

    conflict_event_id = uuid.uuid4()
    conflict_response, conflict_payload = post_sync([
        event(
            conflict_event_id,
            "crop_stage",
            "UPDATE",
            {
                "crop_cycle_id": str(cycle_id),
                "stage_code": "TRANSPLANTING",
                "action": "COMPLETE",
                "actual_end_date": date.today().isoformat(),
                "notes": "Invalid offline transition sample",
            },
            dependency_ids=[crop_cycle_event_id],
        )
    ])
    check(conflict_response.status_code == 200, "Invalid stage transition sync batch returns 200", conflict_payload)
    check(len(conflict_payload.get("conflicts") or []) == 1, "Invalid stage transition appears in conflicts list", conflict_payload)
    conflict = conflict_payload["conflicts"][0]
    check(conflict.get("event_id") == str(conflict_event_id), "Conflict event ID is stable", conflict)
    check(conflict.get("conflict_type") == "WORKFLOW_INVALID", "Conflict type is WORKFLOW_INVALID", conflict)
    check(conflict.get("resolution_strategy") == "SERVER_AUTHORITY", "Conflict resolution strategy is SERVER_AUTHORITY", conflict)
    check(not conflict_payload.get("failed"), "Invalid transition conflict has no failed events", conflict_payload)

    pending_response = client.get("/api/v1/sync/conflicts/pending?limit=100", headers=HEADERS)
    check(pending_response.status_code == 200, "Android pending sync conflicts endpoint returns 200", pending_response.text[:900])
    pending_payload = pending_response.json()
    check(pending_payload.get("schema_version") == "android_pending_sync_conflicts.v1", "Android pending conflicts schema version stable", pending_payload)
    pending_by_event_id = {row.get("event_id"): row for row in pending_payload.get("conflicts") or []}
    check(str(stale_payload_event_id) in pending_by_event_id, "Pending conflicts include stale payload VERSION_MISMATCH", pending_payload)
    check(str(conflict_event_id) in pending_by_event_id, "Pending conflicts include workflow invalid conflict", pending_payload)
    pending_stale = pending_by_event_id[str(stale_payload_event_id)]
    pending_workflow = pending_by_event_id[str(conflict_event_id)]
    check(pending_stale.get("android_action") == "SHOW_MANUAL_REVIEW_CONFLICT", "Stale payload pending conflict has Android manual review action", pending_stale)
    check(pending_workflow.get("android_action") == "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE", "Workflow pending conflict has Android server-authority action", pending_workflow)
    check("payload_keys" in (pending_stale.get("client_payload_summary") or {}), "Pending stale conflict exposes safe client payload summary", pending_stale)
    check("detail" in (pending_workflow.get("server_payload_summary") or {}), "Pending workflow conflict exposes safe server detail", pending_workflow)

    cycle_response = client.get(f"/api/v1/crop-cycles/{cycle_id}", headers=HEADERS)
    check(cycle_response.status_code == 200, "Synced crop cycle can be fetched", cycle_response.text[:900])
    cycle = cycle_response.json()
    check(cycle.get("status") == "ACTIVE", "Synced crop cycle is ACTIVE after stage START", cycle)
    check(cycle.get("farmer_id") == str(FARMER_ID), "Synced crop cycle response preserves farmer_id", cycle)
    check(cycle.get("parcel_id") == str(PARCEL_ID), "Synced crop cycle response preserves parcel_id", cycle)
    db = SessionLocal()
    try:
        persisted_cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id, CropCycle.tenant_id == TENANT_ID).first()
        check(bool(persisted_cycle), "Synced crop cycle persists operational row")
        check(str(persisted_cycle.project_id) == str(PROJECT_ID), "Synced crop cycle persists project_id", {"project_id": persisted_cycle.project_id})
    finally:
        db.close()
    nursery = next((stage for stage in cycle.get("stages") or [] if stage.get("code") == "NURSERY"), None)
    check(nursery and nursery.get("status") == "ACTIVE", "Synced NURSERY stage is ACTIVE", nursery)
    transplanting = next((stage for stage in cycle.get("stages") or [] if stage.get("code") == "TRANSPLANTING"), None)
    check(transplanting and transplanting.get("status") == "PENDING", "Invalid conflict did not mutate pending TRANSPLANTING stage", transplanting)

    activity_response = client.get(f"/api/v1/crop-cycles/{cycle_id}/activities", headers=HEADERS)
    check(activity_response.status_code == 200, "Synced activity list returns 200", activity_response.text[:900])
    activities = activity_response.json()
    synced_activity = next((row for row in activities if row.get("id") == str(activity_id)), None)
    check(bool(synced_activity), "Synced activity appears in activity list", activities)
    check(synced_activity.get("stage_code") == "NURSERY", "Synced activity is stage-linked", synced_activity)
    check(synced_activity.get("cost_amount") == ACTIVITY_COST, "Synced activity cost is preserved", synced_activity)
    check(synced_activity.get("input_name") == "Nursery bed preparation labor", "Changed stale conflict did not mutate activity payload", synced_activity)

    summary_response = client.get(f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary", headers=HEADERS)
    check(summary_response.status_code == 200, "Synced stage-cost summary returns 200", summary_response.text[:900])
    summary = summary_response.json()
    check((summary.get("totals") or {}).get("activity_count") == 1, "Synced summary activity_count updated", summary.get("totals"))
    check((summary.get("totals") or {}).get("actual_expense") == ACTIVITY_COST, "Synced summary actual_expense updated", summary.get("totals"))

    print("=" * 72)
    print("Android offline sync crop-cycle activity flow validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())