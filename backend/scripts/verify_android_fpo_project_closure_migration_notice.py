"""Verify FPO project-closure notice and independent-continuation lifecycle contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel
from app.modules.media.models import BroadcastAuditEvent, BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery
from app.modules.workflow.models import CropCycle
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
    check(response.status_code == expected, f"{method} {path} returns {expected}", response.text[:1200])
    return response.json()


def cleanup_campaign(db) -> None:
    for model in (BroadcastAuditEvent, BroadcastDelivery, BroadcastAudienceRule, BroadcastContent, BroadcastCampaign):
        db.query(model).filter(model.tenant_id == TENANT_ID, getattr(model, "campaign_id", model.id) == CAMPAIGN_ID).delete(synchronize_session=False)
    db.commit()


def restore_selected_enrollment(db) -> None:
    enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == SELECTED_ENROLLMENT_ID, FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
    if enrollment:
        metadata = dict(enrollment.metadata_ or {})
        metadata["restored_after_project_closure_notice_smoke"] = True
        enrollment.status = "ACTIVE"
        enrollment.metadata_ = metadata
        db.commit()


def verify_db_baseline() -> dict:
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.id == SELECTED_FARMER_ID, Farmer.tenant_id == TENANT_ID).first()
        enrollment = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.id == SELECTED_ENROLLMENT_ID, FarmerProjectEnrollment.tenant_id == TENANT_ID).first()
        check(farmer is not None and farmer.mobile_number == SELECTED_MOBILE, "Selected FPO farmer exists", farmer.mobile_number if farmer else None)
        check(enrollment is not None and enrollment.status == "ACTIVE", "Selected FPO enrollment starts ACTIVE", enrollment.status if enrollment else None)
        return {
            "selected_farmer_id": str(SELECTED_FARMER_ID),
            "selected_enrollment_id": str(SELECTED_ENROLLMENT_ID),
            "selected_mobile": SELECTED_MOBILE,
        }
    finally:
        db.close()


def create_publish_generate_notice(client: TestClient, headers: dict, actor_id: uuid.UUID) -> dict:
    create_payload = {
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
            {"rule_type": "PROJECT", "operator": "IN", "values": [str(PROJECT_ID)], "metadata": {"reason": "all active project farmers"}}
        ],
    }
    created = request_json(client, "POST", "/api/v1/broadcasts", headers, create_payload, 201)
    check(created["id"] == str(CAMPAIGN_ID), "Closure notice campaign created", created)
    check(created["status"] == "DRAFT", "Closure notice starts draft")

    published = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/publish", headers, {"approved_by": str(actor_id), "reason": "Project closure migration notice smoke"})
    check(published["status"] == "PUBLISHED", "Closure notice published", published)

    generated = request_json(client, "POST", f"/api/v1/broadcasts/{CAMPAIGN_ID}/generate-deliveries", headers)
    summary = generated["delivery_summary"]
    check(summary["total"] == len(FARMERS), "Closure notice generated one delivery per FPO farmer", summary)
    return {"campaign": generated, "delivery_summary": summary}


def verify_farmer_notice_feed(client: TestClient) -> dict:
    feed = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{SELECTED_FARMER_ID}/broadcasts?language_code=en&include_read=true")
    check(feed["count"] == 1, "Selected farmer receives one closure notice", feed)
    item = feed["broadcasts"][0]
    check(item["campaign"]["metadata"]["event_type"] == "PROJECT_CLOSURE_MIGRATION_NOTICE", "Notice carries project closure event type", item)
    check(item["content"]["cta_label"] == "Continue as independent farmer", "Notice carries independent continuation CTA", item["content"])
    check(item["content"]["deeplink_url"].startswith("agrios://project-closure/continue-independent"), "Notice carries Android deeplink", item["content"])
    return feed


def verify_lifecycle_transition(client: TestClient, headers: dict) -> dict:
    before = request_json(client, "GET", f"/api/v1/farmers/by-mobile/{SELECTED_MOBILE}?include_form_contract=true&project_id={PROJECT_ID}")
    check(before["farmer_context"]["mode"] == "PROJECT", "Before closure selected farmer is in PROJECT context", before["farmer_context"])
    check(before["farmer_context"]["can_continue_independently"] is False, "Before closure active project blocks independent context")

    patched = request_json(
        client,
        "PATCH",
        f"/api/v1/farmer-project-enrollments/{SELECTED_ENROLLMENT_ID}/status",
        headers,
        {"status": "COMPLETED", "reason": "Project closure migration smoke: farmer may continue independently"},
    )
    check(patched["status"] == "COMPLETED", "Selected enrollment can be completed", patched)

    after = request_json(client, "GET", f"/api/v1/farmers/by-mobile/{SELECTED_MOBILE}?include_form_contract=true&project_id={PROJECT_ID}")
    context = after["farmer_context"]
    check(context["mode"] == "SELF_SERVICE", "After closure farmer hydrates into SELF_SERVICE context", context)
    check(context["can_continue_independently"] is True, "After closure farmer can continue independently", context)
    check(context["active_project_count"] == 0, "After closure active project count is zero", context)
    check(after["summary"]["project_enrollment_count"] == 1, "Completed enrollment remains auditable", after["summary"])

    db = SessionLocal()
    try:
        orphan_parcels = db.execute(text("select id::text from parcels where tenant_id = :tenant_id and farmer_id = :farmer_id and is_active = true"), {"tenant_id": TENANT_ID, "farmer_id": str(SELECTED_FARMER_ID)}).scalars().all()
        cycles = db.query(CropCycle).filter(CropCycle.tenant_id == TENANT_ID, CropCycle.farmer_id == SELECTED_FARMER_ID).count()
        check(len(orphan_parcels) == 1, "Farmer parcel remains linked after project closure", orphan_parcels)
        check(cycles == 1, "Farmer crop cycle remains linked after project closure", cycles)
    finally:
        db.close()

    return {"before_context": before["farmer_context"], "after_context": context, "patched_enrollment": patched}


def main() -> int:
    print("=" * 72)
    print("ANDROID FPO PROJECT CLOSURE MIGRATION NOTICE VERIFIER")
    print("=" * 72)
    baseline = verify_db_baseline()
    db = SessionLocal()
    cleanup_campaign(db)
    admin_user, admin_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
    db.close()

    try:
        client = TestClient(app)
        notice = create_publish_generate_notice(client, admin_headers, admin_user.id)
        farmer_feed = verify_farmer_notice_feed(client)
        lifecycle = verify_lifecycle_transition(client, admin_headers)
        result = {
            "schema_version": "android_fpo_project_closure_migration_notice_verification.v1",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "baseline": baseline,
            "notice": {
                "delivery_count": notice["delivery_summary"]["total"],
                "selected_farmer_notice_count": farmer_feed["count"],
                "event_type": farmer_feed["broadcasts"][0]["campaign"]["metadata"]["event_type"],
                "cta_label": farmer_feed["broadcasts"][0]["content"]["cta_label"],
                "deeplink_url": farmer_feed["broadcasts"][0]["content"]["deeplink_url"],
            },
            "lifecycle": lifecycle,
            "readiness": {
                "ready_for_android_project_closure_notice_maestro": True,
                "backend_triggered_closure_notice_covered": True,
                "farmer_independent_continuation_covered": True,
                "project_closure_does_not_delete_farmer_data": True,
            },
            "restore_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply",
        }
    finally:
        cleanup_db = SessionLocal()
        try:
            restore_selected_enrollment(cleanup_db)
            cleanup_campaign(cleanup_db)
            delete_test_admin(cleanup_db, admin_user.id)
        finally:
            cleanup_db.close()

    print("=" * 72)
    print("ANDROID FPO PROJECT CLOSURE MIGRATION NOTICE VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())