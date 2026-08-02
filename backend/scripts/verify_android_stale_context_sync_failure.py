"""Verify Android stale-context sync failure after Sync Now.

The Android test should pass the event_id for the queued offline crop_cycle
event. The verifier confirms the event failed as stale context, not as a
manual conflict.
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
    parser.add_argument("--event-id", required=True, help="Android queued offline crop_cycle sync event UUID.")
    parser.add_argument("--tenant-id", default=TENANT_ID)
    args = parser.parse_args()

    event_id = uuid.UUID(args.event_id)
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
        check(processed.status == "FAILED", "sync event status is FAILED", processed.__dict__)
        check(processed.entity_type == "crop_cycle", "failed event entity_type is crop_cycle", processed.entity_type)

        conflict = (
            db.query(SyncConflict)
            .filter(
                SyncConflict.tenant_id == args.tenant_id,
                SyncConflict.event_id == event_id,
            )
            .first()
        )
        check(conflict is None, "no manual sync_conflicts row created", conflict.__dict__ if conflict else None)

        audit_candidates = (
            db.query(AuditChainEntry)
            .filter(
                AuditChainEntry.tenant_id == args.tenant_id,
                AuditChainEntry.action == "SYNC_FAILED",
                AuditChainEntry.entity_type == processed.entity_type,
                AuditChainEntry.entity_id == processed.entity_id,
            )
            .order_by(AuditChainEntry.created_at.desc(), AuditChainEntry.id.desc())
            .limit(20)
            .all()
        )
        audit = next(
            (
                row for row in audit_candidates
                if (row.metadata_ or {}).get("sync_event_id") == str(event_id)
            ),
            None,
        )
        check(audit is not None, "SYNC_FAILED audit row exists", {"event_id": str(event_id)})

        metadata = audit.metadata_ or {}
        check(metadata.get("error_code") == "MATERIALIZATION_FAILED", "audit error_code is MATERIALIZATION_FAILED", metadata)
        check(metadata.get("detail_code") == "PARCEL_PROJECT_MISMATCH", "audit detail_code is PARCEL_PROJECT_MISMATCH", metadata)

        result = {
            "schema_version": "android_stale_context_sync_failure_verify.v1",
            "tenant_id": args.tenant_id,
            "event_id": str(event_id),
            "processed_event": {
                "status": processed.status,
                "entity_type": processed.entity_type,
                "entity_id": str(processed.entity_id) if processed.entity_id else None,
                "operation": processed.operation,
                "processed_at": processed.processed_at,
            },
            "conflict_row_present": False,
            "audit": {
                "action": audit.action,
                "error_code": metadata.get("error_code"),
                "detail_code": metadata.get("detail_code"),
                "message": metadata.get("message"),
                "created_at": audit.created_at,
            },
            "android_expected_home_status": {
                "title": "Refresh required: local context is stale",
                "mode": "refresh_local_data",
                "manual_conflict_ui": False,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
