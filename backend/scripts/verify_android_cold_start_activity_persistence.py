"""Verify Android offline sync queue persists across app cold start/relaunch.

Verifier accepts random Android event/activity UUIDs:

    ANDROID_COLD_START_ACTIVITY_EVENT_ID={optional sync event UUID}
    ANDROID_COLD_START_ACTIVITY_ID={optional activity entity UUID}

If no UUIDs are supplied, it uses the /tmp baseline from the prepare script and
verifies a new NURSERY activity with cost 325.50 was materialized after baseline.
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

from app.main import app
from app.core.database import SessionLocal
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent
from app.modules.workflow.models import CropActivity


TENANT_ID = "android-dynamic-test"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_cold_start_activity_persistence_baseline.json")
HEADERS = {"X-Tenant-ID": TENANT_ID}

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


def money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def get_json(path: str):
    response = client.get(path, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response, payload


def load_baseline(path: Path) -> dict:
    check(path.exists(), "Baseline file exists", str(path))
    return json.loads(path.read_text())


def sync_event_status(event_id: str | None):
    if not event_id:
        return None
    db = SessionLocal()
    try:
        parsed = UUID(str(event_id))
        event = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID,
            SyncProcessedEvent.event_id == parsed,
        ).first()
        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == TENANT_ID,
            SyncConflict.event_id == parsed,
        ).all()
        failures = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == TENANT_ID,
            AuditChainEntry.entity_type == "crop_activity",
            AuditChainEntry.action == "SYNC_FAILED",
        ).all()
        matching_failures = [
            row for row in failures
            if (row.metadata_ or {}).get("sync_event_id") == str(event_id)
            or str(row.correlation_id) == str(event_id)
        ]
        return {
            "event": None if not event else {
                "event_id": str(event.event_id),
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id) if event.entity_id else None,
                "operation": event.operation,
                "status": event.status,
                "server_version": event.server_version,
                "processed_at": event.processed_at.isoformat() if event.processed_at else None,
            },
            "conflicts": [
                {
                    "id": str(row.id),
                    "conflict_type": row.conflict_type,
                    "resolution_strategy": row.resolution_strategy,
                    "status": row.status,
                }
                for row in conflicts
            ],
            "failed_audit_entries": [
                {
                    "id": row.id,
                    "action": row.action,
                    "metadata": row.metadata_,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in matching_failures
            ],
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-path", default=str(BASELINE_PATH))
    parser.add_argument("--event-id", default=os.getenv("ANDROID_COLD_START_ACTIVITY_EVENT_ID"))
    parser.add_argument("--activity-id", default=os.getenv("ANDROID_COLD_START_ACTIVITY_ID"))
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID COLD-START OFFLINE ACTIVITY PERSISTENCE VERIFIER")
    print("=" * 72)

    baseline = load_baseline(Path(args.baseline_path))
    check(baseline.get("cycle_id") == CYCLE_ID, "Baseline cycle id matches", baseline)
    baseline_count = int(baseline.get("activity_count") or 0)

    if args.event_id:
        activity_event = sync_event_status(args.event_id)
        check(activity_event and (activity_event.get("event") or {}).get("status") == "COMMITTED", "Activity sync event is committed", activity_event)
        check((activity_event.get("event") or {}).get("entity_type") == "crop_activity", "Activity sync event type is crop_activity", activity_event)
        check(not activity_event.get("conflicts"), "Activity sync event has no conflicts", activity_event)
        check(not activity_event.get("failed_audit_entries"), "Activity sync event has no failed audit entries", activity_event)

    cycle_response, cycle = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}")
    check(cycle_response.status_code == 200, "Crop cycle fetch returns 200", cycle_response.text[:1000])
    check(cycle.get("status") == "ACTIVE", "Crop cycle remains ACTIVE", cycle)
    nursery = next((stage for stage in cycle.get("stages") or [] if stage.get("code") == EXPECTED_STAGE_CODE), None)
    check(bool(nursery), "NURSERY stage exists", cycle.get("stages"))
    check(nursery.get("status") == "ACTIVE", "NURSERY stage remains ACTIVE", nursery)

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:1000])
    nursery_activities = [row for row in activities if row.get("stage_code") == EXPECTED_STAGE_CODE]
    check(len(nursery_activities) > baseline_count, "NURSERY activity count increased after cold-start replay", {
        "baseline_count": baseline_count,
        "current_count": len(nursery_activities),
    })

    if args.activity_id:
        activity = next((row for row in nursery_activities if row.get("id") == args.activity_id), None)
        check(bool(activity), "Expected Android activity id is present", nursery_activities)
    else:
        baseline_latest = str(baseline.get("latest_activity_created_at") or "")
        candidates = [
            row for row in nursery_activities
            if money(row.get("cost_amount")) == EXPECTED_COST
            and str(row.get("created_at") or row.get("activity_date") or "") >= baseline_latest[:10]
        ]
        activity = sorted(candidates or nursery_activities, key=lambda row: str(row.get("created_at") or row.get("activity_date") or ""), reverse=True)[0]
        print("INFO using latest matching/random Android activity", json.dumps(activity, sort_keys=True, default=str))

    check(activity.get("stage_code") == EXPECTED_STAGE_CODE, "Activity is linked to NURSERY", activity)
    check(money(activity.get("cost_amount")) == EXPECTED_COST, "Activity cost is 325.50", activity)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:1000])
    totals = stage_summary.get("totals") or {}
    check(money(totals.get("actual_expense")) >= EXPECTED_COST, "Stage-cost summary actual_expense includes cold-start activity", totals)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:1000])
    pnl_totals = pnl.get("totals") or {}
    check(money(pnl_totals.get("total_expenses")) >= EXPECTED_COST, "P&L total_expenses includes cold-start activity", pnl_totals)

    db = SessionLocal()
    try:
        db_count = db.query(CropActivity).filter(CropActivity.tenant_id == TENANT_ID, CropActivity.crop_cycle_id == UUID(CYCLE_ID)).count()
    finally:
        db.close()

    print(json.dumps({
        "schema_version": "android_cold_start_activity_persistence_verify.v1",
        "tenant_id": TENANT_ID,
        "cycle_id": CYCLE_ID,
        "baseline_activity_count": baseline_count,
        "current_activity_count": len(nursery_activities),
        "db_cycle_activity_count": db_count,
        "verified_activity": activity,
        "random_android_ids_supported": True,
        "exact_event_id_checked": bool(args.event_id),
        "exact_activity_id_checked": bool(args.activity_id),
    }, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("Android cold-start offline activity persistence verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
