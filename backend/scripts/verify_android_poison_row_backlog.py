"""Verify Android large backlog with one WORKFLOW_INVALID poison row.

Flow 29 validates that one non-accepted row in a larger 25-row backlog does not
stop queue traversal:

- rows 1..9 are valid crop_activity CREATE events;
- row 10 is a crop_stage START against already ACTIVE NURSERY and should return
  WORKFLOW_INVALID in conflicts[];
- rows 11..25 are valid crop_activity CREATE events.

The expected final durable state is 24 committed activities, one durable pending
workflow conflict, no failed audit rows, and finance impact of 24 x INR 20.00.
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
from app.modules.workflow.models import CropActivity, CropStageInstance


TENANT_ID = "android-dynamic-test"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
DEFAULT_COUNT = 25
POISON_INDEX = 10
DEFAULT_AMOUNT = Decimal("20.00")
SOURCE = "android_maestro_poison_row_backlog_test"
NOTE_PREFIX = "Poison backlog valid activity"
BASELINE_PATH = Path("/tmp/android_poison_row_backlog_baseline.json")
MANIFEST_PATH = Path("/tmp/android_poison_row_backlog_sample_events.json")

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


def valid_indices(count: int) -> list[int]:
    return [index for index in range(1, count + 1) if index != POISON_INDEX]


def expected_notes(count: int) -> list[str]:
    return [note_for_index(index) for index in valid_indices(count)]


def load_json(path: Path) -> dict:
    check(path.exists(), f"JSON file exists: {path}")
    return json.loads(path.read_text())


def events_from_manifest(path: Path) -> list[dict]:
    payload = load_json(path)
    events = payload.get("events") or []
    check(bool(events), "Manifest contains events[]", payload)
    return events


def expected_batch_outcome(events: list[dict], start: int, batch: list[dict]) -> tuple[list[str], list[str]]:
    accepted = []
    conflicts = []
    for offset, event in enumerate(batch, start=start + 1):
        if offset == POISON_INDEX:
            conflicts.append(str(event["event_id"]))
        else:
            accepted.append(str(event["event_id"]))
    return accepted, conflicts


def post_batches(events: list[dict], batch_size: int) -> list[dict]:
    responses = []
    for start in range(0, len(events), batch_size):
        batch = events[start:start + batch_size]
        response = client.post("/api/v1/sync/events", json={"events": batch}, headers=HEADERS)
        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text}
        batch_number = start // batch_size + 1
        accepted_ids, conflict_ids = expected_batch_outcome(events, start, batch)
        check(response.status_code == 200, f"Batch {batch_number} returns HTTP 200", payload)
        check(payload.get("accepted") == accepted_ids, f"Batch {batch_number} accepted IDs match", payload)
        check(payload.get("failed") == [], f"Batch {batch_number} failed empty", payload)
        conflicts = payload.get("conflicts") or []
        check(len(conflicts) == len(conflict_ids), f"Batch {batch_number} conflict count matches", payload)
        if conflict_ids:
            conflict = conflicts[0]
            check(conflict.get("event_id") == conflict_ids[0], f"Batch {batch_number} conflict event_id matches poison row", conflict)
            check(conflict.get("conflict_type") == "WORKFLOW_INVALID", f"Batch {batch_number} conflict_type is WORKFLOW_INVALID", conflict)
            check(conflict.get("resolution_strategy") == "SERVER_AUTHORITY", f"Batch {batch_number} resolution strategy is SERVER_AUTHORITY", conflict)
        check(payload.get("total_processed") == len(batch), f"Batch {batch_number} total_processed", payload)
        responses.append(payload)
    return responses


def audit_rows_for_source(db) -> list[AuditChainEntry]:
    rows = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
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


def infer_event_ids_from_audit(db, expected_indices: set[int]) -> dict[int, str]:
    inferred: dict[int, str] = {}
    for row in audit_rows_for_source(db):
        metadata = row.metadata_ or {}
        index = metadata.get("poison_backlog_index")
        event_id = metadata.get("sync_event_id") or str(row.correlation_id)
        if index is None or not event_id:
            continue
        try:
            index_int = int(index)
        except (TypeError, ValueError):
            continue
        if index_int in expected_indices:
            inferred[index_int] = str(event_id)
    return inferred


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--events-json", default=str(MANIFEST_PATH), help="Optional manifest containing exact events[].")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--amount", default=None)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--send-sample", action="store_true", help="POST sample manifest in bounded batches.")
    parser.add_argument("--resend-sample", action="store_true", help="POST sample manifest again and assert idempotency/no duplicate finance.")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID POISON ROW BACKLOG VERIFIER")
    print("=" * 72)

    baseline = load_json(Path(args.baseline_path))
    count = args.count or int(baseline.get("expected_count") or DEFAULT_COUNT)
    amount = money(args.amount or baseline.get("amount_per_activity") or DEFAULT_AMOUNT)
    valid_count = count - 1
    expected_delta = amount * valid_count
    baseline_count = int(baseline.get("activity_count") or 0)
    baseline_stage_expense = money(baseline.get("stage_summary_actual_expense"))
    baseline_pnl_expense = money(baseline.get("pnl_total_expenses"))
    valid_index_set = set(valid_indices(count))
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
        check(len(activities) == valid_count, "Exactly 24 valid crop_activities materialized", [
            {"id": str(row.id), "notes": row.notes, "cost_amount": str(row.cost_amount)}
            for row in activities[:10]
        ])
        activity_ids = [str(row.id) for row in activities]
        check(len(set(activity_ids)) == valid_count, "No duplicate valid activity IDs", activity_ids)
        check(all(money(row.cost_amount) == amount for row in activities), "Every valid activity has expected amount", [
            {"id": str(row.id), "cost_amount": str(row.cost_amount)} for row in activities[:10]
        ])
        check(all(row.is_active for row in activities), "Every valid activity is active")
        check({row.notes for row in activities} == expected_note_set, "Valid activity notes match all non-poison indices", sorted(expected_note_set)[:10])

        manifest_event_ids_by_index = {index: str(event["event_id"]) for index, event in enumerate(exact_events, start=1)}
        manifest_entity_ids_by_index = {index: str(event["entity_id"]) for index, event in enumerate(exact_events, start=1)}
        manifest_activity_event_ids = {manifest_event_ids_by_index[index] for index in valid_index_set if index in manifest_event_ids_by_index}
        manifest_activity_entity_ids = {manifest_entity_ids_by_index[index] for index in valid_index_set if index in manifest_entity_ids_by_index}
        poison_event_id = manifest_event_ids_by_index.get(POISON_INDEX) or (baseline.get("expected_conflict") or {}).get("event_id")
        poison_entity_id = manifest_entity_ids_by_index.get(POISON_INDEX) or (baseline.get("expected_conflict") or {}).get("entity_id")

        inferred_by_index = infer_event_ids_from_audit(db, valid_index_set)
        inferred_event_ids = set(inferred_by_index.values())
        activity_event_ids = manifest_activity_event_ids or inferred_event_ids
        check(len(activity_event_ids) == valid_count, "Verifier has 24 valid activity event IDs via manifest or audit inference", {
            "manifest_event_ids": len(manifest_activity_event_ids),
            "inferred_event_ids": len(inferred_event_ids),
            "expected_valid_count": valid_count,
        })

        processed_activity_rows = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id.in_([UUID(event_id) for event_id in activity_event_ids]),
        ).all()
        check(len(processed_activity_rows) == valid_count, "All 24 activity sync_processed_events rows exist", [
            {"event_id": str(row.event_id), "status": row.status, "entity_id": str(row.entity_id)}
            for row in processed_activity_rows[:10]
        ])
        check(all(row.status == "COMMITTED" for row in processed_activity_rows), "All 24 activity processed events are COMMITTED", [
            {"event_id": str(row.event_id), "status": row.status} for row in processed_activity_rows[:10]
        ])
        check(all(row.entity_type == "crop_activity" for row in processed_activity_rows), "All valid processed events are crop_activity")

        if manifest_activity_entity_ids:
            processed_entity_ids = {str(row.entity_id) for row in processed_activity_rows}
            check(processed_entity_ids == manifest_activity_entity_ids, "Processed activity entity IDs match manifest", {
                "processed": sorted(processed_entity_ids)[:10],
                "manifest": sorted(manifest_activity_entity_ids)[:10],
            })
            check(set(activity_ids) == manifest_activity_entity_ids, "Materialized activity IDs match manifest activity entity IDs", sorted(activity_ids)[:10])

        check(bool(poison_event_id), "Poison event ID available", poison_event_id)
        poison_processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == UUID(poison_event_id),
        ).first()
        check(poison_processed is not None, "Poison stage processed event exists", {"event_id": poison_event_id})
        check(poison_processed.status == "CONFLICT", "Poison stage processed event status is CONFLICT", poison_processed.status)
        check(poison_processed.entity_type == "crop_stage", "Poison processed event entity_type is crop_stage", poison_processed.entity_type)

        conflict = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id == UUID(poison_event_id),
        ).order_by(SyncConflict.created_at.desc()).first()
        check(conflict is not None, "Durable sync_conflicts row exists for poison row", {"event_id": poison_event_id})
        check(conflict.conflict_type == "WORKFLOW_INVALID", "Poison conflict_type is WORKFLOW_INVALID", conflict.conflict_type)
        check(conflict.resolution_strategy == "SERVER_AUTHORITY", "Poison resolution_strategy is SERVER_AUTHORITY", conflict.resolution_strategy)
        check(conflict.status == "PENDING_REVIEW", "Poison conflict remains PENDING_REVIEW", conflict.status)

        if poison_entity_id:
            poison_stage_rows = db.query(CropStageInstance).filter(
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.id == UUID(poison_entity_id),
            ).all()
            check(not poison_stage_rows, "Poison entity_id did not materialize as server stage row", [
                {"id": str(row.id), "stage_code": row.stage_code, "status": row.status}
                for row in poison_stage_rows
            ])

        all_event_ids = set(activity_event_ids)
        if poison_event_id:
            all_event_ids.add(poison_event_id)
        conflicts_for_valid = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id.in_([UUID(event_id) for event_id in activity_event_ids]),
        ).all()
        check(not conflicts_for_valid, "No sync_conflicts rows for valid activity events", [
            {"event_id": str(row.event_id), "conflict_type": row.conflict_type, "status": row.status}
            for row in conflicts_for_valid
        ])
        failures = failed_audit_rows_for_events(db, all_event_ids)
        check(not failures, "No SYNC_FAILED audit rows for poison backlog events", [
            {"id": row.id, "metadata": row.metadata_} for row in failures
        ])
    finally:
        db.close()

    activity_response, activity_payload = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    api_indexed = [row for row in activity_payload if row.get("notes") in expected_note_set]
    check(len(api_indexed) == valid_count, "Activity API exposes exactly 24 valid indexed rows", api_indexed[:10])

    current_nursery_count = len([row for row in activity_payload if row.get("stage_code") == EXPECTED_STAGE_CODE])
    check(current_nursery_count == baseline_count + valid_count, "NURSERY activity count increased by 24", {
        "baseline_count": baseline_count,
        "current_nursery_count": current_nursery_count,
        "expected_valid_count": valid_count,
    })

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    current_stage_expense = money((stage_summary.get("totals") or {}).get("actual_expense"))
    check(current_stage_expense == baseline_stage_expense + expected_delta, "Stage-cost actual_expense increased by 24 x amount", {
        "baseline_actual_expense": str(baseline_stage_expense),
        "current_actual_expense": str(current_stage_expense),
        "expected_delta": str(expected_delta),
    })

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    current_pnl_expense = money((pnl.get("totals") or {}).get("total_expenses"))
    check(current_pnl_expense == baseline_pnl_expense + expected_delta, "P&L total_expenses increased by 24 x amount", {
        "baseline_total_expenses": str(baseline_pnl_expense),
        "current_total_expenses": str(current_pnl_expense),
        "expected_delta": str(expected_delta),
    })

    pending_response, pending = get_json("/api/v1/sync/conflicts/pending?limit=100")
    check(pending_response.status_code == 200, "Android pending conflicts endpoint returns 200", pending_response.text[:1000])
    pending_conflicts = pending.get("conflicts") or []
    pending_match = next((row for row in pending_conflicts if row.get("event_id") == poison_event_id), None)
    check(pending_match is not None, "Pending conflicts endpoint exposes poison WORKFLOW_INVALID row", pending)
    check(pending_match.get("conflict_type") == "WORKFLOW_INVALID", "Pending conflict type is WORKFLOW_INVALID", pending_match)
    check(pending_match.get("android_action") == "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE", "Pending conflict android_action is workflow server-authority", pending_match)

    print(json.dumps({
        "schema_version": "android_poison_row_backlog_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": CYCLE_ID,
        "stage_code": EXPECTED_STAGE_CODE,
        "count": count,
        "valid_activity_count": valid_count,
        "poison_index": POISON_INDEX,
        "amount_per_activity": str(amount),
        "expected_finance_delta": str(expected_delta),
        "send_sample_performed": args.send_sample,
        "resend_sample_performed": args.resend_sample,
        "batch_size": args.batch_size,
        "random_android_ids_supported": True,
        "id_inference": "exact manifest if present, otherwise SYNC_COMMIT audit metadata source/index for activity rows",
        "expected_android_behavior": {
            "valid_rows_marked_synced": True,
            "poison_row_routed_to_workflow_conflict_ui": True,
            "later_batches_continue_after_poison_row": True,
            "farmer_ui": "workflow intervention only; no raw queue internals",
        },
    }, indent=2, sort_keys=True))
    print("=" * 72)
    print("Android poison row backlog verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
