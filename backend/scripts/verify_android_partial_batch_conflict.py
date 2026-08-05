"""Verify Android partial-batch success + WORKFLOW_INVALID conflict replay.

Required identifiers can be passed as CLI args or environment variables:

    ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID
    ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID
    ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID
    ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID

Optional modes:

--send-mixed-batch
    POST one valid crop_activity plus one WORKFLOW_INVALID crop_stage event.

--resend-mixed-batch
    POST the same mixed batch again and assert idempotent activity +
    repeated/durable conflict behavior.

--ack-conflict
    Resolve/acknowledge the conflict with ACCEPT_SERVER, matching Android's
    conflict recovery lifecycle after local draft discard/context refresh.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent
from app.modules.workflow.models import CropActivity, CropStageInstance


TENANT_ID = "android-dynamic-test"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_partial_batch_conflict_baseline.json")
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


def valid_activity_event(event_id: str, activity_id: str) -> dict:
    return {
        "event_id": event_id,
        "entity_type": "crop_activity",
        "entity_id": activity_id,
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": CYCLE_ID,
            "stage_code": EXPECTED_STAGE_CODE,
            "activity_date": "2026-08-02",
            "activity_type": "FERTILIZER",
            "input_code": "DAP_18_46_0",
            "input_name": "DAP 18-46-0",
            "quantity": 1,
            "quantity_unit": "KG",
            "cost_amount": float(EXPECTED_COST),
            "currency": "INR",
            "notes": "Partial batch success plus conflict activity test",
        },
        "metadata": {
            "source": "android_maestro_partial_batch_conflict_test",
        },
    }


def workflow_invalid_stage_event(event_id: str, entity_id: str) -> dict:
    return {
        "event_id": event_id,
        "entity_type": "crop_stage",
        "entity_id": entity_id,
        "operation": "UPDATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": CYCLE_ID,
            "stage_code": EXPECTED_STAGE_CODE,
            "action": "START",
            "actual_start_date": "2026-08-02",
        },
        "metadata": {
            "source": "android_maestro_partial_batch_conflict_test",
        },
    }


def mixed_batch(args) -> list[dict]:
    return [
        valid_activity_event(args.activity_event_id, args.activity_id),
        workflow_invalid_stage_event(args.conflict_event_id, args.conflict_entity_id),
    ]


def post_sync(events: list[dict]):
    response = client.post("/api/v1/sync/events", json={"events": events}, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--activity-event-id", default=os.getenv("ANDROID_PARTIAL_CONFLICT_ACTIVITY_EVENT_ID"))
    parser.add_argument("--activity-id", default=os.getenv("ANDROID_PARTIAL_CONFLICT_ACTIVITY_ID"))
    parser.add_argument("--conflict-event-id", default=os.getenv("ANDROID_PARTIAL_CONFLICT_STAGE_EVENT_ID"))
    parser.add_argument("--conflict-entity-id", default=os.getenv("ANDROID_PARTIAL_CONFLICT_STAGE_ENTITY_ID"))


def require_ids(args) -> None:
    for name in ["activity_event_id", "activity_id", "conflict_event_id", "conflict_entity_id"]:
        check(bool(getattr(args, name)), f"{name} supplied")
        UUID(str(getattr(args, name)))


def sync_failed_for_event(db, event_id: UUID) -> list[AuditChainEntry]:
    failures = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in failures
        if ((row.metadata_ or {}).get("sync_event_id") and str((row.metadata_ or {}).get("sync_event_id")) == str(event_id))
        or str(row.correlation_id) == str(event_id)
    ]


def assert_mixed_response(payload: dict, args) -> None:
    check(payload.get("accepted") == [args.activity_event_id], "Mixed response accepted only activity event", payload)
    check(payload.get("failed") == [], "Mixed response failed list is empty", payload)
    conflicts = payload.get("conflicts") or []
    check(len(conflicts) == 1, "Mixed response contains one conflict", payload)
    conflict = conflicts[0]
    check(conflict.get("event_id") == args.conflict_event_id, "Conflict event_id matches stage event", conflict)
    check(conflict.get("conflict_type") == "WORKFLOW_INVALID", "Conflict type is WORKFLOW_INVALID", conflict)
    check(conflict.get("resolution_strategy") == "SERVER_AUTHORITY", "Conflict resolution strategy is SERVER_AUTHORITY", conflict)
    check("Invalid stage transition" in (conflict.get("detail") or ""), "Conflict detail explains invalid stage transition", conflict)
    check(payload.get("total_processed") == 2, "Mixed response total_processed is 2", payload)


def find_conflict(db, event_id: str, prefer_pending: bool = False) -> SyncConflict | None:
    query = db.query(SyncConflict).filter(
        SyncConflict.tenant_id == TENANT_ID,
        SyncConflict.event_id == UUID(event_id),
    )
    if prefer_pending:
        pending = query.filter(SyncConflict.status == "PENDING_REVIEW").order_by(SyncConflict.created_at.desc()).first()
        if pending is not None:
            return pending
    return query.order_by(SyncConflict.created_at.desc()).first()


def main() -> int:
    parser = argparse.ArgumentParser()
    add_args(parser)
    parser.add_argument("--send-mixed-batch", action="store_true")
    parser.add_argument("--resend-mixed-batch", action="store_true")
    parser.add_argument("--ack-conflict", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID PARTIAL-BATCH SUCCESS + CONFLICT VERIFIER")
    print("=" * 72)

    require_ids(args)
    baseline = load_baseline(Path(args.baseline_path))
    baseline_count = int(baseline.get("activity_count") or 0)
    baseline_stage_expense = money(baseline.get("stage_summary_actual_expense"))
    baseline_pnl_expense = money(baseline.get("pnl_total_expenses"))

    if args.send_mixed_batch:
        response, payload = post_sync(mixed_batch(args))
        check(response.status_code == 200, "Mixed success+conflict batch returns HTTP 200", payload)
        assert_mixed_response(payload, args)

    if args.resend_mixed_batch:
        response, payload = post_sync(mixed_batch(args))
        check(response.status_code == 200, "Resend mixed success+conflict batch returns HTTP 200", payload)
        assert_mixed_response(payload, args)

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    matches = [row for row in activities if row.get("id") == args.activity_id]
    check(len(matches) == 1, "Accepted activity materialized exactly once", matches)
    activity = matches[0]
    check(activity.get("stage_code") == EXPECTED_STAGE_CODE, "Accepted activity linked to NURSERY", activity)
    check(money(activity.get("cost_amount")) == EXPECTED_COST, "Accepted activity cost is 325.50", activity)

    nursery_count = len([row for row in activities if row.get("stage_code") == EXPECTED_STAGE_CODE])
    check(nursery_count == baseline_count + 1, "NURSERY activity count increased by exactly one", {
        "baseline_count": baseline_count,
        "current_nursery_count": nursery_count,
    })

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    stage_totals = stage_summary.get("totals") or {}
    current_stage_expense = money(stage_totals.get("actual_expense"))
    check(current_stage_expense == baseline_stage_expense + EXPECTED_COST, "Stage-cost actual_expense increased exactly once", {
        "baseline_actual_expense": str(baseline_stage_expense),
        "current_actual_expense": str(current_stage_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    pnl_totals = pnl.get("totals") or {}
    current_pnl_expense = money(pnl_totals.get("total_expenses"))
    check(current_pnl_expense == baseline_pnl_expense + EXPECTED_COST, "P&L total_expenses increased exactly once", {
        "baseline_total_expenses": str(baseline_pnl_expense),
        "current_total_expenses": str(current_pnl_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    db = SessionLocal()
    try:
        activity_processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == UUID(args.activity_event_id),
        ).first()
        check(activity_processed is not None, "Accepted activity processed event exists", {"event_id": args.activity_event_id})
        check(activity_processed.status == "COMMITTED", "Accepted activity processed event is COMMITTED", activity_processed.status)

        conflict_processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == UUID(args.conflict_event_id),
        ).first()
        check(conflict_processed is not None, "Conflict processed event exists", {"event_id": args.conflict_event_id})
        check(conflict_processed.status == "CONFLICT", "Conflict processed event status is CONFLICT", conflict_processed.status)
        check(conflict_processed.entity_type == "crop_stage", "Conflict processed event entity_type is crop_stage", conflict_processed.entity_type)

        conflict = find_conflict(db, args.conflict_event_id)
        check(conflict is not None, "Durable sync_conflicts row exists", {"event_id": args.conflict_event_id})
        check(conflict.conflict_type == "WORKFLOW_INVALID", "Durable conflict_type is WORKFLOW_INVALID", conflict.conflict_type)
        check(conflict.resolution_strategy == "SERVER_AUTHORITY", "Durable resolution_strategy is SERVER_AUTHORITY", conflict.resolution_strategy)
        check(conflict.status in {"PENDING_REVIEW", "RESOLVED_SERVER"}, "Durable conflict status is pending or resolved", conflict.status)

        failed_activity = sync_failed_for_event(db, UUID(args.activity_event_id))
        check(not failed_activity, "No SYNC_FAILED audit for accepted activity", [{"id": row.id, "metadata": row.metadata_} for row in failed_activity])
        failed_conflict = sync_failed_for_event(db, UUID(args.conflict_event_id))
        check(not failed_conflict, "No SYNC_FAILED audit for conflict event", [{"id": row.id, "metadata": row.metadata_} for row in failed_conflict])

        conflict_stage_rows = db.query(CropStageInstance).filter(
            CropStageInstance.tenant_id == TENANT_ID,
            CropStageInstance.id == UUID(args.conflict_entity_id),
        ).all()
        check(not conflict_stage_rows, "Conflict entity_id did not materialize as server stage row", [
            {"id": str(row.id), "stage_code": row.stage_code, "status": row.status}
            for row in conflict_stage_rows
        ])
    finally:
        db.close()

    pending_response, pending = get_json("/api/v1/sync/conflicts/pending?limit=100")
    check(pending_response.status_code == 200, "Android pending conflicts endpoint returns 200", pending_response.text[:1000])
    pending_conflicts = pending.get("conflicts") or []
    pending_match = next((row for row in pending_conflicts if row.get("event_id") == args.conflict_event_id), None)

    if args.ack_conflict:
        db = SessionLocal()
        try:
            conflict = find_conflict(db, args.conflict_event_id, prefer_pending=True)
            check(conflict is not None, "Conflict exists before acknowledgement", {"event_id": args.conflict_event_id})
            conflict_id = str(conflict.id)
        finally:
            db.close()

        ack_response = client.patch(
            f"/api/v1/sync/conflicts/{conflict_id}",
            json={"strategy": "ACCEPT_SERVER"},
            headers=HEADERS,
        )
        ack_payload = ack_response.json()
        check(ack_response.status_code == 200, "Conflict ACK ACCEPT_SERVER returns 200", ack_payload)
        check((ack_payload.get("status") or ack_payload.get("conflict", {}).get("status")) in {"RESOLVED_SERVER", "RESOLVED", "resolved"}, "Conflict ACK marks row resolved", ack_payload)

        db = SessionLocal()
        try:
            conflict = find_conflict(db, args.conflict_event_id)
            check(conflict.status == "RESOLVED_SERVER", "Durable conflict status is RESOLVED_SERVER after ACK", conflict.status)
        finally:
            db.close()
    else:
        check(pending_match is not None, "Pending conflicts endpoint includes WORKFLOW_INVALID event", pending)
        check(pending_match.get("conflict_type") == "WORKFLOW_INVALID", "Pending conflict type is WORKFLOW_INVALID", pending_match)
        check(pending_match.get("android_action") == "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE", "Pending conflict android_action is server-authority workflow message", pending_match)

    print(json.dumps({
        "schema_version": "android_partial_batch_conflict_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": CYCLE_ID,
        "activity_id": args.activity_id,
        "event_ids": {
            "accepted_activity": args.activity_event_id,
            "workflow_invalid_stage": args.conflict_event_id,
        },
        "mixed_batch_sent_by_verifier": bool(args.send_mixed_batch),
        "mixed_batch_resend_performed": bool(args.resend_mixed_batch),
        "conflict_ack_performed": bool(args.ack_conflict),
        "expected_android_behavior": {
            "accepted_activity": "mark local row synced",
            "workflow_invalid_conflict": "show server-authority workflow conflict UI, not retry queue",
            "title": "Workflow changed on backend",
        },
        "random_android_ids_supported": True,
    }, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("Android partial-batch success + conflict verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
