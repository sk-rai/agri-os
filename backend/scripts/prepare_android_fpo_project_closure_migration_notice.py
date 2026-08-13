"""Prepare stateful FPO project-closure notice fixture for Android Maestro.

Unlike verify_android_fpo_project_closure_migration_notice.py, this script leaves
state applied so Android can observe it:
- published broadcast campaign with generated farmer deliveries;
- selected farmer project enrollment marked COMPLETED;
- hydration moves selected farmer to SELF_SERVICE context.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import FarmerProjectEnrollment
from app.modules.media.models import BroadcastAuditEvent, BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
from scripts.prepare_android_fpo_multi_village_workflow import FARMERS, PROJECT_ID, TENANT_ID, enrollment_id, farmer_id

CAMPAIGN_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002950")
SELECTED_FARMER_ID = farmer_id(6)
SELECTED_ENROLLMENT_ID = enrollment_id(6)
SELECTED_MOBILE = "+919900002106"


def check(condition: bool, label: str, detail=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str) if not isinstance(detail, str) else detail)
    if not condition:
        raise AssertionError(label)


def request_json(client: TestClient, method: str, path: str, headers: dict | None = None, body: dict | None = None, expected: int = 200) -> dict:
    response = client.request(method, path, headers=headers or {"X-Tenant-ID": TENANT_ID}, json=body)
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1000])
    return response.json()


def cleanup_campaign(db) -> None:
    db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
    db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
    db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == TENANT_ID, BroadcastAudienceRule.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
    db.query(BroadcastContent).filter(BroadcastContent.tenant_id == TENANT_ID, BroadcastContent.campaign_id == CAMPAIGN_ID).delete(synchronize_session=False)
    db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id == CAMPAIGN_ID).delete(synchronize_session=False)


def set_selected_enrollment_status(status: str) -> None:
    db = SessionLocal()
    try:
        enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == SELECTED_ENROLLMENT_ID, FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
        check(enrollment is not None, "Selected enrollment exists")
        metadata = dict(enrollment.metadata_ or {})
        metadata["project_closure_migration_notice_prepare"] = {"selected_status": status, "script": Path(__file__).name}
        enrollment.status = status
        enrollment.metadata_ = metadata
        db.commit()
    finally:
        db.close()


def create_notice(client: TestClient, headers: dict, actor_id: uuid.UUID) -> dict:
    body = {
        "id": str(CAMPAIGN_ID),
        "project_id": str(PROJECT_ID),
        "title": "FPO project closure migration notice",
        "category": "GENERAL",
        "priority": "HIGH",
        "created_by": str(actor_id),
        "metadata": {
            "event_type": "PROJECT_CLOSURE_MIGRATION_NOTICE",
            "android_contract": "project_closure_migration_notice.v1",
            "requires_farmer_choice": True,
            "migration_target": "SELF_SERVICE",
            "audience_match_mode": "ALL",
            "stateful_android_prepare": True,
        },
        "contents": [
            {
                "language_code": "en",
                "title": "Project is closing soon",
                "body_text": "This FPO crop project is coming to a close. You can continue using Agri-OS as an independent farmer after the project ends.",
                "cta_label": "Continue as independent farmer",
                "deeplink_url": f"agrios://project-closure/continue-independent?project_id={PROJECT_ID}",
                "metadata": {
                    "android_copy_role": "project_closure_migration_notice",
                    "display_as_actionable_info": True,
                    "does_not_block_home": True,
                },
            }
        ],
        "audience_rules": [
            {"rule_type": "PROJECT", "operator": "IN", "values": [str(PROJECT_ID)], "metadata": {"reason": "all active project farmers before selected enrollment closure"}}
        ],
    }
    created = request_json(client, "POST", "/api/v1/broadcasts", headers, body, 201)
    published = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish", headers, {"approved_by": str(actor_id), "reason": "Android Flow 43 project closure migration notice prepare"})
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries", headers)
    check(created["id"] == str(CAMPAIGN_ID), "Closure notice campaign id is deterministic")
    check(published["status"] == "PUBLISHED", "Closure notice campaign published")
    check(generated["delivery_summary"]["total"] == len(FARMERS), "Closure notice generated all FPO deliveries", generated["delivery_summary"])
    return generated


def verify_applied_state(client: TestClient) -> dict:
    feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read=true")
    hydration = request_json(client, "GET", f"/api/v1/farmers/by-mobile/{SELECTED_MOBILE}?include_form_contract=true&project_id={PROJECT_ID}")
    check(feed["count"] == 1, "Selected farmer broadcast feed has closure notice", feed)
    item = feed["broadcasts"][0]
    check(item["campaign"]["metadata"].get("event_type") == "PROJECT_CLOSURE_MIGRATION_NOTICE", "Closure notice event type is Android-visible")
    check(item["content"]["cta_label"] == "Continue as independent farmer", "Closure notice CTA is Android-visible")
    check(item["content"]["deeplink_url"].startswith("agrios://project-closure/continue-independent"), "Closure notice deeplink is Android-visible")
    context = hydration["farmer_context"]
    selected_enrollments = [row for row in hydration["project_enrollments"] if row["id"] == str(SELECTED_ENROLLMENT_ID)]
    check(len(selected_enrollments) == 1 and selected_enrollments[0]["status"] == "COMPLETED", "Selected enrollment is COMPLETED for Android")
    check(context["mode"] == "SELF_SERVICE", "Selected farmer hydrates as SELF_SERVICE for Android", context)
    check(context["can_continue_independently"] is True, "Selected farmer can continue independently")
    check(context["active_project_count"] == 0, "Selected farmer active project count is zero")
    return {"feed": feed, "hydration_context": context, "selected_enrollment": selected_enrollments[0]}


def apply_state(reset: bool) -> dict:
    db = SessionLocal()
    try:
        if reset:
            cleanup_campaign(db)
            db.commit()
    finally:
        db.close()

    set_selected_enrollment_status("ACTIVE")
    db = SessionLocal()
    admin_user, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
    db.close()
    try:
        client = TestClient(app)
        campaign = create_notice(client, admin_headers, admin_user.id)
        set_selected_enrollment_status("COMPLETED")
        applied = verify_applied_state(client)
        return {"campaign": campaign, "applied": applied}
    finally:
        cleanup_db = SessionLocal()
        try:
            delete_test_admin(cleanup_db, admin_user.id)
        finally:
            cleanup_db.close()


def reset_state() -> dict:
    db = SessionLocal()
    try:
        cleanup_campaign(db)
        db.commit()
    finally:
        db.close()
    set_selected_enrollment_status("ACTIVE")
    client = TestClient(app)
    hydration = request_json(client, "GET", f"/api/v1/farmers/by-mobile/{SELECTED_MOBILE}?include_form_contract=true&project_id={PROJECT_ID}")
    check(hydration["farmer_context"]["mode"] == "PROJECT", "Reset restores selected farmer PROJECT context", hydration["farmer_context"])
    return {"hydration_context": hydration["farmer_context"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Clear existing closure notice campaign and start from ACTIVE selected enrollment before applying.")
    parser.add_argument("--apply", action="store_true", help="Apply and leave Android-observable closure notice state.")
    parser.add_argument("--restore", action="store_true", help="Remove closure notice and restore selected enrollment ACTIVE.")
    args = parser.parse_args()
    if not args.apply and not args.restore:
        parser.error("Use --apply or --restore")

    print("=" * 72)
    print("ANDROID FPO PROJECT CLOSURE MIGRATION NOTICE PREPARE")
    print("=" * 72)
    if args.restore:
        state = reset_state()
        mode = "RESTORE"
    else:
        state = apply_state(reset=args.reset)
        mode = "APPLY_LEAVE_STATE"

    result = {
        "schema_version": "android_fpo_project_closure_migration_notice_prepare.v1",
        "mode": mode,
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_id": str(CAMPAIGN_ID),
        "selected_farmer_id": str(SELECTED_FARMER_ID),
        "selected_mobile": SELECTED_MOBILE,
        "selected_enrollment_id": str(SELECTED_ENROLLMENT_ID),
        "state": state,
        "android_expected": {
            "selected_farmer_broadcast_count": 1 if args.apply else 0,
            "event_type": "PROJECT_CLOSURE_MIGRATION_NOTICE",
            "cta_label": "Continue as independent farmer",
            "after_context": "SELF_SERVICE" if args.apply else "PROJECT",
        },
        "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore",
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())