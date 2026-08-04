"""Verify backend conflict state after Android conflict recovery/dismissal.

Android conflict recovery should acknowledge the backend conflict with
ACCEPT_SERVER when the user discards the local conflicted draft/action after
refreshing context. This leaves a durable resolved conflict row and
CONFLICT_RESOLVED audit entry.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent


TENANT_ID = "android-dynamic-test"
EXPECTED = {
    "VERSION_MISMATCH": {
        "event_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000111"),
        "entity_type": "crop_activity",
        "resolved_status": "RESOLVED_SERVER",
    },
    "WORKFLOW_INVALID": {
        "event_id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000121"),
        "entity_type": "crop_stage",
        "resolved_status": "RESOLVED_SERVER",
    },
}


def check(condition: bool, label: str, detail=None) -> None:
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(f"      {json.dumps(detail, default=str)[:1000]}")
        return
    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, default=str)[:2000])
    raise AssertionError(label)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conflict-type",
        required=True,
        choices=sorted(EXPECTED.keys()),
    )
    parser.add_argument("--event-id", help="Override deterministic event id.")
    parser.add_argument("--tenant-id", default=TENANT_ID)
    args = parser.parse_args()

    expected = EXPECTED[args.conflict_type]
    event_id = uuid.UUID(args.event_id) if args.event_id else expected["event_id"]

    db = SessionLocal()
    try:
        processed = (
            db.query(SyncProcessedEvent)
            .filter(
                SyncProcessedEvent.tenant_id == args.tenant_id,
                SyncProcessedEvent.event_id == event_id,
            )
            .first()
        )
        check(processed is not None, "sync_processed_events row exists", {"event_id": str(event_id)})
        check(processed.status == "CONFLICT", "processed event remains CONFLICT for audit/idempotency", processed.__dict__)
        check(processed.entity_type == expected["entity_type"], "processed entity_type matches expected", processed.entity_type)

        conflict = (
            db.query(SyncConflict)
            .filter(
                SyncConflict.tenant_id == args.tenant_id,
                SyncConflict.event_id == event_id,
                SyncConflict.conflict_type == args.conflict_type,
            )
            .order_by(SyncConflict.created_at.desc())
            .first()
        )
        check(conflict is not None, "sync_conflicts row exists", {"event_id": str(event_id)})
        check(conflict.status == expected["resolved_status"], "conflict is resolved as server accepted", conflict.__dict__)
        check(conflict.resolved_at is not None, "conflict resolved_at is set", conflict.resolved_at)
        check(conflict.resolved_by is not None, "conflict resolved_by is set", conflict.resolved_by)

        pending_same_event = (
            db.query(SyncConflict)
            .filter(
                SyncConflict.tenant_id == args.tenant_id,
                SyncConflict.event_id == event_id,
                SyncConflict.status == "PENDING_REVIEW",
            )
            .first()
        )
        check(pending_same_event is None, "no pending conflict remains for this event")

        failed = (
            db.query(SyncProcessedEvent)
            .filter(
                SyncProcessedEvent.tenant_id == args.tenant_id,
                SyncProcessedEvent.event_id == event_id,
                SyncProcessedEvent.status == "FAILED",
            )
            .first()
        )
        check(failed is None, "no FAILED processed-event row exists for conflict recovery")

        audit_candidates = (
            db.query(AuditChainEntry)
            .filter(
                AuditChainEntry.tenant_id == args.tenant_id,
                AuditChainEntry.entity_type == conflict.entity_type,
                AuditChainEntry.entity_id == conflict.entity_id,
                AuditChainEntry.action == "CONFLICT_RESOLVED",
            )
            .order_by(AuditChainEntry.created_at.desc(), AuditChainEntry.id.desc())
            .limit(50)
            .all()
        )
        audit = next(
            (
                row for row in audit_candidates
                if (row.metadata_ or {}).get("conflict_id") == str(conflict.id)
            ),
            None,
        )
        check(audit is not None, "CONFLICT_RESOLVED audit row exists for exact conflict", {"event_id": str(event_id), "conflict_id": str(conflict.id)})
        metadata = audit.metadata_ or {}
        check(metadata.get("resolution_strategy") == "ACCEPT_SERVER", "audit resolution_strategy is ACCEPT_SERVER", metadata)
        check(metadata.get("sync_event_id") == str(event_id), "audit sync_event_id matches", metadata)
        check(metadata.get("conflict_type") == args.conflict_type, "audit conflict_type matches", metadata)

        result = {
            "schema_version": "android_conflict_recovery_state_verify.v1",
            "tenant_id": args.tenant_id,
            "event_id": str(event_id),
            "conflict_type": args.conflict_type,
            "processed_event": {
                "status": processed.status,
                "entity_type": processed.entity_type,
                "entity_id": str(processed.entity_id) if processed.entity_id else None,
                "operation": processed.operation,
                "processed_at": processed.processed_at,
            },
            "conflict": {
                "id": str(conflict.id),
                "status": conflict.status,
                "resolution_strategy": conflict.resolution_strategy,
                "resolved_at": conflict.resolved_at,
                "resolved_by": str(conflict.resolved_by) if conflict.resolved_by else None,
            },
            "pending_conflict_remaining": False,
            "failed_row_present": False,
            "audit": {
                "action": audit.action,
                "resolution_strategy": metadata.get("resolution_strategy"),
                "created_at": audit.created_at,
            },
            "android_expected_recovery": {
                "refresh_context_first": True,
                "discard_local_conflicted_row_only": True,
                "backend_acknowledged_with_accept_server": True,
                "delete_synced_rows": False,
                "delete_unrelated_pending_rows": False,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
