#!/usr/bin/env python3
"""Regression for Android crop-cycle stage + activity logging flow.

Uses the deterministic android-dynamic-test crop-cycle fixture:
- reset/reseed farmer + parcel;
- create a Rice/Kharif crop cycle;
- start the first stage;
- log a stage-linked activity with cost;
- verify activity list, stage-cost summary, and P&L summary update.
"""

from __future__ import annotations

import atexit
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.sync.models import AuditChainEntry, SyncProcessedEvent
from app.modules.workflow.models import CropActivity, CropCycle
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
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
HEADERS = {}
ACTIVITY_COST = Decimal("325.50")
UPDATED_ACTIVITY_COST = Decimal("475.75")


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


def get_json(path: str, params=None):
    response = client.get(path, params=params or {}, headers=HEADERS)
    return response, response.json()


def install_test_admin(tenant_id: str) -> None:
    global HEADERS
    db = SessionLocal()
    try:
        user, HEADERS = create_test_admin(
            db,
            tenant_id=tenant_id,
            role="ENTERPRISE_ADMIN",
        )
        user_id = user.id
    finally:
        db.close()

    def cleanup_test_admin() -> None:
        cleanup_db = SessionLocal()
        try:
            delete_test_admin(cleanup_db, user_id)
        finally:
            cleanup_db.close()

    atexit.register(cleanup_test_admin)


def main() -> int:
    print("=" * 72)
    print("ANDROID CROP-CYCLE ACTIVITY LOGGING FLOW REGRESSION")
    print("=" * 72)

    reset_fixture()
    install_test_admin(TENANT_ID)

    create_payload = {
        "farmer_id": str(FARMER_ID),
        "parcel_id": str(PARCEL_ID),
        "project_id": str(PROJECT_ID),
        "crop_code": CROP_CODE,
        "season_code": SEASON_CODE,
        "planned_sowing_date": (date.today() + timedelta(days=7)).isoformat(),
        "seed_source": "OWN_SAVED",
    }
    create_response = client.post("/api/v1/crop-cycles", json=create_payload, headers=HEADERS)
    check(create_response.status_code == 201, "Crop-cycle create returns 201", create_response.text[:1000])
    cycle = create_response.json()
    cycle_id = cycle.get("id")
    stages = cycle.get("stages") or []
    check(bool(cycle_id), "Crop-cycle id present", cycle)
    check(bool(stages), "Crop-cycle stages present", {"stage_count": len(stages)})

    first_stage = stages[0]
    stage_id = first_stage["id"]
    stage_code = first_stage["code"]
    start_response = client.patch(
        f"/api/v1/crop-cycles/{cycle_id}/stages/{stage_id}",
        json={"action": "START", "gps_lat": 15.4589, "gps_lng": 75.0078, "notes": "Android regression start first stage"},
        headers=HEADERS,
    )
    check(start_response.status_code == 200, "First stage START transition returns 200", start_response.text[:1000])
    start_payload = start_response.json()
    check(start_payload.get("new_status") == "ACTIVE", "First stage is ACTIVE", start_payload)
    check(start_payload.get("cycle_status") == "ACTIVE", "Crop cycle becomes ACTIVE after first stage START", start_payload)

    activity_payload = {
        "activity_id": str(uuid.uuid4()),
        "activity_type": "LABOR",
        "input_name": "Nursery bed preparation labor",
        "quantity": "1",
        "quantity_unit": "DAY",
        "area_applied": "1.25",
        "area_unit": "ACRE",
        "cost_amount": str(ACTIVITY_COST),
        "activity_date": date.today().isoformat(),
        "gps_lat": 15.4589,
        "gps_lng": 75.0078,
        "notes": "Android regression activity log",
    }
    activity_response = client.post(f"/api/v1/crop-cycles/{cycle_id}/activities", json=activity_payload, headers=HEADERS)
    check(activity_response.status_code == 201, "Activity log accepts Android payload", activity_response.text[:1000])
    activity = activity_response.json()
    activity_id = activity.get("activity_id")
    check(bool(activity_id), "Activity response exposes activity_id", activity)
    check(activity_id == activity_payload["activity_id"], "Direct activity preserves client activity_id", activity)
    check(activity.get("stage_code") == stage_code, "Activity is linked to active stage", activity)
    check(activity.get("cycle_total_input_cost") == str(ACTIVITY_COST), "Cycle total input cost updated", activity)

    fallback_event_id = str(uuid.uuid4())
    fallback_event = {
        "event_id": fallback_event_id,
        "entity_type": "CROP_ACTIVITY",
        "entity_id": activity_id,
        "operation": "CREATE",
        "payload": {
            **activity_payload,
            "crop_cycle_id": cycle_id,
            "stage_code": stage_code,
        },
        "version": 1,
        "dependency_ids": [],
        "metadata": {"source": "android_offline_activity_log"},
    }
    fallback_response = client.post(
        "/api/v1/sync/events",
        json={"events": [fallback_event]},
        headers=HEADERS,
    )
    check(fallback_response.status_code == 200, "Lost-response fallback sync returns 200")
    check(
        fallback_event_id in (fallback_response.json().get("accepted") or []),
        "Lost-response fallback event is accepted",
    )

    db = SessionLocal()
    try:
        create_rows = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).all()
        create_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        committed_create = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == uuid.UUID(fallback_event_id),
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.status == "COMMITTED",
        ).one_or_none()
        check(len(create_rows) == 1, "Fallback CREATE retains one activity row")
        check(create_rows[0].id == uuid.UUID(activity_id), "Fallback CREATE retains the direct activity identity")
        check(create_rows[0].cost_amount == ACTIVITY_COST, "Fallback CREATE retains one activity cost")
        check(create_cycle.total_input_cost == ACTIVITY_COST, "Fallback CREATE retains one cycle economic effect")
        check(bool(committed_create), "Fallback CREATE is recorded COMMITTED")
    finally:
        db.close()

    replay_response = client.post(
        "/api/v1/sync/events",
        json={"events": [fallback_event]},
        headers=HEADERS,
    )
    check(replay_response.status_code == 200, "Fallback event replay returns 200")
    check(
        fallback_event_id in (replay_response.json().get("accepted") or []),
        "Fallback replay remains idempotently accepted",
    )

    db = SessionLocal()
    try:
        replay_rows = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).all()
        replay_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        create_sync_audits = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == TENANT_ID,
            AuditChainEntry.entity_id == uuid.UUID(activity_id),
            AuditChainEntry.action == "SYNC_COMMIT",
        ).all()
        check(len(replay_rows) == 1, "Fallback event replay does not add an activity")
        check(replay_cycle.total_input_cost == ACTIVITY_COST, "Fallback event replay does not add an economic effect")
        check(len(create_sync_audits) == 1, "Fallback replay does not add another sync-event audit")
    finally:
        db.close()

    update_event_id = str(uuid.uuid4())
    update_payload = {
        **activity_payload,
        "crop_cycle_id": cycle_id,
        "stage_code": stage_code,
        "input_name": "Nursery bed preparation labor - corrected",
        "quantity": "2",
        "cost_amount": str(UPDATED_ACTIVITY_COST),
        "notes": "Applied offline activity correction",
    }
    update_event = {
        "event_id": update_event_id,
        "entity_type": "CROP_ACTIVITY",
        "entity_id": activity_id,
        "operation": "UPDATE",
        "payload": update_payload,
        "version": 2,
        "dependency_ids": [],
        "metadata": {"source": "android_offline_activity_update"},
    }
    update_response = client.post(
        "/api/v1/sync/events",
        json={"events": [update_event]},
        headers=HEADERS,
    )
    check(update_response.status_code == 200, "Higher-version activity UPDATE returns 200")
    update_result = update_response.json()
    check(update_event_id in (update_result.get("accepted") or []), "Higher-version activity UPDATE is accepted")
    check(not update_result.get("failed"), "Higher-version activity UPDATE has no failure")
    check(not update_result.get("conflicts"), "Higher-version activity UPDATE has no conflict")

    db = SessionLocal()
    try:
        updated_rows = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).all()
        updated_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        committed_update = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == uuid.UUID(update_event_id),
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.status == "COMMITTED",
        ).one_or_none()
        check(len(updated_rows) == 1, "UPDATE preserves one activity identity")
        check(updated_rows[0].input_name == update_payload["input_name"], "UPDATE applies input_name")
        check(updated_rows[0].quantity == Decimal("2"), "UPDATE applies quantity")
        check(updated_rows[0].cost_amount == UPDATED_ACTIVITY_COST, "UPDATE applies cost")
        check(updated_rows[0].notes == update_payload["notes"], "UPDATE applies notes")
        check(updated_cycle.total_input_cost == UPDATED_ACTIVITY_COST, "UPDATE recalculates cycle economic state")
        check(bool(committed_update), "UPDATE is COMMITTED with its requested mutation applied")
    finally:
        db.close()

    update_replay_response = client.post(
        "/api/v1/sync/events",
        json={"events": [update_event]},
        headers=HEADERS,
    )
    check(update_replay_response.status_code == 200, "Exact UPDATE replay returns 200")
    check(update_event_id in (update_replay_response.json().get("accepted") or []), "Exact UPDATE replay remains accepted")

    db = SessionLocal()
    try:
        replayed_update_rows = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).all()
        replayed_update_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        update_sync_audits = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == TENANT_ID,
            AuditChainEntry.entity_id == uuid.UUID(activity_id),
            AuditChainEntry.action == "SYNC_COMMIT",
        ).all()
        check(len(replayed_update_rows) == 1, "Exact UPDATE replay preserves activity count")
        check(replayed_update_rows[0].cost_amount == UPDATED_ACTIVITY_COST, "Exact UPDATE replay preserves updated activity")
        check(replayed_update_cycle.total_input_cost == UPDATED_ACTIVITY_COST, "Exact UPDATE replay preserves economic state")
        check(len(update_sync_audits) == 2, "CREATE and UPDATE each retain one sync-event audit")
    finally:
        db.close()

    stale_update_event_id = str(uuid.uuid4())
    stale_update_event = {
        **update_event,
        "event_id": stale_update_event_id,
        "payload": {
            **update_payload,
            "input_name": "Stale changed offline activity",
            "cost_amount": "999.00",
        },
    }
    stale_update_response = client.post(
        "/api/v1/sync/events",
        json={"events": [stale_update_event]},
        headers=HEADERS,
    )
    check(stale_update_response.status_code == 200, "Stale changed-payload UPDATE returns 200")
    stale_update_result = stale_update_response.json()
    stale_conflicts = stale_update_result.get("conflicts") or []
    check(len(stale_conflicts) == 1, "Stale changed-payload UPDATE is conflicted")
    check(stale_conflicts[0].get("conflict_type") == "VERSION_MISMATCH", "Stale UPDATE preserves VERSION_MISMATCH policy")
    check(stale_update_event_id not in (stale_update_result.get("accepted") or []), "Stale UPDATE is not acknowledged as committed")

    db = SessionLocal()
    try:
        after_stale = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).one()
        after_stale_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        check(after_stale.input_name == update_payload["input_name"], "Stale UPDATE does not change authoritative activity")
        check(after_stale.cost_amount == UPDATED_ACTIVITY_COST, "Stale UPDATE does not change authoritative cost")
        check(after_stale_cycle.total_input_cost == UPDATED_ACTIVITY_COST, "Stale UPDATE does not change cycle economics")
    finally:
        db.close()

    second_cycle_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        original_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        now = datetime.now(timezone.utc)
        db.add(CropCycle(
            id=uuid.UUID(second_cycle_id),
            tenant_id=TENANT_ID,
            farmer_id=original_cycle.farmer_id,
            parcel_id=original_cycle.parcel_id,
            project_id=original_cycle.project_id,
            crop_code=original_cycle.crop_code,
            variety_code=original_cycle.variety_code,
            season_code=original_cycle.season_code,
            lifecycle_template_id=original_cycle.lifecycle_template_id,
            workflow_template_version_id=original_cycle.workflow_template_version_id,
            planned_sowing_date=date.today() + timedelta(days=14),
            expected_harvest_date=original_cycle.expected_harvest_date,
            status="PLANNED",
            total_input_cost=Decimal("0"),
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        check(True, "Synthetic second cycle for identity-boundary checks is isolated")
    finally:
        db.close()

    for operation, version in (("CREATE", 3), ("UPDATE", 4)):
        cross_event_id = str(uuid.uuid4())
        cross_event = {
            **update_event,
            "event_id": cross_event_id,
            "operation": operation,
            "version": version,
            "payload": {
                **update_payload,
                "crop_cycle_id": second_cycle_id,
            },
        }
        cross_response = client.post(
            "/api/v1/sync/events",
            json={"events": [cross_event]},
            headers=HEADERS,
        )
        check(cross_response.status_code == 200, f"Cross-cycle {operation} returns batch response")
        cross_result = cross_response.json()
        failures = cross_result.get("failed") or []
        check(len(failures) == 1, f"Cross-cycle {operation} is rejected")
        check(failures[0].get("error_code") == "MATERIALIZATION_FAILED", f"Cross-cycle {operation} uses materialization rejection")
        check(cross_event_id not in (cross_result.get("accepted") or []), f"Cross-cycle {operation} is not accepted")

    db = SessionLocal()
    try:
        after_cross = db.query(CropActivity).filter(
            CropActivity.id == uuid.UUID(activity_id),
            CropActivity.tenant_id == TENANT_ID,
        ).all()
        original_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        second_cycle = db.query(CropCycle).filter(
            CropCycle.id == uuid.UUID(second_cycle_id),
            CropCycle.tenant_id == TENANT_ID,
        ).one()
        check(len(after_cross) == 1, "Cross-cycle rejections preserve one original activity")
        check(after_cross[0].crop_cycle_id == uuid.UUID(cycle_id), "Cross-cycle rejections preserve original cycle binding")
        check(after_cross[0].cost_amount == UPDATED_ACTIVITY_COST, "Cross-cycle rejections preserve original activity cost")
        check(original_cycle.total_input_cost == UPDATED_ACTIVITY_COST, "Cross-cycle rejections preserve original cycle economics")
        check((second_cycle.total_input_cost or Decimal("0")) == Decimal("0"), "Cross-cycle rejections do not change target cycle economics")
    finally:
        db.close()

    list_response, activities = get_json(f"/api/v1/crop-cycles/{cycle_id}/activities")
    check(list_response.status_code == 200, "Activity list returns 200", list_response.text[:1000])
    logged = next((row for row in activities if row.get("id") == activity_id), None)
    check(bool(logged), "Logged activity appears in activity list", activities)
    check(
        len([row for row in activities if row.get("id") == activity_id]) == 1,
        "Direct plus fallback retains one activity identity",
    )
    check(logged.get("stage_code") == stage_code, "Activity list preserves stage_code", logged)
    check(logged.get("input_name") == update_payload["input_name"], "Activity list exposes applied UPDATE", logged)
    check(logged.get("cost_amount") == str(UPDATED_ACTIVITY_COST), "Activity list exposes updated cost_amount", logged)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    check(stage_summary.get("schema_version") == "crop_cycle_stage_cost_summary.v1", "Stage-cost summary schema stable", stage_summary.get("schema_version"))
    check((stage_summary.get("totals") or {}).get("activity_count") == 1, "Stage-cost summary activity_count updated", stage_summary.get("totals"))
    check((stage_summary.get("totals") or {}).get("actual_expense") == str(UPDATED_ACTIVITY_COST), "Stage-cost summary reflects UPDATE expense", stage_summary.get("totals"))
    stage_row = next((row for row in stage_summary.get("stage_summaries") or [] if row.get("stage_code") == stage_code), None)
    check(bool(stage_row), "Stage-cost summary includes active stage row", stage_summary.get("stage_summaries"))
    check(stage_row.get("activity_count") == 1, "Active stage summary activity_count updated", stage_row)
    check(stage_row.get("actual_expense") == str(UPDATED_ACTIVITY_COST), "Active stage reflects UPDATE expense", stage_row)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{cycle_id}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    check(pnl.get("schema_version") == "crop_cycle_profit_loss_summary.v1", "P&L summary schema stable", pnl.get("schema_version"))
    check((pnl.get("totals") or {}).get("total_expenses") == str(UPDATED_ACTIVITY_COST), "P&L total expenses reflect UPDATE", pnl.get("totals"))

    print("=" * 72)
    print("Android crop-cycle activity logging flow validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
