"""Verify Android partial-batch offline sync replay resilience.

Required identifiers can be passed as CLI args or environment variables:

    ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID
    ANDROID_PARTIAL_VALID_ACTIVITY_ID
    ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID
    ANDROID_PARTIAL_MISSING_CYCLE_ID
    ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID
    ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID

Optional modes:

--send-mixed-batch
    POST one valid crop_activity plus one dependency-missing crop_stage.

--commit-dependency-and-retry
    POST the missing crop_cycle dependency, then retry the same crop_stage event.

--resend-mixed-batch
    POST the original mixed batch again and assert idempotent/partial behavior.
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
    FARMER_ID as DEP_FARMER_ID,
    PARCEL_ID as DEP_PARCEL_ID,
    PROJECT_ID,
    SEASON_CODE,
    TENANT_ID,
)


ACTOR_ID = "11111111-1111-4111-8111-111111111111"
VALID_CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_partial_batch_replay_baseline.json")
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
            "crop_cycle_id": VALID_CYCLE_ID,
            "stage_code": EXPECTED_STAGE_CODE,
            "activity_date": "2026-08-02",
            "activity_type": "FERTILIZER",
            "input_code": "DAP_18_46_0",
            "input_name": "DAP 18-46-0",
            "quantity": 1,
            "quantity_unit": "KG",
            "cost_amount": float(EXPECTED_COST),
            "currency": "INR",
            "notes": "Partial batch valid activity test",
        },
        "metadata": {
            "source": "android_maestro_partial_batch_replay_test",
        },
    }


def missing_cycle_event(event_id: str, cycle_id: str) -> dict:
    return {
        "event_id": event_id,
        "entity_type": "crop_cycle",
        "entity_id": cycle_id,
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "farmer_id": str(DEP_FARMER_ID),
            "parcel_id": str(DEP_PARCEL_ID),
            "project_id": str(PROJECT_ID),
            "crop_code": CROP_CODE,
            "season_code": SEASON_CODE,
            "planned_sowing_date": "2026-08-02",
            "status": "PLANNED",
        },
        "metadata": {
            "source": "android_maestro_partial_batch_replay_test",
        },
    }


def missing_stage_event(stage_event_id: str, stage_entity_id: str, cycle_event_id: str, cycle_id: str) -> dict:
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
            "source": "android_maestro_partial_batch_replay_test",
        },
    }


def mixed_batch(args) -> list[dict]:
    return [
        valid_activity_event(args.valid_activity_event_id, args.valid_activity_id),
        missing_stage_event(
            args.missing_stage_event_id,
            args.missing_stage_entity_id,
            args.missing_cycle_event_id,
            args.missing_cycle_id,
        ),
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
    parser.add_argument("--valid-activity-event-id", default=os.getenv("ANDROID_PARTIAL_VALID_ACTIVITY_EVENT_ID"))
    parser.add_argument("--valid-activity-id", default=os.getenv("ANDROID_PARTIAL_VALID_ACTIVITY_ID"))
    parser.add_argument("--missing-cycle-event-id", default=os.getenv("ANDROID_PARTIAL_MISSING_CYCLE_EVENT_ID"))
    parser.add_argument("--missing-cycle-id", default=os.getenv("ANDROID_PARTIAL_MISSING_CYCLE_ID"))
    parser.add_argument("--missing-stage-event-id", default=os.getenv("ANDROID_PARTIAL_MISSING_STAGE_EVENT_ID"))
    parser.add_argument("--missing-stage-entity-id", default=os.getenv("ANDROID_PARTIAL_MISSING_STAGE_ENTITY_ID"))


def require_ids(args) -> None:
    for name in [
        "valid_activity_event_id",
        "valid_activity_id",
        "missing_cycle_event_id",
        "missing_cycle_id",
        "missing_stage_event_id",
        "missing_stage_entity_id",
    ]:
        check(bool(getattr(args, name)), f"{name} supplied")
        UUID(str(getattr(args, name)))


def failure_entries_for_event(db, event_id: UUID) -> list[AuditChainEntry]:
    failures = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in failures
        if ((row.metadata_ or {}).get("sync_event_id") and str((row.metadata_ or {}).get("sync_event_id")) == str(event_id))
        or str(row.correlation_id) == str(event_id)
    ]


def assert_mixed_response(payload: dict, args, *, after_dependency: bool = False) -> None:
    expected_accepted = {args.valid_activity_event_id}
    if after_dependency:
        expected_accepted.add(args.missing_stage_event_id)
    check(set(payload.get("accepted") or []) == expected_accepted, "Mixed batch accepted set matches expected", payload)
    check(payload.get("conflicts") == [], "Mixed batch has no conflicts", payload)
    failures = payload.get("failed") or []
    if after_dependency:
        check(failures == [], "Mixed batch has no failed rows after dependency commit", payload)
    else:
        check(len(failures) == 1, "Mixed batch has one failed row", payload)
        failure = failures[0]
        check(failure.get("event_id") == args.missing_stage_event_id, "Failed row is missing-stage event", failure)
        check(failure.get("error_code") == "DEPENDENCY_MISSING", "Failed row error_code is DEPENDENCY_MISSING", failure)
        check(failure.get("detail_code") is None, "Failed row detail_code is currently null", failure)
        check(args.missing_cycle_event_id in (failure.get("message") or ""), "Failed row message includes missing cycle event_id", failure)


def main() -> int:
    parser = argparse.ArgumentParser()
    add_args(parser)
    parser.add_argument("--send-mixed-batch", action="store_true")
    parser.add_argument("--commit-dependency-and-retry", action="store_true")
    parser.add_argument("--resend-mixed-batch", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID PARTIAL-BATCH OFFLINE REPLAY VERIFIER")
    print("=" * 72)

    require_ids(args)
    baseline = load_baseline(Path(args.baseline_path))
    valid_baseline = baseline.get("valid_context") or {}
    baseline_activity_count = int(valid_baseline.get("activity_count") or 0)
    baseline_stage_expense = money(valid_baseline.get("stage_summary_actual_expense"))
    baseline_pnl_expense = money(valid_baseline.get("pnl_total_expenses"))

    if args.send_mixed_batch:
        response, payload = post_sync(mixed_batch(args))
        check(response.status_code == 200, "Mixed batch returns HTTP 200", payload)
        assert_mixed_response(payload, args, after_dependency=False)
        check(payload.get("total_processed") == 2, "Mixed batch total_processed is 2", payload)

    if args.commit_dependency_and_retry:
        dependency_response, dependency_payload = post_sync([
            missing_cycle_event(args.missing_cycle_event_id, args.missing_cycle_id)
        ])
        check(dependency_response.status_code == 200, "Missing crop_cycle dependency create returns HTTP 200", dependency_payload)
        check(dependency_payload.get("accepted") == [args.missing_cycle_event_id], "Missing crop_cycle dependency accepted", dependency_payload)
        check(dependency_payload.get("conflicts") == [], "Missing crop_cycle dependency has no conflicts", dependency_payload)
        check(dependency_payload.get("failed") == [], "Missing crop_cycle dependency has no failed rows", dependency_payload)

        retry_response, retry_payload = post_sync([
            missing_stage_event(
                args.missing_stage_event_id,
                args.missing_stage_entity_id,
                args.missing_cycle_event_id,
                args.missing_cycle_id,
            )
        ])
        check(retry_response.status_code == 200, "Retry missing-stage event returns HTTP 200", retry_payload)
        check(retry_payload.get("accepted") == [args.missing_stage_event_id], "Retry missing-stage event accepted", retry_payload)
        check(retry_payload.get("conflicts") == [], "Retry missing-stage has no conflicts", retry_payload)
        check(retry_payload.get("failed") == [], "Retry missing-stage has no failed rows", retry_payload)

    if args.resend_mixed_batch:
        response, payload = post_sync(mixed_batch(args))
        check(response.status_code == 200, "Resend mixed batch returns HTTP 200", payload)
        dep_committed = False
        db = SessionLocal()
        try:
            dep_committed = db.query(SyncProcessedEvent).filter(
                SyncProcessedEvent.tenant_id == TENANT_ID,
                SyncProcessedEvent.event_id == UUID(args.missing_stage_event_id),
                SyncProcessedEvent.status == "COMMITTED",
            ).first() is not None
        finally:
            db.close()
        assert_mixed_response(payload, args, after_dependency=dep_committed)
        check(payload.get("total_processed") == 2, "Resend mixed batch total_processed is 2", payload)

    valid_activity_response, valid_activities = get_json(f"/api/v1/crop-cycles/{VALID_CYCLE_ID}/activities")
    check(valid_activity_response.status_code == 200, "Valid cycle activity list returns 200", valid_activity_response.text[:1000])
    valid_matches = [row for row in valid_activities if row.get("id") == args.valid_activity_id]
    check(len(valid_matches) == 1, "Valid activity materialized exactly once", valid_matches)
    valid_activity = valid_matches[0]
    check(valid_activity.get("stage_code") == EXPECTED_STAGE_CODE, "Valid activity linked to NURSERY", valid_activity)
    check(money(valid_activity.get("cost_amount")) == EXPECTED_COST, "Valid activity cost is 325.50", valid_activity)

    current_valid_nursery_count = len([row for row in valid_activities if row.get("stage_code") == EXPECTED_STAGE_CODE])
    check(current_valid_nursery_count == baseline_activity_count + 1, "Valid NURSERY activity count increased by exactly one", {
        "baseline_activity_count": baseline_activity_count,
        "current_valid_nursery_count": current_valid_nursery_count,
    })

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{VALID_CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Valid cycle stage-cost summary returns 200", stage_summary_response.text[:1000])
    stage_totals = stage_summary.get("totals") or {}
    current_stage_expense = money(stage_totals.get("actual_expense"))
    check(current_stage_expense == baseline_stage_expense + EXPECTED_COST, "Valid cycle stage-cost actual_expense increased exactly once", {
        "baseline_actual_expense": str(baseline_stage_expense),
        "current_actual_expense": str(current_stage_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{VALID_CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "Valid cycle P&L summary returns 200", pnl_response.text[:1000])
    pnl_totals = pnl.get("totals") or {}
    current_pnl_expense = money(pnl_totals.get("total_expenses"))
    check(current_pnl_expense == baseline_pnl_expense + EXPECTED_COST, "Valid cycle P&L total_expenses increased exactly once", {
        "baseline_total_expenses": str(baseline_pnl_expense),
        "current_total_expenses": str(current_pnl_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    db = SessionLocal()
    try:
        valid_processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == UUID(args.valid_activity_event_id),
        ).first()
        check(valid_processed is not None, "Valid sync_processed_events row exists", {"event_id": args.valid_activity_event_id})
        check(valid_processed.status == "COMMITTED", "Valid sync_processed_events status is COMMITTED", valid_processed.status)

        missing_stage_processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == UUID(args.missing_stage_event_id),
        ).first()
        check(missing_stage_processed is not None, "Missing-stage sync_processed_events row exists", {"event_id": args.missing_stage_event_id})

        missing_cycle = db.query(CropCycle).filter(
            CropCycle.tenant_id == TENANT_ID,
            CropCycle.id == UUID(args.missing_cycle_id),
        ).first()
        missing_stage_committed = missing_stage_processed.status == "COMMITTED"
        if missing_stage_committed:
            check(missing_cycle is not None, "Missing dependency crop_cycle materialized after retry", {"cycle_id": args.missing_cycle_id})
            stage = db.query(CropStageInstance).filter(
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.crop_cycle_id == UUID(args.missing_cycle_id),
                CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
            ).first()
            check(stage is not None, "Retried missing-stage NURSERY row exists", {"cycle_id": args.missing_cycle_id})
            check(stage.status == "ACTIVE", "Retried missing-stage NURSERY is ACTIVE", {"status": stage.status})
        else:
            check(missing_stage_processed.status == "DEPENDENCY_MISSING", "Missing-stage row remains DEPENDENCY_MISSING before retry", missing_stage_processed.status)
            check(missing_cycle is None, "Missing dependency crop_cycle not materialized before retry", {"cycle_id": args.missing_cycle_id})

        valid_conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id.in_([
                UUID(args.valid_activity_event_id),
                UUID(args.missing_stage_event_id),
                UUID(args.missing_cycle_event_id),
            ]),
        ).all()
        check(not valid_conflicts, "No sync_conflicts rows for partial-batch events", [
            {"id": str(row.id), "event_id": str(row.event_id), "conflict_type": row.conflict_type}
            for row in valid_conflicts
        ])

        valid_failures = failure_entries_for_event(db, UUID(args.valid_activity_event_id))
        check(not valid_failures, "No SYNC_FAILED audit for accepted valid activity", [
            {"id": row.id, "metadata": row.metadata_}
            for row in valid_failures
        ])
        missing_stage_failures = failure_entries_for_event(db, UUID(args.missing_stage_event_id))
        check(not missing_stage_failures, "No SYNC_FAILED audit for retryable DEPENDENCY_MISSING stage", [
            {"id": row.id, "metadata": row.metadata_}
            for row in missing_stage_failures
        ])
    finally:
        db.close()

    print(json.dumps({
        "schema_version": "android_partial_batch_replay_verify.v1",
        "tenant_id": TENANT_ID,
        "valid_cycle_id": VALID_CYCLE_ID,
        "valid_activity_id": args.valid_activity_id,
        "missing_cycle_id": args.missing_cycle_id,
        "event_ids": {
            "valid_activity": args.valid_activity_event_id,
            "missing_cycle": args.missing_cycle_event_id,
            "missing_stage": args.missing_stage_event_id,
        },
        "mixed_batch_sent_by_verifier": bool(args.send_mixed_batch),
        "dependency_retry_performed": bool(args.commit_dependency_and_retry),
        "mixed_batch_resend_performed": bool(args.resend_mixed_batch),
        "dependency_missing_is_retryable": True,
        "random_android_ids_supported": True,
    }, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("Android partial-batch offline replay verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
