"""Verify Android VERSION_MISMATCH conflict after Sync Now."""

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
ANDROID_EVENT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000111")
ACTIVITY_ENTITY_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000112")


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
    parser.add_argument("--event-id", default=str(ANDROID_EVENT_ID))
    parser.add_argument("--entity-id", default=str(ACTIVITY_ENTITY_ID))
    parser.add_argument("--tenant-id", default=TENANT_ID)
    args = parser.parse_args()

    event_id = uuid.UUID(args.event_id)
    entity_id = uuid.UUID(args.entity_id)

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
        check(processed.status == "CONFLICT", "sync event status is CONFLICT", processed.__dict__)
        check(processed.entity_type == "crop_activity", "entity_type is crop_activity", processed.entity_type)
        check(processed.entity_id == entity_id, "entity_id matches fixture activity", str(processed.entity_id))

        conflict = (
            db.query(SyncConflict)
            .filter(
                SyncConflict.tenant_id == args.tenant_id,
                SyncConflict.event_id == event_id,
            )
            .order_by(SyncConflict.created_at.desc())
            .first()
        )
        check(conflict is not None, "sync_conflicts row exists", {"event_id": str(event_id)})
        check(conflict.conflict_type == "VERSION_MISMATCH", "conflict_type is VERSION_MISMATCH", conflict.__dict__)
        check(conflict.resolution_strategy == "MANUAL_REVIEW", "resolution_strategy is MANUAL_REVIEW", conflict.resolution_strategy)
        check(conflict.status == "PENDING_REVIEW", "conflict status is PENDING_REVIEW", conflict.status)

        failed = (
            db.query(SyncProcessedEvent)
            .filter(
                SyncProcessedEvent.tenant_id == args.tenant_id,
                SyncProcessedEvent.event_id == event_id,
                SyncProcessedEvent.status == "FAILED",
            )
            .first()
        )
        check(failed is None, "no FAILED processed-event row for this event")

        audit_candidates = (
            db.query(AuditChainEntry)
            .filter(
                AuditChainEntry.tenant_id == args.tenant_id,
                AuditChainEntry.action == "SYNC_CONFLICT",
                AuditChainEntry.entity_type == "crop_activity",
                AuditChainEntry.entity_id == entity_id,
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
        check(audit is not None, "SYNC_CONFLICT audit row exists", {"event_id": str(event_id)})
        metadata = audit.metadata_ or {}
        check(metadata.get("conflict_type") == "VERSION_MISMATCH", "audit conflict_type is VERSION_MISMATCH", metadata)

        result = {
            "schema_version": "android_version_mismatch_conflict_verify.v1",
            "tenant_id": args.tenant_id,
            "event_id": str(event_id),
            "entity_id": str(entity_id),
            "processed_event": {
                "status": processed.status,
                "entity_type": processed.entity_type,
                "operation": processed.operation,
                "server_version": processed.server_version,
                "processed_at": processed.processed_at,
            },
            "conflict": {
                "conflict_type": conflict.conflict_type,
                "resolution_strategy": conflict.resolution_strategy,
                "status": conflict.status,
                "detail": (conflict.server_payload or {}).get("detail"),
            },
            "failed_row_present": False,
            "android_expected_home_status": {
                "title": "Manual review needed: server has a newer version",
                "mode": "manual_conflict_review",
                "stale_context_refresh_guidance": False,
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
