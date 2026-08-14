"""Stateful Android fixture for broadcast terminal visibility dismissal.

Modes:
- --reset --apply: create a deterministic PUBLISHED farmer broadcast and leave it visible.
- --transition expire|cancel: move that campaign to a terminal state and verify farmer feed hides it.
- --cleanup: delete deterministic campaign/delivery/audit rows.

This gives Android/Maestro a stable before/after seam: render the visible card,
run --transition from backend, refresh Android feed, then assert the card is gone
without fatal error or retry-loop copy.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.media.models import (
    BroadcastAuditEvent,
    BroadcastAudienceRule,
    BroadcastCampaign,
    BroadcastContent,
    BroadcastDelivery,
)
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID

ACTOR_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")
SELECTED_FARMER_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002106")
SELECTED_MOBILE = "+919900002106"
CAMPAIGN_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002980")

TITLE = "Terminal visibility advisory smoke"
CONTENT_TITLE = "Broadcast ending soon"
BODY_TEXT = "This advisory is intentionally removed from the farmer feed after backend terminal transition."
CTA_LABEL = "Open terminal visibility advisory"
DEEPLINK_URL = "agrios://broadcast/terminal-visibility?campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002980"

TERMINAL_ACTIONS = {
    "expire": {"status": "EXPIRED", "endpoint": "expire", "audit": "EXPIRE_CAMPAIGN"},
    "cancel": {"status": "CANCELLED", "endpoint": "cancel", "audit": "CANCEL_CAMPAIGN"},
}


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def request_json(client: TestClient, method: str, path: str, *, expected: int = 200, body: dict | None = None) -> dict:
    response = client.request(method, path, headers={"X-Tenant-ID": TENANT_ID}, json=body)
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1200])
    return response.json()


def cleanup_state() -> dict:
    db = SessionLocal()
    try:
        counts = {
            "broadcast_deliveries": db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False),
            "broadcast_audit_events": db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False),
            "broadcast_audience_rules": db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == TENANT_ID, BroadcastAudienceRule.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False),
            "broadcast_contents": db.query(BroadcastContent).filter(BroadcastContent.tenant_id == TENANT_ID, BroadcastContent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False),
            "broadcast_campaigns": db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id == CAMPAIGN_ID).delete(synchronize_session=False),
        }
        db.commit()
        return {key: int(value or 0) for key, value in counts.items()}
    finally:
        db.close()


def farmer_feed(client: TestClient, include_read: bool = True) -> dict:
    include = "true" if include_read else "false"
    return request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read={include}")


def select_campaign_items(feed: dict) -> list[dict]:
    return [row for row in feed.get("broadcasts", []) if row.get("campaign", {}).get("id") == str(CAMPAIGN_ID)]


def create_visible_campaign(client: TestClient) -> dict:
    created = request_json(
        client,
        "POST",
        "/api/v1/broadcasts",
        expected=201,
        body={
            "id": str(CAMPAIGN_ID),
            "project_id": str(PROJECT_ID),
            "title": TITLE,
            "category": "GENERAL",
            "priority": "HIGH",
            "created_by": str(ACTOR_ID),
            "metadata": {
                "android_contract": "broadcast_terminal_visibility.v1",
                "event_type": "TERMINAL_VISIBILITY_ADVISORY",
                "terminal_transition_backend_owned": True,
                "expected_android_behavior": "DISMISS_AFTER_REFRESH",
                "audience_match_mode": "ALL",
            },
            "contents": [
                {
                    "language_code": "en",
                    "title": CONTENT_TITLE,
                    "body_text": BODY_TEXT,
                    "cta_label": CTA_LABEL,
                    "deeplink_url": DEEPLINK_URL,
                    "metadata": {"android_copy_role": "terminal_visibility_advisory", "does_not_block_home": True},
                }
            ],
            "audience_rules": [
                {
                    "rule_type": "FARMER",
                    "operator": "IN",
                    "values": [str(SELECTED_FARMER_ID)],
                    "metadata": {"reason": "single selected Android FPO farmer for terminal visibility smoke"},
                }
            ],
        },
    )
    published = request_json(
        client,
        "POST",
        f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish",
        body={"approved_by": str(ACTOR_ID), "reason": "Android terminal visibility smoke publish"},
    )
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries")
    check(published["status"] == "PUBLISHED", "Campaign is PUBLISHED before Android observes it", published)
    check(generated["delivery_summary"]["total"] == 1, "Single selected farmer delivery generated", generated.get("delivery_summary"))
    return {"created": created, "published": published, "generated": generated}


def verify_visible_state(client: TestClient) -> dict:
    detail = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}")
    check(detail["status"] == "PUBLISHED", "Campaign detail is PUBLISHED", detail)
    check((detail.get("delivery_summary") or {}).get("total") == 1, "Campaign has one delivery row", detail.get("delivery_summary"))
    feed = farmer_feed(client, include_read=True)
    items = select_campaign_items(feed)
    check(len(items) == 1, "Selected farmer feed shows terminal visibility campaign", feed)
    item = items[0]
    check(item["content"]["title"] == CONTENT_TITLE, "Farmer feed renders expected title", item.get("content"))
    check(item["delivery"]["delivery_status"] == "PENDING", "Visible delivery starts PENDING", item.get("delivery"))
    return {"detail": detail, "feed": feed, "item": item}


def mark_read_ack(client: TestClient, delivery_id: str) -> dict:
    read = request_json(client, "POST", f"/api/v1/broadcasts/deliveries/{delivery_id}/read")
    ack = request_json(client, "POST", f"/api/v1/broadcasts/deliveries/{delivery_id}/acknowledge")
    check(read["read_at"] is not None, "Optional pre-terminal read_at is set", read)
    check(ack["delivery_status"] == "ACKNOWLEDGED" and ack["acknowledged_at"] is not None, "Optional pre-terminal ACK is preserved", ack)
    return {"read": read, "ack": ack}


def transition_terminal(client: TestClient, action: str, ack_before_transition: bool) -> dict:
    config = TERMINAL_ACTIONS[action]
    before = verify_visible_state(client)
    ack = {}
    if ack_before_transition:
        ack = mark_read_ack(client, before["item"]["delivery"]["id"])

    transitioned = request_json(
        client,
        "POST",
        f"/api/v1/broadcasts/{CAMPAIGN_ID}/{config['endpoint']}",
        body={"actor_id": str(ACTOR_ID), "reason": f"Android terminal visibility smoke: {config['status']}"},
    )
    check(transitioned["status"] == config["status"], f"Campaign transitioned to {config['status']}", transitioned)
    check((transitioned.get("delivery_summary") or {}).get("total") == 1, "Terminal transition preserves delivery history", transitioned.get("delivery_summary"))

    feed_after = farmer_feed(client, include_read=True)
    check(len(select_campaign_items(feed_after)) == 0, "Selected farmer feed hides terminal campaign after refresh", feed_after)

    audit = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/audit?limit=100")
    actions = [row["action"] for row in audit.get("events", [])]
    check(config["audit"] in actions, f"Audit includes {config['audit']}", actions)
    if ack_before_transition:
        check("MARK_DELIVERY_READ" in actions and "ACKNOWLEDGE_DELIVERY" in actions, "Read/ACK audit remains preserved before terminal transition", actions)

    deliveries = request_json(client, "GET", f"/api/v1/broadcasts/{CAMPAIGN_ID}/deliveries?limit=100")
    check(deliveries["count"] == 1, "Admin delivery drilldown still has one row", deliveries)
    if ack_before_transition:
        check(deliveries["deliveries"][0]["delivery_status"] == "ACKNOWLEDGED", "Terminal campaign preserves acknowledged delivery status", deliveries["deliveries"][0])

    return {"before": before, "ack": ack, "transitioned": transitioned, "feed_after": feed_after, "audit": audit, "deliveries": deliveries}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete prior deterministic terminal visibility state before running.")
    parser.add_argument("--apply", action="store_true", help="Create and leave PUBLISHED campaign visible for Android.")
    parser.add_argument("--transition", choices=sorted(TERMINAL_ACTIONS), help="Transition visible campaign to terminal state and verify feed hides it.")
    parser.add_argument("--ack-before-transition", action="store_true", help="Mark selected delivery read/ack before terminal transition.")
    parser.add_argument("--cleanup", action="store_true", help="Delete deterministic terminal visibility state and exit.")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID BROADCAST TERMINAL VISIBILITY PREPARE")
    print("=" * 72)

    reset_counts = {}
    if args.reset or args.cleanup:
        reset_counts = cleanup_state()
        check(True, "Cleaned deterministic terminal visibility smoke state", reset_counts)
    if args.cleanup:
        print(json.dumps({
            "schema_version": "android_broadcast_terminal_visibility_prepare.v1",
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "reset": reset_counts,
        }, indent=2, sort_keys=True, default=str))
        return 0

    client = TestClient(app)
    created = create_visible_campaign(client) if args.apply else {}
    visible = verify_visible_state(client) if args.apply or not args.transition else {}
    terminal = transition_terminal(client, args.transition, args.ack_before_transition) if args.transition else {}

    result = {
        "schema_version": "android_broadcast_terminal_visibility_prepare.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "mode": "TRANSITION" if args.transition else "APPLY" if args.apply else "VERIFY",
        "terminal_action": args.transition,
        "ack_before_transition": args.ack_before_transition,
        "reset": reset_counts,
        "created_delivery_count": (created.get("generated") or {}).get("delivery_summary", {}).get("total"),
        "visible_feed_count": (visible.get("feed") or {}).get("count"),
        "terminal_feed_count": (terminal.get("feed_after") or {}).get("count"),
        "readiness": {
            "visible_before_transition_covered": True if args.apply or args.transition else False,
            "terminal_transition_backend_owned": True if args.transition else False,
            "farmer_feed_hidden_after_terminal_refresh": True if args.transition else False,
            "delivery_history_preserved": True if args.transition else False,
            "ready_for_android_broadcast_terminal_visibility_maestro": True,
        },
        "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_broadcast_terminal_visibility.py --cleanup",
    }
    print("=" * 72)
    print("ANDROID BROADCAST TERMINAL VISIBILITY READY")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())