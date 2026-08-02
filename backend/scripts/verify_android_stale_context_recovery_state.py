"""Verify backend state after Android locally discards a stale-context sync row.

Android should not call a backend cleanup endpoint for stale-context failed sync
events. The backend keeps the FAILED idempotency row and SYNC_FAILED audit entry
for traceability. This read-only verifier confirms the durable failure remains
and that no conflict/commit row was created for the discarded local draft.
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
from app.modules.workflow.models import CropCycle


TENANT_ID = "android-dynamic-test"
STALE_DETAIL_CODES = {
    "PARCEL_PROJECT_MISMATCH",
    "PARCEL_FARMER_MISMATCH",
    "INVALID_PARCEL_FOR_FARMER",
    "INVALID_FARMER_FOR_TENANT",
    "INVALID_PROJECT_FOR_TENANT",
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
    parser.add_argument("--event-id", required=True, help="Failed stale-context sync event UUID.")
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
        check(processed is not None, "FAILED sync_processed_events row is still durable", {"event_id": str(event_id)})
        check(processed.status == "FAILED", "processed event remains FAILED after Android local discard", processed.__dict__)
        check(processed.status != "COMMITTED", "event was not later accepted/committed", processed.status)

        conflict = (
            db.query(SyncConflict)
            .filter(
                SyncConflict.tenant_id == args.tenant_id,
                SyncConflict.event_id == event_id,
            )
            .first()
        )
        check(conflict is None, "no sync_conflicts row exists for stale-context failure", conflict.__dict__ if conflict else None)

        audit_candidates = (
            db.query(AuditChainEntry)
            .filter(
                AuditChainEntry.tenant_id == args.tenant_id,
                AuditChainEntry.action == "SYNC_FAILED",
                AuditChainEntry.entity_type == processed.entity_type,
                AuditChainEntry.entity_id == processed.entity_id,
            )
            .order_by(AuditChainEntry.created_at.desc(), AuditChainEntry.id.desc())
            .limit(50)
            .all()
        )
        audit = next(
            (
                row for row in audit_candidates
                if (row.metadata_ or {}).get("sync_event_id") == str(event_id)
            ),
            None,
        )
        check(audit is not None, "SYNC_FAILED audit row is still durable", {"event_id": str(event_id)})
        metadata = audit.metadata_ or {}
        check(metadata.get("error_code") == "MATERIALIZATION_FAILED", "audit error_code remains MATERIALIZATION_FAILED", metadata)
        check(metadata.get("detail_code") in STALE_DETAIL_CODES, "audit detail_code is a stale-context code", metadata)

        materialized_entity_present = None
        if processed.entity_type == "crop_cycle" and processed.entity_id:
            materialized_entity_present = (
                db.query(CropCycle)
                .filter(
                    CropCycle.tenant_id == args.tenant_id,
                    CropCycle.id == processed.entity_id,
                )
                .first()
                is not None
            )
            check(not materialized_entity_present, "failed crop_cycle draft was not materialized", {"entity_id": str(processed.entity_id)})

        result = {
            "schema_version": "android_stale_context_recovery_state_verify.v1",
            "tenant_id": args.tenant_id,
            "event_id": str(event_id),
            "processed_event": {
                "status": processed.status,
                "entity_type": processed.entity_type,
                "entity_id": str(processed.entity_id) if processed.entity_id else None,
                "operation": processed.operation,
                "processed_at": processed.processed_at,
            },
            "audit": {
                "action": audit.action,
                "error_code": metadata.get("error_code"),
                "detail_code": metadata.get("detail_code"),
                "message": metadata.get("message"),
                "created_at": audit.created_at,
            },
            "conflict_row_present": False,
            "accepted_or_committed_after_discard": False,
            "materialized_entity_present": materialized_entity_present,
            "backend_cleanup_endpoint_required": False,
            "android_expected_recovery": {
                "refresh_context_first": True,
                "discard_stale_local_draft_only": True,
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
