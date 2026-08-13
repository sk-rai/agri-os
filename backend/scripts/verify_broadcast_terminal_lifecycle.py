"""Verify broadcast terminal lifecycle removes farmer feed visibility while preserving admin audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.media.models import BroadcastAuditEvent, BroadcastCampaign, BroadcastDelivery
from scripts.prepare_android_fpo_project_closure_migration_notice import CAMPAIGN_ID, SELECTED_FARMER_ID, SELECTED_MOBILE
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID

TERMINAL_ACTIONS = {
    "expire": {"status": "EXPIRED", "audit": "EXPIRE_CAMPAIGN", "endpoint": "expire"},
    "cancel": {"status": "CANCELLED", "audit": "CANCEL_CAMPAIGN", "endpoint": "cancel"},
}


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


def selected_feed(client: TestClient) -> dict:
    return request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read=true")


def verify_pre_transition(client: TestClient) -> dict:
    detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    summary = detail.get("delivery_summary") or {}
    check(detail["status"] == "PUBLISHED", "Campaign starts PUBLISHED", {"status": detail["status"]})
    check(summary.get("total") == 12, "Campaign preserves 12 delivery rows before transition", summary)

    feed = selected_feed(client)
    check(feed["count"] == 1, "Selected farmer sees active campaign before terminal transition", feed)
    check(feed["broadcasts"][0]["campaign"]["id"] == str(CAMPAIGN_ID), "Feed points to deterministic closure campaign")
    return {"detail": detail, "feed": feed}


def verify_terminal_transition(client: TestClient, action: str) -> dict:
    config = TERMINAL_ACTIONS[action]
    before = verify_pre_transition(client)
    before_summary = before["detail"].get("delivery_summary") or {}

    transitioned = request_json(
        client,
        "POST",
        f"/api/v1/broadcasts/{CAMPAIGN_ID}/{config['endpoint']}",
        body={"reason": f"Broadcast terminal lifecycle smoke: {config['status']}"},
    )
    check(transitioned["status"] == config["status"], f"Campaign transitions to {config['status']}", transitioned)
    check((transitioned.get("delivery_summary") or {}).get("total") == before_summary.get("total"), "Terminal transition preserves delivery rows", transitioned.get("delivery_summary"))
    if config["status"] == "EXPIRED":
        check(transitioned.get("expires_at") is not None, "Expired campaign sets expires_at", transitioned.get("expires_at"))

    feed_after = selected_feed(client)
    check(feed_after["count"] == 0, "Selected farmer feed hides terminal campaign", feed_after)

    admin_detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    check(admin_detail["status"] == config["status"], "Admin detail still exposes terminal campaign", admin_detail)
    check((admin_detail.get("delivery_summary") or {}).get("total") == 12, "Admin detail keeps delivery summary after terminal transition", admin_detail.get("delivery_summary"))
    return {"before": before, "transitioned": transitioned, "feed_after": feed_after, "admin_detail": admin_detail}


def verify_db_audit(action: str) -> dict:
    config = TERMINAL_ACTIONS[action]
    db = SessionLocal()
    try:
        campaign = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id == CAMPAIGN_ID).first()
        check(campaign is not None and campaign.status == config["status"], "DB campaign has terminal status", campaign.status if campaign else None)
        delivery_count = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id == CAMPAIGN_ID).count()
        check(delivery_count == 12, "DB keeps 12 delivery rows after terminal transition", delivery_count)
        events = db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id == CAMPAIGN_ID).order_by(BroadcastAuditEvent.created_at.asc()).all()
        actions = [row.action for row in events]
        check(config["audit"] in actions, f"Broadcast audit includes {config['audit']}", actions)
        return {"campaign_status": campaign.status, "delivery_count": delivery_count, "audit_actions": actions}
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify terminal broadcast lifecycle behavior.")
    parser.add_argument("--action", choices=sorted(TERMINAL_ACTIONS), required=True)
    args = parser.parse_args()
    config = TERMINAL_ACTIONS[args.action]

    print("=" * 72)
    print(f"BROADCAST TERMINAL LIFECYCLE VERIFIER: {config['status']}")
    print("=" * 72)
    client = TestClient(app)
    lifecycle = verify_terminal_transition(client, args.action)
    audit = verify_db_audit(args.action)
    result = {
        "schema_version": "broadcast_terminal_lifecycle_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "action": args.action,
        "terminal_status": config["status"],
        "audit_action": config["audit"],
        "lifecycle": lifecycle,
        "db_audit": audit,
        "readiness": {
            "farmer_feed_hidden_after_terminal_transition": True,
            "admin_detail_preserves_terminal_campaign": True,
            "delivery_history_preserved": True,
            "terminal_audit_event_covered": True,
            "ready_for_broadcast_terminal_web_smoke": True,
        },
        "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore",
    }
    print("=" * 72)
    print(f"BROADCAST TERMINAL LIFECYCLE VERIFIED: {config['status']}")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())