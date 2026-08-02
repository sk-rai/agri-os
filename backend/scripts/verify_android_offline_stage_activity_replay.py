#!/usr/bin/env python3
"""Read-only verifier for Android offline stage/activity replay on dynamic test cycle.

By default this validates the latest NURSERY activity for the Android-created
cycle, because Android-generated activity event/entity UUIDs are random during
Maestro/manual tests. Optional env vars can tighten the check:

    ANDROID_ACTIVITY_EVENT_ID={sync event id}
    ANDROID_ACTIVITY_ID={activity entity id}
"""

from __future__ import annotations

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
from app.modules.sync.models import SyncProcessedEvent, SyncConflict, AuditChainEntry

TENANT_ID = "android-dynamic-test"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"
STAGE_EVENT_ID = "93a6424d-ac6e-4524-9bff-6bc7573e607e"
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
EXPECTED_COST_TEXT = "325.50"
ACTIVITY_EVENT_ID = os.getenv("ANDROID_ACTIVITY_EVENT_ID")
ACTIVITY_ID = os.getenv("ANDROID_ACTIVITY_ID")
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
        print("     ", json.dumps(detail, sort_keys=True, default=str)[:900] if isinstance(detail, (dict, list)) else detail)


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
            AuditChainEntry.correlation_id == parsed,
            AuditChainEntry.action == "SYNC_FAILED",
        ).all()
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
                for row in failures
            ],
        }
    finally:
        db.close()


def main() -> int:
    print("=" * 72)
    print("ANDROID OFFLINE STAGE/ACTIVITY REPLAY VERIFIER")
    print("=" * 72)

    stage_event = sync_event_status(STAGE_EVENT_ID)
    check(stage_event and (stage_event.get("event") or {}).get("status") == "COMMITTED", "Stage START sync event is committed", stage_event)
    check(not stage_event.get("conflicts"), "Stage START sync event has no conflicts", stage_event)
    check(not stage_event.get("failed_audit_entries"), "Stage START sync event has no failed audit entries", stage_event)

    if ACTIVITY_EVENT_ID:
        activity_event = sync_event_status(ACTIVITY_EVENT_ID)
        check(activity_event and (activity_event.get("event") or {}).get("status") == "COMMITTED", "Activity sync event is committed", activity_event)
        check((activity_event.get("event") or {}).get("entity_type") == "crop_activity", "Activity sync event type is crop_activity", activity_event)
        check(not activity_event.get("conflicts"), "Activity sync event has no conflicts", activity_event)
        check(not activity_event.get("failed_audit_entries"), "Activity sync event has no failed audit entries", activity_event)

    cycle_response, cycle = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}")
    check(cycle_response.status_code == 200, "Crop cycle fetch returns 200", cycle_response.text[:900])
    check(cycle.get("id") == CYCLE_ID, "Crop cycle id matches", cycle.get("id"))
    check(cycle.get("status") == "ACTIVE", "Crop cycle is ACTIVE after stage replay", cycle)
    check(cycle.get("inferred_current_stage") == EXPECTED_STAGE_CODE, "Current stage is NURSERY", cycle)
    nursery = next((stage for stage in cycle.get("stages") or [] if stage.get("code") == EXPECTED_STAGE_CODE), None)
    check(bool(nursery), "NURSERY stage exists", cycle.get("stages"))
    check(nursery.get("status") == "ACTIVE", "NURSERY stage is ACTIVE", nursery)

    activity_response, activities = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/activities")
    check(activity_response.status_code == 200, "Activity list returns 200", activity_response.text[:900])
    nursery_activities = [row for row in activities if row.get("stage_code") == EXPECTED_STAGE_CODE]
    check(bool(nursery_activities), "At least one NURSERY activity exists", activities)
    if ACTIVITY_ID:
        activity = next((row for row in nursery_activities if row.get("id") == ACTIVITY_ID), None)
        check(bool(activity), "Expected Android activity id is present", nursery_activities)
    else:
        activity = sorted(nursery_activities, key=lambda row: str(row.get("activity_date") or ""), reverse=True)[0]
        print("INFO using latest NURSERY activity", json.dumps(activity, sort_keys=True, default=str))
    check(activity.get("stage_code") == EXPECTED_STAGE_CODE, "Activity is linked to NURSERY", activity)
    check(money(activity.get("cost_amount")) == EXPECTED_COST, "Activity cost is 325.50", activity)

    stage_summary_response, stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
    check(stage_summary_response.status_code == 200, "Stage-cost summary returns 200", stage_summary_response.text[:900])
    totals = stage_summary.get("totals") or {}
    check(int(totals.get("activity_count") or 0) >= 1, "Stage-cost summary activity_count includes replayed activity", totals)
    check(money(totals.get("actual_expense")) >= EXPECTED_COST, "Stage-cost summary actual_expense includes 325.50", totals)

    pnl_response, pnl = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
    check(pnl_response.status_code == 200, "P&L summary returns 200", pnl_response.text[:900])
    pnl_totals = pnl.get("totals") or {}
    check(money(pnl_totals.get("total_expenses")) >= EXPECTED_COST, "P&L total_expenses includes 325.50", pnl_totals)

    print("=" * 72)
    print("Android offline stage/activity replay verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
