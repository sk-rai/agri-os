"""Verify Android dependency-ordered offline replay after cold start/reboot.

Required identifiers can be passed as CLI args or environment variables:

    ANDROID_DEP_ORDER_CYCLE_EVENT_ID
    ANDROID_DEP_ORDER_CYCLE_ID
    ANDROID_DEP_ORDER_STAGE_EVENT_ID
    ANDROID_DEP_ORDER_STAGE_ENTITY_ID
    ANDROID_DEP_ORDER_ACTIVITY_EVENT_ID
    ANDROID_DEP_ORDER_ACTIVITY_ID

Optional --resend posts the same three events again and verifies idempotency.
Optional --send-out-of-order-stage posts the stage event before the cycle and
asserts the current DEPENDENCY_MISSING response shape. It is safe to follow with
the ordered batch because DEPENDENCY_MISSING rows are retryable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance
from scripts.seed_android_crop_cycle_test_fixture import (
    CROP_CODE,
    FARMER_ID,
    PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
)


ACTOR_ID = "11111111-1111-4111-8111-111111111111"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_dependency_order_replay_baseline.json")
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}

client = TestClient(app)


def check(condition, label, detail=None):
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str) if isinstance(detail, (dict, list)) else detail)
        raise AssertionError(label)
    print(f"PASS {label}")
    if detail is not None:
        print("     ", json.dumps(detail, sort_keys=True, default=str)[:1000] if isinstance(detail, (dict, list)) else detail)


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def get_json(path: str):
    response = client.get(path, headers={"X-Tenant-ID": TENANT_ID})
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def load_baseline(path: Path) -> dict:
    check(path.exists(), "Baseline file exists", str(path))
    return json.loads(path.read_text())


def crop_cycle_event(cycle_event_id: str, cycle_id: str) -> dict:
    return {
        "event_id": cycle_event_id,
        "entity_type": "crop_cycle",
        "entity_id": cycle_id,
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "project_id": str(PROJECT_ID),
            "crop_code": CROP_CODE,
            "season_code": SEASON_CODE,
            "planned_sowing_date": "2026-08-02",
            "status": "PLANNED",
        },
        "metadata": {
            "source": "android_maestro_dependency_order_replay_test",
        },
    }


def crop_stage_event(stage_event_id: str, stage_entity_id: str, cycle_event_id: str, cycle_id: str) -> dict:
    return {
        "event_id": stage_event_id,
        "entity_type": "crop_stage",
        "entity_id": stage_entity_id,
        "operation": "UPDATE",
        "version": 1,
        "dependency_ids": [cycle_event_id],
        "payload": {
            "crop_cycle_id": cycle_id,
            "stage_code": EXPECTED_STAGE_CODE,
            "action": "START",
            "actual_start_date": "2026-08-02",
        },
        "metadata": {
            "source": "android_maestro_dependency_order_replay_test",
        },
    }


def crop_activity_event(activity_event_id: str, activity_id: str, cycle_event_id: str, stage_event_id: str, cycle_id: str) -> dict:
    return {
        "event_id": activity_event_id,
        "entity_type": "crop_activity",
        "entity_id": activity_id,
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [cycle_event_id, stage_event_id],
        "payload": {
            "crop_cycle_id": cycle_id,
            "stage_code": EXPECTED_STAGE_CODE,
            "activity_date": "2026-08-02",
            "activity_type": "FERTILIZER",
            "input_code": "DAP_18_46_0",
            "input_name": "DAP 18-46-0",
            "quantity": 1,
            "quantity_unit": "KG",
            "cost_amount": float(EXPECTED_COST),
            "currency": "INR",
            "notes": "Dependency ordered replay after restart test",
        },
        "metadata": {
            "source": "android_maestro_dependency_order_replay_test",
        },
    }


def ordered_events(args) -> list[dict]:
    return [
        crop_cycle_event(args.cycle_event_id, args.cycle_id),
        crop_stage_event(args.stage_event_id, args.stage_entity_id, args.cycle_event_id, args.cycle_id),
        crop_activity_event(args.activity_event_id, args.activity_id, args.cycle_event_id, args.stage_event_id, args.cycle_id),
    ]


def post_sync(events: list[dict]):
    response = client.post("/api/v1/sync/events", json={"events": events}, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def failed_audit_entries(db, event_ids: set[UUID]) -> list[AuditChainEntry]:
    failures = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in failures
        if ((row.metadata_ or {}).get("sync_event_id") and UUID(str((row.metadata_ or {}).get("sync_event_id"))) in event_ids)
        or (row.correlation_id and row.correlation_id in event_ids)
    ]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--cycle-event-id", default=os.getenv("ANDROID_DEP_ORDER_CYCLE_EVENT_ID"))
    parser.add_argument("--cycle-id", default=os.getenv("ANDROID_DEP_ORDER_CYCLE_ID"))
    parser.add_argument("--stage-event-id", default=os.getenv("ANDROID_DEP_ORDER_STAGE_EVENT_ID"))
    parser.add_argument("--stage-entity-id", default=os.getenv("ANDROID_DEP_ORDER_STAGE_ENTITY_ID"))
    parser.add_argument("--activity-event-id", default=os.getenv("ANDROID_DEP_ORDER_ACTIVITY_EVENT_ID"))
    parser.add_argument("--activity-id", default=os.getenv("ANDROID_DEP_ORDER_ACTIVITY_ID"))


def require_ids(args) -> None:
    for name in [
        "cycle_event_id",
        "cycle_id",
        "stage_event_id",
        "stage_entity_id",
        "activity_event_id",
        "activity_id",
    ]:
        check(bool(getattr(args, name)), f"{name} supplied")
        UUID(str(getattr(args, name)))


def main() -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--resend", action="store_true", help="POST the same ordered batch again and assert idempotency.")
    parser.add_argument("--send-out-of-order-stage", action="store_true", help="POST stage before cycle and assert DEPENDENCY_MISSING.")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID DEPENDENCY-ORDERED OFFLINE REPLAY VERIFIER")
    print("=" * 72)

    require_ids(args)
    baseline = load_baseline(Path(args.baseline_path))
    check(baseline.get("tenant_id") == TENANT_ID, "Baseline tenant matches", baseline)
    check(baseline.get("farmer_id") == str(FARMER_ID), "Baseline farmer matches", baseline)
    check(baseline.get("parcel_id") == str(PARCEL_ID), "Baseline parcel matches", baseline)

    if args.send_out_of_order_stage:
        response, payload = post_sync([
            crop_stage_event(args.stage_event_id, args.stage_entity_id, args.cycle_event_id, args.cycle_id)
        ])
        check(response.status_code == 200, "Out-of-order stage replay returns HTTP 200", payload)
        check(payload.get("accepted") == [], "Out-of-order stage has no accepted rows", payload)
        check(payload.get("conflicts") == [], "Out-of-order stage has no conflicts", payload)
        failures = payload.get("failed") or []
        check(len(failures) == 1, "Out-of-order stage appears in failed list", payload)
        failure = failures[0]
        check(failure.get("event_id") == args.stage_event_id, "Out-of-order failed event_id is stage event", failure)
        check(failure.get("error_code") == "DEPENDENCY_MISSING", "Out-of-order error_code is DEPENDENCY_MISSING", failure)
        check(failure.get("detail_code") is None, "Out-of-order detail_code is currently null", failure)
        check(args.cycle_event_id in (failure.get("message") or ""), "Out-of-order message includes missing cycle event_id", failure)

    if args.resend:
        response, payload = post_sync(ordered_events(args))
        expected = {args.cycle_event_id, args.stage_event_id, args.activity_event_id}
        check(response.status_code == 200, "Ordered same-batch resend returns HTTP 200", payload)
        check(set(payload.get("accepted") or []) == expected, "Ordered same-batch resend accepted all event IDs", payload)
        check(payload.get("conflicts") == [], "Ordered same-batch resend has no conflicts", payload)
        check(payload.get("failed") == [], "Ordered same-batch resend has no failed rows", payload)
        check(payload.get("total_processed") == 3, "Ordered same-batch resend total_processed is 3", payload)

    cycle_response, cycle_body = get_json(f"/api/v1/crop-cycles/{args.cycle_id}")
    check(cycle_response.status_code == 200, "Crop cycle fetch returns 200", cycle_response.text[:1000])
    check(cycle_body.get("id") == args.cycle_id, "Crop cycle id matches Android entity_id", cycle_body)
    check(cycle_body.get("farmer_id") == str(FARMER_ID), "Crop cycle farmer matches fixture", cycle_body)
    check(cycle_body.get("parcel_id") == str(PARCEL_ID), "Crop cycle parcel matches fixture", cycle_body)
    check(cycle_body.get("crop_code") == CROP_CODE, "Crop cycle crop_code is RICE", cycle_body)
    check(cycle_body.get("season_code") == SEASON_CODE, "Crop cycle season_code is KHARIF", cycle_body)
    check(cycle_body.get("status") == "ACTIVE", "Crop cycle is ACTIVE after NURSERY START", cycle_body)

    nursery = next((stage for stage in cycle_body.get("stages") or [] if stage.get("code") == EXPECTED_STAGE_CODE), None)
    check(bool(nursery), "NURSERY stage exists", cycle_body.get("stages"))
    check(nursery.get("status") == "ACTIVE", "NURSERY stage is ACTIVE", nursery)
    check(nursery.get("actual_start_date") == "2026-08-02", "NURSERY actual_start_date is 2026-08-02", nursery)

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{args.cycle_id}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    matching = [row for row in activities if row.get("id") == args.activity_id]
    check(len(matching) == 1, "Exactly one activity API row exists for Android activity id", matching)
    activity = matching[0]
    check(activity.get("stage_code") == EXPECTED_STAGE_CODE, "Activity is linked to NURSERY", activity)
    check(money(activity.get("cost_amount")) == EXPECTED_COST, "Activity cost is 325.50", activity)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{args.cycle_id}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    stage_totals = stage_summary.get("totals") or {}
    check(money(stage_totals.get("actual_expense")) == EXPECTED_COST, "Stage-cost actual_expense is exactly 325.50", stage_totals)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{args.cycle_id}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    pnl_totals = pnl.get("totals") or {}
    check(money(pnl_totals.get("total_expenses")) == EXPECTED_COST, "P&L total_expenses is exactly 325.50", pnl_totals)

    event_ids = {
        UUID(args.cycle_event_id),
        UUID(args.stage_event_id),
        UUID(args.activity_event_id),
    }
    db = SessionLocal()
    try:
        processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id.in_(event_ids),
        ).all()
        processed_by_id = {str(row.event_id): row for row in processed}
        check(set(processed_by_id) == {str(item) for item in event_ids}, "sync_processed_events rows exist for all three events", [
            {"event_id": str(row.event_id), "entity_type": row.entity_type, "entity_id": str(row.entity_id) if row.entity_id else None, "status": row.status}
            for row in processed
        ])
        for event_id in [args.cycle_event_id, args.stage_event_id, args.activity_event_id]:
            check(processed_by_id[event_id].status == "COMMITTED", f"{event_id} status is COMMITTED", processed_by_id[event_id].status)

        cycle_rows = db.query(CropCycle).filter(CropCycle.tenant_id == TENANT_ID, CropCycle.id == UUID(args.cycle_id)).all()
        check(len(cycle_rows) == 1, "Exactly one crop_cycles row exists for cycle entity_id", [
            {"id": str(row.id), "status": row.status, "crop_code": row.crop_code, "season_code": row.season_code}
            for row in cycle_rows
        ])
        stage_rows = db.query(CropStageInstance).filter(
            CropStageInstance.tenant_id == TENANT_ID,
            CropStageInstance.crop_cycle_id == UUID(args.cycle_id),
            CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
        ).all()
        check(len(stage_rows) == 1, "Exactly one NURSERY stage row exists for cycle", [
            {"id": str(row.id), "status": row.status, "actual_start_date": row.actual_start_date}
            for row in stage_rows
        ])
        activity_rows = db.query(CropActivity).filter(CropActivity.tenant_id == TENANT_ID, CropActivity.id == UUID(args.activity_id)).all()
        check(len(activity_rows) == 1, "Exactly one crop_activities row exists for activity entity_id", [
            {"id": str(row.id), "crop_cycle_id": str(row.crop_cycle_id), "cost_amount": str(row.cost_amount)}
            for row in activity_rows
        ])
        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id.in_(event_ids),
        ).all()
        check(not conflicts, "No sync_conflicts rows exist for ordered replay events", [
            {"id": str(row.id), "event_id": str(row.event_id), "conflict_type": row.conflict_type}
            for row in conflicts
        ])
        failures = failed_audit_entries(db, event_ids)
        check(not failures, "No SYNC_FAILED audit rows exist for ordered replay events", [
            {"id": row.id, "metadata": row.metadata_}
            for row in failures
        ])
    finally:
        db.close()

    print(json.dumps({
        "schema_version": "android_dependency_order_replay_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": args.cycle_id,
        "activity_id": args.activity_id,
        "event_ids": {
            "cycle": args.cycle_event_id,
            "stage": args.stage_event_id,
            "activity": args.activity_event_id,
        },
        "dependency_id_contract": {
            "canonical_android_dependency_ids": "sync event IDs",
            "backend_currently_accepts": ["committed event_id", "committed entity_id"],
            "recommended": {
                "crop_cycle": [],
                "crop_stage": ["cycle_event_id"],
                "crop_activity": ["cycle_event_id", "stage_event_id"],
            },
        },
        "duplicate_resend_performed": bool(args.resend),
        "out_of_order_stage_probe_performed": bool(args.send_out_of_order_stage),
        "random_android_ids_supported": True,
    }, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("Android dependency-ordered offline replay verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
