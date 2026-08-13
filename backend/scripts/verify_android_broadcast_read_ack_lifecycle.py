"""Verify Android-visible broadcast read/ack lifecycle for project closure notice."""

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


def request_json(client: TestClient, method: str, path: str, body: dict | None = None, expected: int = 200) -> dict:
    response = client.request(method, path, headers={"X-Tenant-ID": TENANT_ID}, json=body)
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1000])
    return response.json()


def selected_feed(client: TestClient, include_read: bool = True) -> dict:
    include = "true" if include_read else "false"
    return request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read={include}")


def verify_prepared_state(client: TestClient) -> dict:
    feed = selected_feed(client, include_read=True)
    check(feed["count"] == 1, "Prepared feed has one selected closure notice", feed)
    item = feed["broadcasts"][0]
    check(item["campaign"]["id"] == str(CAMPAIGN_ID), "Prepared feed uses deterministic campaign id")
    check(item["campaign"]["metadata"].get("event_type") == "PROJECT_CLOSURE_MIGRATION_NOTICE", "Prepared feed has closure event type")
    check(item["delivery"]["delivery_status"] == "PENDING", "Prepared delivery starts PENDING", item["delivery"])
    check(item["delivery"]["read_at"] is None, "Prepared delivery read_at is null")
    check(item["delivery"]["acknowledged_at"] is None, "Prepared delivery acknowledged_at is null")
    return item


def verify_read_ack(client: TestClient, delivery_id: str) -> dict:
    read = request_json(client, "POST", f"/api/v1/broadcasts/deliveries/{delivery_id}/read")
    check(read["delivery_status"] == "DELIVERED", "Read marks pending delivery as DELIVERED", read)
    check(read["delivered_at"] is not None, "Read sets delivered_at")
    check(read["read_at"] is not None, "Read sets read_at")
    check(read["acknowledged_at"] is None, "Read does not set acknowledged_at")

    unread_feed = selected_feed(client, include_read=False)
    check(unread_feed["count"] == 0, "include_read=false hides read delivery", unread_feed)

    ack = request_json(client, "POST", f"/api/v1/broadcasts/deliveries/{delivery_id}/acknowledge")
    check(ack["delivery_status"] == "ACKNOWLEDGED", "Acknowledge marks delivery ACKNOWLEDGED", ack)
    check(ack["delivered_at"] is not None, "Acknowledge preserves delivered_at")
    check(ack["read_at"] is not None, "Acknowledge preserves read_at")
    check(ack["acknowledged_at"] is not None, "Acknowledge sets acknowledged_at")

    feed_after_ack = selected_feed(client, include_read=True)
    check(feed_after_ack["count"] == 1, "include_read=true still returns acknowledged delivery", feed_after_ack)
    check(feed_after_ack["broadcasts"][0]["delivery"]["delivery_status"] == "ACKNOWLEDGED", "Feed reflects acknowledged delivery")

    return {"read": read, "acknowledged": ack, "feed_after_ack": feed_after_ack}


def verify_db_audit(delivery_id: str) -> dict:
    db = SessionLocal()
    try:
        delivery = db.query(BroadcastDelivery).filter(BroadcastDelivery.id == delivery_id, BroadcastDelivery.tenant_id == TENANT_ID).first()
        check(delivery is not None and delivery.delivery_status == "ACKNOWLEDGED", "DB delivery is acknowledged", delivery.delivery_status if delivery else None)
        actions = [row.action for row in db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.delivery_id == delivery.id).order_by(BroadcastAuditEvent.created_at.asc()).all()]
        check("MARK_DELIVERY_READ" in actions, "Broadcast audit includes MARK_DELIVERY_READ", actions)
        check("ACKNOWLEDGE_DELIVERY" in actions, "Broadcast audit includes ACKNOWLEDGE_DELIVERY", actions)
        return {"delivery_status": delivery.delivery_status, "audit_actions": actions}
    finally:
        db.close()


def main() -> int:
    print("=" * 72)
    print("ANDROID BROADCAST READ/ACK LIFECYCLE VERIFIER")
    print("=" * 72)
    client = TestClient(app)
    prepared = verify_prepared_state(client)
    delivery_id = prepared["delivery"]["id"]
    lifecycle = verify_read_ack(client, delivery_id)
    audit = verify_db_audit(delivery_id)
    result = {
        "schema_version": "android_broadcast_read_ack_lifecycle_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "delivery_id": delivery_id,
        "lifecycle": lifecycle,
        "db_audit": audit,
        "readiness": {
            "ready_for_android_broadcast_read_ack_maestro": True,
            "delivery_read_lifecycle_covered": True,
            "delivery_ack_lifecycle_covered": True,
            "audit_events_covered": True,
            "hide_read_feed_filter_covered": True,
        },
        "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore",
    }
    print("=" * 72)
    print("ANDROID BROADCAST READ/ACK LIFECYCLE VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())