"""Verify Android multi-conflict pending drawer ordering/dedup contract.

This verifier can either inspect conflicts created by Android, or POST the
canonical VERSION_MISMATCH + WORKFLOW_INVALID batch itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent


TENANT_ID = "android-dynamic-test"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}
BASELINE_PATH = Path("/tmp/android_multi_conflict_pending_drawer_baseline.json")

VERSION_EVENT_ID = "0f7e0a6b-8472-5d6d-8a14-a9d000000111"
VERSION_ACTIVITY_ID = "0f7e0a6b-8472-5d6d-8a14-a9d000000112"
WORKFLOW_EVENT_ID = "0f7e0a6b-8472-5d6d-8a14-a9d000000121"
WORKFLOW_ENTITY_ID = "0f7e0a6b-8472-5d6d-8a14-a9d000000122"
CYCLE_ID = "aa346148-468b-47de-9c86-47ad41aa1f11"

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


def version_mismatch_event() -> dict:
    return {
        "event_id": VERSION_EVENT_ID,
        "entity_type": "crop_activity",
        "entity_id": VERSION_ACTIVITY_ID,
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": CYCLE_ID,
            "stage_code": "NURSERY",
            "activity_date": "2026-08-02",
            "activity_type": "FERTILIZER",
            "input_code": "DAP_18_46_0",
            "description": "Android offline changed activity payload",
            "quantity": 1,
            "quantity_unit": "KG",
            "cost_amount": 325.5,
            "currency": "INR",
        },
        "metadata": {"source": "android_maestro_multi_conflict_pending_drawer_test"},
    }


def workflow_invalid_event() -> dict:
    return {
        "event_id": WORKFLOW_EVENT_ID,
        "entity_type": "crop_stage",
        "entity_id": WORKFLOW_ENTITY_ID,
        "operation": "UPDATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "crop_cycle_id": CYCLE_ID,
            "stage_code": "NURSERY",
            "action": "START",
            "actual_start_date": "2026-08-02",
        },
        "metadata": {"source": "android_maestro_multi_conflict_pending_drawer_test"},
    }


def conflict_batch() -> list[dict]:
    return [version_mismatch_event(), workflow_invalid_event()]


def post_sync(events: list[dict]) -> tuple[int, dict]:
    response = client.post("/api/v1/sync/events", json={"events": events}, headers=HEADERS)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response.status_code, payload


def get_pending() -> dict:
    response = client.get("/api/v1/sync/conflicts/pending?limit=100", headers={"X-Tenant-ID": TENANT_ID})
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    check(response.status_code == 200, "Pending conflicts endpoint returns 200", payload)
    return payload


def assert_batch_response(payload: dict) -> None:
    check(payload.get("accepted") == [], "Conflict batch accepted[] is empty", payload)
    check(payload.get("failed") == [], "Conflict batch failed[] is empty", payload)
    conflicts = payload.get("conflicts") or []
    check(len(conflicts) == 2, "Conflict batch returns exactly two conflicts", payload)
    by_event = {row.get("event_id"): row for row in conflicts}
    version = by_event.get(VERSION_EVENT_ID)
    workflow = by_event.get(WORKFLOW_EVENT_ID)
    check(version is not None, "VERSION_MISMATCH response row present", payload)
    check(workflow is not None, "WORKFLOW_INVALID response row present", payload)
    check(version.get("conflict_type") == "VERSION_MISMATCH", "Version response conflict_type", version)
    check(version.get("resolution_strategy") == "MANUAL_REVIEW", "Version response resolution_strategy", version)
    check(workflow.get("conflict_type") == "WORKFLOW_INVALID", "Workflow response conflict_type", workflow)
    check(workflow.get("resolution_strategy") == "SERVER_AUTHORITY", "Workflow response resolution_strategy", workflow)
    check(payload.get("total_processed") == 2, "Conflict batch total_processed is 2", payload)


def latest_conflict(db, event_id: str, pending_only: bool = False) -> SyncConflict | None:
    query = db.query(SyncConflict).filter(
        SyncConflict.tenant_id == TENANT_ID,
        SyncConflict.event_id == uuid.UUID(event_id),
    )
    if pending_only:
        query = query.filter(SyncConflict.status == "PENDING_REVIEW")
    return query.order_by(SyncConflict.created_at.desc()).first()


def all_conflicts(db, event_id: str) -> list[SyncConflict]:
    return db.query(SyncConflict).filter(
        SyncConflict.tenant_id == TENANT_ID,
        SyncConflict.event_id == uuid.UUID(event_id),
    ).order_by(SyncConflict.created_at.desc()).all()


def sync_failed_for_event(db, event_id: str) -> list[AuditChainEntry]:
    rows = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == TENANT_ID,
        AuditChainEntry.action == "SYNC_FAILED",
    ).all()
    return [
        row for row in rows
        if str(row.correlation_id) == event_id
        or str((row.metadata_ or {}).get("sync_event_id")) == event_id
    ]


def assert_durable_conflict_rows(expect_version_pending: bool, expect_workflow_pending: bool) -> None:
    db = SessionLocal()
    try:
        processed_expectations = {
            VERSION_EVENT_ID: ("crop_activity", VERSION_ACTIVITY_ID, "VERSION_MISMATCH", "MANUAL_REVIEW"),
            WORKFLOW_EVENT_ID: ("crop_stage", WORKFLOW_ENTITY_ID, "WORKFLOW_INVALID", "SERVER_AUTHORITY"),
        }
        for event_id, (entity_type, entity_id, conflict_type, strategy) in processed_expectations.items():
            processed = db.query(SyncProcessedEvent).filter(
                SyncProcessedEvent.tenant_id == TENANT_ID,
                SyncProcessedEvent.event_id == uuid.UUID(event_id),
            ).first()
            check(processed is not None, f"processed row exists for {conflict_type}", {"event_id": event_id})
            check(processed.status == "CONFLICT", f"processed status is CONFLICT for {conflict_type}", processed.status)
            check(processed.entity_type == entity_type, f"processed entity_type for {conflict_type}", processed.entity_type)
            check(str(processed.entity_id) == entity_id, f"processed entity_id for {conflict_type}", str(processed.entity_id))

            conflicts = all_conflicts(db, event_id)
            check(bool(conflicts), f"sync_conflicts row exists for {conflict_type}", {"event_id": event_id})
            latest = conflicts[0]
            check(latest.conflict_type == conflict_type, f"durable conflict_type for {conflict_type}", latest.conflict_type)
            check(latest.resolution_strategy == strategy, f"durable resolution_strategy for {conflict_type}", latest.resolution_strategy)
            check(not sync_failed_for_event(db, event_id), f"no SYNC_FAILED audit for {conflict_type}")

        version_pending = latest_conflict(db, VERSION_EVENT_ID, pending_only=True)
        workflow_pending = latest_conflict(db, WORKFLOW_EVENT_ID, pending_only=True)
        check(bool(version_pending) == expect_version_pending, "VERSION_MISMATCH pending DB expectation", {
            "expected_pending": expect_version_pending,
            "pending_found": bool(version_pending),
        })
        check(bool(workflow_pending) == expect_workflow_pending, "WORKFLOW_INVALID pending DB expectation", {
            "expected_pending": expect_workflow_pending,
            "pending_found": bool(workflow_pending),
        })
    finally:
        db.close()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_pending_endpoint(expect_version: bool, expect_workflow: bool) -> dict:
    payload = get_pending()
    rows = payload.get("conflicts") or []
    by_event = {}
    for row in rows:
        by_event.setdefault(row.get("event_id"), []).append(row)

    check(len(by_event.get(VERSION_EVENT_ID, [])) <= 1, "Pending endpoint dedups VERSION_MISMATCH by event_id", by_event.get(VERSION_EVENT_ID, []))
    check(len(by_event.get(WORKFLOW_EVENT_ID, [])) <= 1, "Pending endpoint dedups WORKFLOW_INVALID by event_id", by_event.get(WORKFLOW_EVENT_ID, []))
    check((VERSION_EVENT_ID in by_event) == expect_version, "Pending endpoint VERSION_MISMATCH visibility", {
        "expected_visible": expect_version,
        "visible": VERSION_EVENT_ID in by_event,
    })
    check((WORKFLOW_EVENT_ID in by_event) == expect_workflow, "Pending endpoint WORKFLOW_INVALID visibility", {
        "expected_visible": expect_workflow,
        "visible": WORKFLOW_EVENT_ID in by_event,
    })

    if expect_version:
        version = by_event[VERSION_EVENT_ID][0]
        check(version.get("conflict_type") == "VERSION_MISMATCH", "Pending version conflict_type", version)
        check(version.get("resolution_strategy") == "MANUAL_REVIEW", "Pending version resolution_strategy", version)
        check(version.get("android_action") == "SHOW_MANUAL_REVIEW_CONFLICT", "Pending version android_action", version)
        check("client_payload_summary" in version and "server_payload_summary" in version, "Pending version summaries present", version)
    if expect_workflow:
        workflow = by_event[WORKFLOW_EVENT_ID][0]
        check(workflow.get("conflict_type") == "WORKFLOW_INVALID", "Pending workflow conflict_type", workflow)
        check(workflow.get("resolution_strategy") == "SERVER_AUTHORITY", "Pending workflow resolution_strategy", workflow)
        check(workflow.get("android_action") == "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE", "Pending workflow android_action", workflow)
        check("client_payload_summary" in workflow and "server_payload_summary" in workflow, "Pending workflow summaries present", workflow)

    if expect_version and expect_workflow:
        version_index = next(i for i, row in enumerate(rows) if row.get("event_id") == VERSION_EVENT_ID)
        workflow_index = next(i for i, row in enumerate(rows) if row.get("event_id") == WORKFLOW_EVENT_ID)
        version_created = parse_dt(by_event[VERSION_EVENT_ID][0]["created_at"])
        workflow_created = parse_dt(by_event[WORKFLOW_EVENT_ID][0]["created_at"])
        check(workflow_created >= version_created, "Fixture created_at order has workflow newest or equal", {
            "version_created_at": by_event[VERSION_EVENT_ID][0]["created_at"],
            "workflow_created_at": by_event[WORKFLOW_EVENT_ID][0]["created_at"],
        })
        check(workflow_index < version_index, "Pending endpoint order is newest first for fixture conflicts", {
            "workflow_index": workflow_index,
            "version_index": version_index,
        })

    return payload


def ack_event(event_id: str) -> dict:
    pending = get_pending()
    matches = [item for item in pending.get("conflicts", []) if item.get("event_id") == event_id]
    check(len(matches) == 1, f"Pending endpoint has exactly one visible row to ACK for {event_id}", matches)
    row = matches[0]
    response = client.patch(
        f"/api/v1/sync/conflicts/{row['id']}",
        json={"strategy": "ACCEPT_SERVER"},
        headers=HEADERS,
    )
    payload = response.json()
    check(response.status_code == 200, f"ACK {event_id} returns 200", payload)
    check(payload.get("status") == "resolved", f"ACK {event_id} response status resolved", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-conflict-batch", action="store_true")
    parser.add_argument("--resend-conflict-batch", action="store_true")
    parser.add_argument("--ack-version", action="store_true")
    parser.add_argument("--ack-workflow", action="store_true")
    parser.add_argument("--ack-both", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID MULTI-CONFLICT PENDING DRAWER VERIFIER")
    print("=" * 72)

    if BASELINE_PATH.exists():
        print(json.dumps({"baseline_path": str(BASELINE_PATH), "baseline_present": True}, sort_keys=True))

    if args.send_conflict_batch:
        status, payload = post_sync(conflict_batch())
        check(status == 200, "Multi-conflict batch returns HTTP 200", payload)
        assert_batch_response(payload)

    if args.resend_conflict_batch:
        status, payload = post_sync(conflict_batch())
        check(status == 200, "Multi-conflict resend returns HTTP 200", payload)
        assert_batch_response(payload)

    if args.ack_both:
        args.ack_version = True
        args.ack_workflow = True

    if args.ack_version and args.ack_workflow:
        ack_event(VERSION_EVENT_ID)
        assert_durable_conflict_rows(expect_version_pending=False, expect_workflow_pending=True)
        assert_pending_endpoint(expect_version=False, expect_workflow=True)
        ack_event(WORKFLOW_EVENT_ID)
        assert_durable_conflict_rows(expect_version_pending=False, expect_workflow_pending=False)
        assert_pending_endpoint(expect_version=False, expect_workflow=False)
    elif args.ack_version:
        ack_event(VERSION_EVENT_ID)
        assert_durable_conflict_rows(expect_version_pending=False, expect_workflow_pending=True)
        assert_pending_endpoint(expect_version=False, expect_workflow=True)
    elif args.ack_workflow:
        ack_event(WORKFLOW_EVENT_ID)
        assert_durable_conflict_rows(expect_version_pending=True, expect_workflow_pending=False)
        assert_pending_endpoint(expect_version=True, expect_workflow=False)
    else:
        assert_durable_conflict_rows(expect_version_pending=True, expect_workflow_pending=True)
        assert_pending_endpoint(expect_version=True, expect_workflow=True)

    print(json.dumps({
        "schema_version": "android_multi_conflict_pending_drawer_verify.v1",
        "tenant_id": TENANT_ID,
        "event_ids": {
            "version_mismatch": VERSION_EVENT_ID,
            "workflow_invalid": WORKFLOW_EVENT_ID,
        },
        "expected_android_behavior": {
            "VERSION_MISMATCH": {
                "android_action": "SHOW_MANUAL_REVIEW_CONFLICT",
                "title": "Manual review needed: server has a newer version",
            },
            "WORKFLOW_INVALID": {
                "android_action": "SHOW_SERVER_AUTHORITY_WORKFLOW_MESSAGE",
                "title": "Workflow changed on backend",
            },
        },
        "resend_checked": args.resend_conflict_batch,
        "ack_version": args.ack_version,
        "ack_workflow": args.ack_workflow,
    }, indent=2, sort_keys=True))
    print("=" * 72)
    print("Android multi-conflict pending drawer verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())