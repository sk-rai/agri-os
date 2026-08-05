"""Verify Android sync queue pagination/backpressure replay.

Flow 27 validates that N offline crop_activity CREATE events replay in bounded
batches and materialize exactly once with exact finance impact.

The verifier supports two modes:
- exact IDs from a manifest JSON containing events[];
- inference by stable notes/source/index when Android generated random IDs.
"""

from __future__ import annotations

import argparse
import json
import sys
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
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
DEFAULT_COUNT = 25
DEFAULT_AMOUNT = Decimal("20.00")
SOURCE = "android_maestro_queue_backpressure_test"
NOTE_PREFIX = "Queue backpressure activity"
BASELINE_PATH = Path("/tmp/android_queue_backpressure_baseline.json")
MANIFEST_PATH = Path("/tmp/android_queue_backpressure_sample_events.json")

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


def note_for_index(index: int) -> str:
    return f"{NOTE_PREFIX} {index:02d} source={SOURCE}"


def load_json(path: Path) -> dict:
    check(path.exists(), f"JSON file exists: {path}")
    return json.loads(path.read_text())


def expected_notes(count: int) -> list[str]:
    return [note_for_index(index) for index in range(1, count + 1)]


def events_from_manifest(path: Path) -> list[dict]:
    payload = load_json(path)
    events = payload.get("events") or []
    check(bool(events), "Manifest contains events[]", payload)
    return events


def post_batches(events: list[dict], batch_size: int) -> list[dict]:
    responses = []
    for start in range(0, len(events), batch_size):
        batch = events[start:start + batch_size]
        response = client.post("/api/v1/sync/events", json={"events": batch}, headers=HEADERS)
        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text}
        check(response.status_code == 200, f"Batch {start // batch_size + 1} returns HTTP 200", payload)
        expected_ids = [str(event["event_id"]) for event in batch]
        check(payload.get("accepted") == expected_ids, f"Batch {start // batch_size + 1} accepted IDs match", payload)
        check(payload.get("conflicts") == [], f"Batch {start // batch_size + 1} conflicts empty", payload)
        check(payload.get("failed") == [], f"Batch {start // batch_size + 1} failed empty", payload)
        check(payload.get("total_processed") == len(batch), f"Batch {start // batch_size + 1} total_processed", payload)
        responses.append(payload)
    return responses


def audit_rows_for_source(db) -> list[AuditChainEntry]:
    rows = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.entity_type == "crop_activity",
        AuditChainEntry.action == "SYNC_COMMIT",
    ).all()
    return [row for row in rows if (row.metadata_ or {}).get("source") == SOURCE]


def failed_audit_rows_for_events(db, event_ids: set[str]) -> list[AuditChainEntry]:
    rows = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in rows
        if str(row.correlation_id) in event_ids
        or str((row.metadata_ or {}).get("sync_event_id")) in event_ids
    ]


def infer_event_ids_from_audit(db, count: int) -> dict[int, str]:
    inferred: dict[int, str] = {}
    for row in audit_rows_for_source(db):
        metadata = row.metadata_ or {}
        index = metadata.get("queue_backpressure_index")
        event_id = metadata.get("sync_event_id") or str(row.correlation_id)
        if index is None or not event_id:
            continue
        try:
            index_int = int(index)
        except (TypeError, ValueError):
            continue
        if 1 <= index_int <= count:
            inferred[index_int] = str(event_id)
    return inferred


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--events-json", default=str(MANIFEST_PATH), help="Optional manifest containing exact events[].")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--amount", default=None)
    parser.add_argument("--send-sample", action="store_true", help="POST sample manifest events in bounded batches.")
    parser.add_argument("--resend-sample", action="store_true", help="POST sample manifest again and assert idempotency/no finance duplicate.")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID QUEUE BACKPRESSURE VERIFIER")
    print("=" * 72)

    baseline = load_json(Path(args.baseline_path))
    count = args.count or int(baseline.get("expected_count") or DEFAULT_COUNT)
    amount = money(args.amount or baseline.get("amount_per_activity") or DEFAULT_AMOUNT)
    expected_delta = amount * count
    baseline_count = int(baseline.get("activity_count") or 0)
    baseline_stage_expense = money(baseline.get("stage_summary_actual_expense"))
    baseline_pnl_expense = money(baseline.get("pnl_total_expenses"))
    expected_note_set = set(expected_notes(count))

    exact_events: list[dict] = []
    events_path = Path(args.events_json)
    if events_path.exists():
        exact_events = events_from_manifest(events_path)
        check(len(exact_events) == count, "Manifest event count matches expected count", {"manifest_count": len(exact_events), "expected_count": count})

    if args.send_sample:
        check(bool(exact_events), "--send-sample requires events manifest")
        post_batches(exact_events, args.batch_size)

    if args.resend_sample:
        check(bool(exact_events), "--resend-sample requires events manifest")
        post_batches(exact_events, args.batch_size)

    db = SessionLocal()
    try:
        activities = db.query(CropActivity).filter(
            CropActivity.tenant_id == TENANT_ID,
            CropActivity.crop_cycle_id == UUID(CYCLE_ID),
            CropActivity.notes.in_(expected_note_set),
        ).all()
        check(len(activities) == count, "Exactly N indexed crop_activities materialized", [
            {"id": str(row.id), "notes": row.notes, "cost_amount": str(row.cost_amount)}
            for row in activities[:10]
        ])
        activity_ids = [str(row.id) for row in activities]
        check(len(set(activity_ids)) == count, "No duplicate activity IDs", activity_ids)
        check(all(money(row.cost_amount) == amount for row in activities), "Every indexed activity has expected amount", [
            {"id": str(row.id), "cost_amount": str(row.cost_amount)} for row in activities[:10]
        ])
        check(all(row.is_active for row in activities), "Every indexed activity is active")

        notes_seen = {row.notes for row in activities}
        check(notes_seen == expected_note_set, "All queue_backpressure_index notes present", sorted(notes_seen))

        manifest_event_ids = {str(event["event_id"]) for event in exact_events}
        manifest_entity_ids = {str(event["entity_id"]) for event in exact_events}
        inferred_by_index = infer_event_ids_from_audit(db, count)
        inferred_event_ids = set(inferred_by_index.values())
        event_ids = manifest_event_ids or inferred_event_ids
        check(len(event_ids) == count, "Verifier has exactly N event IDs via manifest or audit inference", {
            "manifest_event_ids": len(manifest_event_ids),
            "inferred_event_ids": len(inferred_event_ids),
            "expected_count": count,
        })

        processed_rows = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id.in_([UUID(event_id) for event_id in event_ids]),
        ).all()
        check(len(processed_rows) == count, "All N sync_processed_events rows exist", [
            {"event_id": str(row.event_id), "status": row.status, "entity_id": str(row.entity_id)}
            for row in processed_rows[:10]
        ])
        check(all(row.status == "COMMITTED" for row in processed_rows), "All N processed events are COMMITTED", [
            {"event_id": str(row.event_id), "status": row.status} for row in processed_rows[:10]
        ])
        check(all(row.entity_type == "crop_activity" for row in processed_rows), "All N processed events are crop_activity")

        if manifest_entity_ids:
            processed_entity_ids = {str(row.entity_id) for row in processed_rows}
            check(processed_entity_ids == manifest_entity_ids, "Processed entity IDs match manifest entity IDs", {
                "processed": sorted(processed_entity_ids)[:10],
                "manifest": sorted(manifest_entity_ids)[:10],
            })
            check(set(activity_ids) == manifest_entity_ids, "Materialized activity IDs match manifest entity IDs", sorted(activity_ids)[:10])

        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id.in_([UUID(event_id) for event_id in event_ids]),
        ).all()
        check(not conflicts, "No sync_conflicts rows for queue backpressure events", [
            {"event_id": str(row.event_id), "conflict_type": row.conflict_type, "status": row.status}
            for row in conflicts
        ])
        failures = failed_audit_rows_for_events(db, event_ids)
        check(not failures, "No SYNC_FAILED audit rows for queue backpressure events", [
            {"id": row.id, "metadata": row.metadata_} for row in failures
        ])
    finally:
        db.close()

    activity_response, activity_payload = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    api_indexed = [row for row in activity_payload if row.get("notes") in expected_note_set]
    check(len(api_indexed) == count, "Activity API exposes exactly N indexed rows", api_indexed[:10])

    current_nursery_count = len([row for row in activity_payload if row.get("stage_code") == EXPECTED_STAGE_CODE])
    check(current_nursery_count == baseline_count + count, "NURSERY activity count increased by N", {
        "baseline_count": baseline_count,
        "current_nursery_count": current_nursery_count,
        "expected_count": count,
    })

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    current_stage_expense = money((stage_summary.get("totals") or {}).get("actual_expense"))
    check(current_stage_expense == baseline_stage_expense + expected_delta, "Stage-cost actual_expense increased by N x amount", {
        "baseline_actual_expense": str(baseline_stage_expense),
        "current_actual_expense": str(current_stage_expense),
        "expected_delta": str(expected_delta),
    })

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    current_pnl_expense = money((pnl.get("totals") or {}).get("total_expenses"))
    check(current_pnl_expense == baseline_pnl_expense + expected_delta, "P&L total_expenses increased by N x amount", {
        "baseline_total_expenses": str(baseline_pnl_expense),
        "current_total_expenses": str(current_pnl_expense),
        "expected_delta": str(expected_delta),
    })

    print(json.dumps({
        "schema_version": "android_queue_backpressure_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": CYCLE_ID,
        "stage_code": EXPECTED_STAGE_CODE,
        "count": count,
        "amount_per_activity": str(amount),
        "expected_finance_delta": str(expected_delta),
        "send_sample_performed": args.send_sample,
        "resend_sample_performed": args.resend_sample,
        "batch_size": args.batch_size,
        "random_android_ids_supported": True,
        "id_inference": "exact manifest if present, otherwise SYNC_COMMIT audit metadata source/index",
        "expected_android_behavior": {
            "bounded_batches": True,
            "accepted_rows_marked_synced_per_batch": True,
            "reuse_same_ids_on_uncertain_retry": True,
            "farmer_ui": "quiet progress only unless failures/conflicts occur",
        },
    }, indent=2, sort_keys=True))
    print("=" * 72)
    print("Android queue backpressure verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())