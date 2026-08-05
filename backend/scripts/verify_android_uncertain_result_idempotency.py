"""Verify Android uncertain-result offline sync idempotency.

Use after Android sends a crop_activity CREATE and then retries the same local
queue row with the exact same event_id/entity_id/payload.

Required identifiers may be supplied as CLI args or env vars:

    ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID={android event UUID}
    ANDROID_UNCERTAIN_ACTIVITY_ID={android activity/entity UUID}

Optional --resend posts the same event once more through /api/v1/sync/events and
asserts the current backend response shape: accepted contains the same event_id,
conflicts=[], failed=[].
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
from app.modules.workflow.models import CropActivity


TENANT_ID = "android-dynamic-test"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_uncertain_result_idempotency_baseline.json")
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


def activity_payload(activity_id: str) -> dict:
    return {
        "crop_cycle_id": CYCLE_ID,
        "stage_code": EXPECTED_STAGE_CODE,
        "activity_date": date(2026, 8, 2).isoformat(),
        "activity_type": "FERTILIZER",
        "input_code": "DAP_18_46_0",
        "input_name": "DAP 18-46-0",
        "quantity": 1,
        "quantity_unit": "KG",
        "cost_amount": float(EXPECTED_COST),
        "currency": "INR",
        "notes": "Uncertain-result idempotency retry test",
        "id": activity_id,
    }


def sync_request(event_id: str, activity_id: str) -> dict:
    return {
        "events": [
            {
                "event_id": event_id,
                "entity_type": "crop_activity",
                "entity_id": activity_id,
                "operation": "CREATE",
                "version": 1,
                "dependency_ids": [],
                "payload": activity_payload(activity_id),
                "metadata": {
                    "source": "android_maestro_uncertain_result_idempotency_test",
                },
            }
        ]
    }


def failed_audit_entries(db: SessionLocal, event_id: UUID) -> list[AuditChainEntry]:
    failures = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.entity_type == "crop_activity",
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in failures
        if (row.metadata_ or {}).get("sync_event_id") == str(event_id)
        or str(row.correlation_id) == str(event_id)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--event-id", default=os.getenv("ANDROID_UNCERTAIN_ACTIVITY_EVENT_ID"))
    parser.add_argument("--activity-id", default=os.getenv("ANDROID_UNCERTAIN_ACTIVITY_ID"))
    parser.add_argument("--resend", action="store_true", help="POST the same event again and assert idempotent response shape.")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID UNCERTAIN-RESULT IDEMPOTENCY VERIFIER")
    print("=" * 72)

    check(bool(args.event_id), "event_id supplied")
    check(bool(args.activity_id), "activity/entity_id supplied")
    event_id = UUID(str(args.event_id))
    activity_id = UUID(str(args.activity_id))

    baseline = load_baseline(Path(args.baseline_path))
    check(baseline.get("cycle_id") == CYCLE_ID, "Baseline cycle id matches", baseline)
    baseline_count = int(baseline.get("activity_count") or 0)
    baseline_stage_expense = money(baseline.get("stage_summary_actual_expense"))
    baseline_pnl_expense = money(baseline.get("pnl_total_expenses"))

    if args.resend:
        response = client.post("/api/v1/sync/events", json=sync_request(str(event_id), str(activity_id)), headers=HEADERS)
        payload = response.json()
        check(response.status_code == 200, "Duplicate same-event resend returns 200", payload)
        check(payload.get("accepted") == [str(event_id)], "Duplicate same-event response accepted list contains same event_id", payload)
        check(payload.get("conflicts") == [], "Duplicate same-event response has no conflicts", payload)
        check(payload.get("failed") == [], "Duplicate same-event response has no failed rows", payload)

    db = SessionLocal()
    try:
        processed_rows = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == event_id,
        ).all()
        check(len(processed_rows) == 1, "Exactly one sync_processed_events row exists for event_id", [
            {
                "event_id": str(row.event_id),
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "status": row.status,
                "processed_at": row.processed_at.isoformat() if row.processed_at else None,
            }
            for row in processed_rows
        ])
        processed = processed_rows[0]
        check(processed.status == "COMMITTED", "sync_processed_events status is COMMITTED", processed.status)
        check(processed.entity_type == "crop_activity", "processed event entity_type is crop_activity", processed.entity_type)
        check(str(processed.entity_id) == str(activity_id), "processed event entity_id matches activity id", str(processed.entity_id))

        activity_rows = db.query(CropActivity).filter(
            CropActivity.tenant_id == TENANT_ID,
            CropActivity.id == activity_id,
        ).all()
        check(len(activity_rows) == 1, "Exactly one crop_activities row exists for activity/entity_id", [
            {
                "id": str(row.id),
                "crop_cycle_id": str(row.crop_cycle_id),
                "stage_instance_id": str(row.stage_instance_id) if row.stage_instance_id else None,
                "cost_amount": str(row.cost_amount),
                "activity_date": row.activity_date.isoformat() if row.activity_date else None,
            }
            for row in activity_rows
        ])
        activity = activity_rows[0]
        check(str(activity.crop_cycle_id) == CYCLE_ID, "Activity belongs to expected cycle", str(activity.crop_cycle_id))
        check(money(activity.cost_amount) == EXPECTED_COST, "Activity cost is 325.50", str(activity.cost_amount))

        cycle_activity_count = db.query(CropActivity).filter(
            CropActivity.tenant_id == TENANT_ID,
            CropActivity.crop_cycle_id == UUID(CYCLE_ID),
        ).count()

        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id == event_id,
        ).all()
        check(not conflicts, "No sync_conflicts row exists for idempotent event", [
            {"id": str(row.id), "conflict_type": row.conflict_type, "status": row.status}
            for row in conflicts
        ])
        failures = failed_audit_entries(db, event_id)
        check(not failures, "No SYNC_FAILED audit row exists for idempotent event", [
            {"id": row.id, "metadata": row.metadata_}
            for row in failures
        ])
    finally:
        db.close()

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    matching_activity_rows = [row for row in activities if row.get("id") == str(activity_id)]
    check(len(matching_activity_rows) == 1, "Activity API exposes exactly one matching activity", matching_activity_rows)
    check(matching_activity_rows[0].get("stage_code") == EXPECTED_STAGE_CODE, "Activity API links activity to NURSERY", matching_activity_rows[0])

    current_nursery_count = len([row for row in activities if row.get("stage_code") == EXPECTED_STAGE_CODE])
    check(current_nursery_count == baseline_count + 1, "NURSERY activity count increased by exactly one", {
        "baseline_count": baseline_count,
        "current_nursery_count": current_nursery_count,
    })

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    stage_totals = stage_summary.get("totals") or {}
    current_stage_expense = money(stage_totals.get("actual_expense"))
    check(current_stage_expense == baseline_stage_expense + EXPECTED_COST, "Stage-cost actual_expense increased by exactly 325.50", {
        "baseline_actual_expense": str(baseline_stage_expense),
        "current_actual_expense": str(current_stage_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    pnl_totals = pnl.get("totals") or {}
    current_pnl_expense = money(pnl_totals.get("total_expenses"))
    check(current_pnl_expense == baseline_pnl_expense + EXPECTED_COST, "P&L total_expenses increased by exactly 325.50", {
        "baseline_total_expenses": str(baseline_pnl_expense),
        "current_total_expenses": str(current_pnl_expense),
        "expected_delta": str(EXPECTED_COST),
    })

    print(json.dumps({
        "schema_version": "android_uncertain_result_idempotency_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": CYCLE_ID,
        "event_id": str(event_id),
        "activity_id": str(activity_id),
        "baseline_activity_count": baseline_count,
        "current_nursery_activity_count": current_nursery_count,
        "db_cycle_activity_count": cycle_activity_count,
        "duplicate_resend_performed": bool(args.resend),
        "expected_duplicate_response_shape": {
            "accepted": [str(event_id)],
            "conflicts": [],
            "failed": [],
            "total_processed": 1,
        },
        "random_android_ids_supported": True,
    }, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("Android uncertain-result idempotency verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
