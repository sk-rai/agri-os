"""Prepare and verify Android broadcast audience targeting edge cases.

Creates deterministic published campaigns for:
- CROP=RICE
- LOCATION=FPO Rampur
- dynamic active STAGE code for farmer 06
- unsupported ROLE rule, accepted in config but producing zero deliveries

The script verifies generated delivery cohorts and Android-visible farmer feeds.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import distinct

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel
from app.modules.media.models import BroadcastAuditEvent, BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery
from app.modules.workflow.models import CropCycle, CropStageInstance
from scripts.prepare_android_fpo_multi_village_workflow import PROJECT_ID, TENANT_ID, farmer_id

ACTOR_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")
RICE_INCLUDED_FARMER_ID = farmer_id(1)
RICE_EXCLUDED_FARMER_ID = farmer_id(6)
LOCATION_INCLUDED_FARMER_ID = farmer_id(1)
LOCATION_EXCLUDED_FARMER_ID = farmer_id(6)
STAGE_SEED_FARMER_ID = farmer_id(6)
UNSUPPORTED_CHECK_FARMER_ID = farmer_id(1)

CAMPAIGNS = {
    "crop_rice": {
        "id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002990"),
        "title": "Rice crop audience advisory",
        "content_title": "Rice farmers advisory",
        "body": "This advisory should reach active Rice crop-cycle farmers only.",
        "rule_type": "CROP",
        "values": ["RICE"],
    },
    "location_rampur": {
        "id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002991"),
        "title": "Rampur village audience advisory",
        "content_title": "Rampur village advisory",
        "body": "This advisory should reach farmers in FPO Rampur only.",
        "rule_type": "LOCATION",
        "values": ["FPO Rampur"],
    },
    "stage_active": {
        "id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002992"),
        "title": "Active stage audience advisory",
        "content_title": "Active stage advisory",
        "body": "This advisory should reach farmers whose active crop cycle has the selected active stage code.",
        "rule_type": "STAGE",
        "values": [],
    },
    "unsupported_role": {
        "id": uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002993"),
        "title": "Unsupported role audience advisory",
        "content_title": "Unsupported role advisory",
        "body": "This advisory config is accepted but should not silently overdeliver while ROLE expansion is unsupported.",
        "rule_type": "ROLE",
        "values": ["FARMER_LEADER"],
    },
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


def campaign_ids() -> list[uuid.UUID]:
    return [row["id"] for row in CAMPAIGNS.values()]


def cleanup_state() -> dict:
    ids = campaign_ids()
    db = SessionLocal()
    try:
        counts = {
            "broadcast_deliveries": db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == TENANT_ID, BroadcastDelivery.campaign_id.in_(ids)).delete(synchronize_session=False),
            "broadcast_audit_events": db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == TENANT_ID, BroadcastAuditEvent.campaign_id.in_(ids)).delete(synchronize_session=False),
            "broadcast_audience_rules": db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == TENANT_ID, BroadcastAudienceRule.campaign_id.in_(ids)).delete(synchronize_session=False),
            "broadcast_contents": db.query(BroadcastContent).filter(BroadcastContent.tenant_id == TENANT_ID, BroadcastContent.campaign_id.in_(ids)).delete(synchronize_session=False),
            "broadcast_campaigns": db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == TENANT_ID, BroadcastCampaign.id.in_(ids)).delete(synchronize_session=False),
        }
        db.commit()
        return {key: int(value or 0) for key, value in counts.items()}
    finally:
        db.close()


def farmer_label(db, farmer_id_value: uuid.UUID) -> dict:
    farmer = db.query(Farmer).filter(Farmer.tenant_id == TENANT_ID, Farmer.id == farmer_id_value).first()
    return {
        "id": str(farmer.id),
        "display_name": farmer.display_name,
        "mobile_number": farmer.mobile_number,
        "village_name_manual": farmer.village_name_manual,
        "primary_crop_code": farmer.primary_crop_code,
    } if farmer else {"id": str(farmer_id_value), "missing": True}


def expected_audiences() -> dict:
    db = SessionLocal()
    try:
        rice_ids = sorted(
            str(row[0])
            for row in db.query(distinct(CropCycle.farmer_id)).filter(
                CropCycle.tenant_id == TENANT_ID,
                CropCycle.crop_code == "RICE",
                CropCycle.status == "ACTIVE",
            ).all()
            if row[0]
        )
        rampur_ids = sorted({
            str(row.id)
            for row in db.query(Farmer).filter(
                Farmer.tenant_id == TENANT_ID,
                Farmer.status == "ACTIVE",
                Farmer.village_name_manual == "FPO Rampur",
            ).all()
        }.union({
            str(row[0])
            for row in db.query(Parcel.farmer_id).filter(
                Parcel.tenant_id == TENANT_ID,
                Parcel.status == "ACTIVE",
                Parcel.village_name_manual == "FPO Rampur",
            ).distinct().all()
            if row[0]
        }))

        seed_stage = (
            db.query(CropStageInstance.stage_code)
            .join(CropCycle, CropCycle.id == CropStageInstance.crop_cycle_id)
            .filter(
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.status == "ACTIVE",
                CropCycle.tenant_id == TENANT_ID,
                CropCycle.status == "ACTIVE",
                CropCycle.farmer_id == STAGE_SEED_FARMER_ID,
            )
            .order_by(CropStageInstance.stage_order.asc())
            .first()
        )
        check(seed_stage is not None, "Seed farmer has an active stage for STAGE targeting", farmer_label(db, STAGE_SEED_FARMER_ID))
        stage_code = seed_stage[0]
        stage_ids = sorted(
            str(row[0])
            for row in db.query(distinct(CropCycle.farmer_id))
            .join(CropStageInstance, CropStageInstance.crop_cycle_id == CropCycle.id)
            .filter(
                CropCycle.tenant_id == TENANT_ID,
                CropCycle.status == "ACTIVE",
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.status == "ACTIVE",
                CropStageInstance.stage_code == stage_code,
            ).all()
            if row[0]
        )
        stage_excluded = next(str(row[0]) for row in db.query(Farmer.id).filter(Farmer.tenant_id == TENANT_ID, Farmer.status == "ACTIVE").order_by(Farmer.id.asc()).all() if str(row[0]) not in set(stage_ids))

        return {
            "crop_rice": {
                "expected_farmer_ids": rice_ids,
                "included_farmer_id": str(RICE_INCLUDED_FARMER_ID),
                "excluded_farmer_id": str(RICE_EXCLUDED_FARMER_ID),
                "rule_values": ["RICE"],
            },
            "location_rampur": {
                "expected_farmer_ids": rampur_ids,
                "included_farmer_id": str(LOCATION_INCLUDED_FARMER_ID),
                "excluded_farmer_id": str(LOCATION_EXCLUDED_FARMER_ID),
                "rule_values": ["FPO Rampur"],
            },
            "stage_active": {
                "expected_farmer_ids": stage_ids,
                "included_farmer_id": str(STAGE_SEED_FARMER_ID),
                "excluded_farmer_id": stage_excluded,
                "rule_values": [stage_code],
                "stage_code": stage_code,
            },
            "unsupported_role": {
                "expected_farmer_ids": [],
                "included_farmer_id": None,
                "excluded_farmer_id": str(UNSUPPORTED_CHECK_FARMER_ID),
                "rule_values": ["FARMER_LEADER"],
            },
        }
    finally:
        db.close()


def create_campaign(client: TestClient, key: str, expected: dict) -> dict:
    config = CAMPAIGNS[key]
    values = expected[key]["rule_values"]
    created = request_json(
        client,
        "POST",
        "/api/v1/broadcasts",
        expected=201,
        body={
            "id": str(config["id"]),
            "project_id": str(PROJECT_ID),
            "title": config["title"],
            "category": "ADVISORY",
            "priority": "HIGH",
            "created_by": str(ACTOR_ID),
            "metadata": {
                "android_contract": "broadcast_audience_targeting.v1",
                "event_type": f"AUDIENCE_TARGETING_{key.upper()}",
                "targeting_backend_owned": True,
                "audience_match_mode": "ANY",
            },
            "contents": [
                {
                    "language_code": "en",
                    "title": config["content_title"],
                    "body_text": config["body"],
                    "cta_label": "Open targeted advisory",
                    "deeplink_url": f"agrios://broadcast/audience-targeting?campaign_id={config['id']}",
                    "metadata": {"android_copy_role": "audience_targeting_advisory", "targeting_key": key},
                }
            ],
            "audience_rules": [
                {
                    "rule_type": config["rule_type"],
                    "operator": "IN",
                    "values": values,
                    "metadata": {"targeting_key": key, "android_fixture": True},
                }
            ],
        },
    )
    published = request_json(client, "POST", f"/api/v1/broadcasts/{config['id']}/publish", body={"approved_by": str(ACTOR_ID), "reason": f"Android audience targeting smoke publish: {key}"})
    generated = request_json(client, "POST", f"/api/v1/broadcasts/{config['id']}/generate-deliveries")
    check(published["status"] == "PUBLISHED", f"{key} campaign is PUBLISHED", published)
    return {"created": created, "published": published, "generated": generated}


def delivery_farmer_ids(client: TestClient, campaign_id: uuid.UUID) -> list[str]:
    payload = request_json(client, "GET", f"/api/v1/broadcasts/{campaign_id}/deliveries?limit=100")
    return sorted(row["farmer_id"] for row in payload.get("deliveries", []) if row.get("farmer_id"))


def feed_has_campaign(client: TestClient, farmer_id_value: str, campaign_id: uuid.UUID) -> bool:
    payload = request_json(client, "GET", f"/api/v1/broadcasts/farmers/{farmer_id_value}/broadcasts?language_code=en&include_read=true")
    return any(row.get("campaign", {}).get("id") == str(campaign_id) for row in payload.get("broadcasts", []))


def verify_campaign(client: TestClient, key: str, expected: dict) -> dict:
    config = CAMPAIGNS[key]
    expected_ids = expected[key]["expected_farmer_ids"]
    delivered_ids = delivery_farmer_ids(client, config["id"])
    check(delivered_ids == expected_ids, f"{key} delivery cohort matches expected audience", {"expected": expected_ids, "actual": delivered_ids})

    included_id = expected[key].get("included_farmer_id")
    excluded_id = expected[key].get("excluded_farmer_id")
    included_visible = feed_has_campaign(client, included_id, config["id"]) if included_id else False
    excluded_visible = feed_has_campaign(client, excluded_id, config["id"]) if excluded_id else False
    if included_id:
        check(included_visible, f"{key} included farmer sees campaign", {"farmer_id": included_id, "campaign_id": str(config["id"])})
    check(not excluded_visible, f"{key} excluded farmer does not see campaign", {"farmer_id": excluded_id, "campaign_id": str(config["id"])})

    preview = request_json(client, "GET", f"/api/v1/broadcasts/{config['id']}/audience-preview")
    if key == "unsupported_role":
        check(preview.get("unsupported_rule_count") == 1, "Unsupported ROLE rule is reported as unsupported", preview)
        check(preview.get("estimated_farmer_count") == 0, "Unsupported ROLE rule targets zero farmers", preview)
    return {"delivered_farmer_ids": delivered_ids, "included_visible": included_visible, "excluded_visible": excluded_visible, "audience_preview": preview}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID BROADCAST AUDIENCE TARGETING VERIFIER")
    print("=" * 72)

    reset_counts = {}
    if args.reset or args.cleanup:
        reset_counts = cleanup_state()
        check(True, "Cleaned deterministic audience targeting smoke state", reset_counts)
    if args.cleanup:
        print(json.dumps({
            "schema_version": "android_broadcast_audience_targeting_verification.v1",
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "campaign_ids": {key: str(value["id"]) for key, value in CAMPAIGNS.items()},
            "reset": reset_counts,
        }, indent=2, sort_keys=True, default=str))
        return 0

    client = TestClient(app)
    expected = expected_audiences()
    created = {key: create_campaign(client, key, expected) for key in CAMPAIGNS} if args.apply else {}
    verified = {key: verify_campaign(client, key, expected) for key in CAMPAIGNS}

    result = {
        "schema_version": "android_broadcast_audience_targeting_verification.v1",
        "tenant_id": TENANT_ID,
        "project_id": str(PROJECT_ID),
        "campaign_ids": {key: str(value["id"]) for key, value in CAMPAIGNS.items()},
        "reset": reset_counts,
        "expected": expected,
        "created_delivery_counts": {key: (value.get("generated") or {}).get("delivery_summary", {}).get("total") for key, value in created.items()},
        "verified": verified,
        "readiness": {
            "crop_targeting_covered": True,
            "location_targeting_covered": True,
            "stage_targeting_covered": True,
            "unsupported_rule_no_overdelivery_covered": True,
            "included_and_excluded_farmer_feeds_covered": True,
            "ready_for_android_broadcast_audience_targeting_maestro": True,
        },
        "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_broadcast_audience_targeting.py --cleanup",
    }
    print("=" * 72)
    print("ANDROID BROADCAST AUDIENCE TARGETING VERIFIED")
    print("=" * 72)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())