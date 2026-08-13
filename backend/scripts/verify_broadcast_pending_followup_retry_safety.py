"""Verify broadcast pending-recipient follow-up and retry safety for admin/FPO ops."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.media.models import BroadcastAuditEvent, BroadcastDelivery
from scripts.prepare_android_fpo_project_closure_migration_notice import CAMPAIGN_ID, SELECTED_FARMER_ID, SELECTED_MOBILE
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def request_json(client: TestClient, method: str, path: str, expected: int = 200) -> dict:
    response = client.request(method, path, headers={"X-Tenant-ID": TENANT_ID})
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1000])
    return response.json()


def delivery_summary(client: TestClient) -> dict:
    detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    summary = detail.get("delivery_summary") or {}
    return {"detail": detail, "summary": summary}


def verify_initial_followup_state(client: TestClient) -> dict:
    payload = delivery_summary(client)
    summary = payload["summary"]
    check(summary.get("total") == 12, "Campaign has 12 delivery rows", summary)
    check(summary.get("pending") == 11, "Pending-recipient cohort has 11 farmers", summary)
    check(summary.get("read") == 1, "Read count remains 1", summary)
    check(summary.get("acknowledged") == 1, "Acknowledged count remains 1", summary)

    pending = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?status=PENDING&limit=100")
    check(pending["count"] == 11, "Pending delivery drilldown returns 11 rows", {"count": pending["count"]})
    check(all(row["delivery_status"] == "PENDING" for row in pending["deliveries"]), "Pending drilldown rows are all PENDING")

    acknowledged = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?status=ACKNOWLEDGED&limit=100")
    check(acknowledged["count"] == 1, "Acknowledged drilldown returns one row", {"count": acknowledged["count"]})
    selected = acknowledged["deliveries"][0]
    check(selected["farmer_id"] == str(SELECTED_FARMER_ID), "Acknowledged row belongs to selected farmer", selected)
    check(selected["read_at"] is not None and selected["acknowledged_at"] is not None, "Acknowledged row keeps read/ack timestamps")
    return {"detail": payload["detail"], "pending": pending, "acknowledged": acknowledged}


def verify_retry_safety(client: TestClient) -> dict:
    before = verify_initial_followup_state(client)
    selected_before = before["acknowledged"]["deliveries"][0]

    retry = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/retry-undelivered")
    metadata = retry.get("metadata") or {}
    summary = retry.get("delivery_summary") or {}
    check(summary.get("pending") == 11, "Retry keeps pending rows pending", summary)
    check(summary.get("acknowledged") == 1, "Retry does not disturb acknowledged rows", summary)
    check(metadata.get("last_delivery_retry_retried") == 11, "Retry attempts 11 pending rows", metadata)
    check(metadata.get("last_delivery_retry_skipped_acknowledged") == 1, "Retry skips one read/ack row", metadata)
    check(metadata.get("last_delivery_retry_marked_failed") == 0, "First retry marks no rows failed", metadata)

    pending_after = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?status=PENDING&limit=100")
    retry_counts = [int((row.get("metadata") or {}).get("retry_count") or 0) for row in pending_after["deliveries"]]
    check(pending_after["count"] == 11, "Pending drilldown remains 11 after retry", {"count": pending_after["count"]})
    check(all(count >= 1 for count in retry_counts), "Pending rows carry retry_count metadata", retry_counts)

    acknowledged_after = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?status=ACKNOWLEDGED&limit=100")
    selected_after = acknowledged_after["deliveries"][0]
    check(selected_after["id"] == selected_before["id"], "Retry preserves selected acknowledged delivery id")
    check(selected_after["delivery_status"] == "ACKNOWLEDGED", "Retry preserves selected acknowledged status", selected_after)
    check(selected_after["read_at"] == selected_before["read_at"], "Retry preserves selected read_at")
    check(selected_after["acknowledged_at"] == selected_before["acknowledged_at"], "Retry preserves selected acknowledged_at")
    return {"retry": retry, "pending_after": pending_after, "acknowledged_after": acknowledged_after}


def verify_db_audit() -> dict:
    db = SessionLocal()
    try:
        events = db.query(BroadcastAuditEvent).filter(
            BroadcastAuditEvent.tenant_id == TENANT_ID,
            BroadcastAuditEvent.campaign_id == CAMPAIGN_ID,
        ).order_by(BroadcastAuditEvent.created_at.asc()).all()
        actions = [row.action for row in events]
        check("RETRY_DELIVERIES" in actions, "Broadcast audit includes RETRY_DELIVERIES", actions)
        pending_retry_rows = db.query(BroadcastDelivery).filter(
            BroadcastDelivery.tenant_id == TENANT_ID,
            BroadcastDelivery.campaign_id == CAMPAIGN_ID,
            BroadcastDelivery.delivery_status == "PENDING",
        ).all()
        check(len(pending_retry_rows) == 11, "DB still has 11 pending rows")
        check(all(int((row.metadata_ or {}).get("retry_count") or 0) >= 1 for row in pending_retry_rows), "DB pending rows have retry metadata")
        return {"audit_actions": actions, "pending_retry_count": len(pending_retry_rows)}
    finally:
        db.close()


def main() -> int:
    print("=" * 72)
    print("BROADCAST PENDING FOLLOW-UP RETRY SAFETY VERIFIER")
    print("=" * 72)
    client = TestClient(app)
    lifecycle = verify_retry_safety(client)
    audit = verify_db_audit()
    result = {
        "schema_version": "broadcast_pending_followup_retry_safety_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "lifecycle": lifecycle,
        "db_audit": audit,
        "readiness": {
            "pending_followup_cohort_covered": True,
            "retry_pending_rows_covered": True,
            "retry_skips_acknowledged_rows": True,
            "ready_for_broadcast_pending_followup_web_smoke": True,
        },
        "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore",
    }
    print("=" * 72)
    print("BROADCAST PENDING FOLLOW-UP RETRY SAFETY VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())