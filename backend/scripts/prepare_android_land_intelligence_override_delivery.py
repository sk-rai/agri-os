#!/usr/bin/env python3
"""Stateful Android prepare for land-intelligence summary override delivery."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

TENANT_ID = "android-fpo-multi-village-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002001")
PIN_CODE = "560003"
SEASON_CODE = "KHARIF"
CROP_CODE = "MAIZE"
LANGUAGE_CODE = "en"
CONTRACT = "android_land_intelligence_override_delivery.v1"

OVERRIDE_TITLE = "FPO Maize land intelligence override"
OVERRIDE_SUBTITLE = "Backend-published FPO guidance for PIN 560003"
REGION_VALUE = "FPO Harohalli maize cluster"
SOIL_WATER_VALUE = "Check irrigation before fertilizer"
CAVEAT_TEXT = "Informational only: do not block farmer onboarding."

SUMMARY_PAYLOAD = {
    "title": {"en": OVERRIDE_TITLE},
    "subtitle": {"en": OVERRIDE_SUBTITLE},
    "cards": [
        {
            "key": "region",
            "title": {"en": "Region"},
            "value": {"en": REGION_VALUE},
            "detail": {"en": "Company-reviewed FPO land-intelligence summary for the demo maize cluster."},
        },
        {
            "key": "season_weather",
            "title": {"en": "Season & weather"},
            "value": {"en": "KHARIF maize watch"},
            "detail": {"en": "Use backend/provider weather context only as advisory context."},
        },
        {
            "key": "soil_water",
            "title": {"en": "Soil & water"},
            "value": {"en": SOIL_WATER_VALUE},
            "detail": {"en": "Ask farmer about water availability and recent soil test before recommending inputs."},
        },
        {
            "key": "crop_options",
            "title": {"en": "Crop options"},
            "value": {"en": "Maize primary, pulses alternate"},
            "detail": {"en": "Workflow templates remain the source for stage-level recommendations."},
        },
    ],
    "main_crops": [
        {"crop_code": "MAIZE", "label": {"en": "Maize"}, "reason": {"en": "Selected FPO project crop for PIN 560003."}},
        {"crop_code": "RICE", "label": {"en": "Rice"}, "reason": {"en": "Possible only where water is available."}},
    ],
    "alternate_crops": [
        {"crop_code": "PULSES", "label": {"en": "Pulses"}, "reason": {"en": "Lower-input alternate for risk spread."}},
        {"crop_code": "FODDER", "label": {"en": "Fodder"}, "reason": {"en": "Useful alternate where livestock demand exists."}},
    ],
    "caveats": [{"en": CAVEAT_TEXT}],
    "version": "android-smoke-v1",
    "android_contract": CONTRACT,
}


def check(condition: bool, label: str, payload=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str) if not isinstance(payload, str) else payload)
    if not condition:
        raise AssertionError(label)


def cleanup_state() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                update land_intelligence_summary_overrides
                set is_active = false,
                    metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('cleanup_reason', 'Android land-intelligence override smoke cleanup'),
                    updated_at = now()
                where tenant_id = :tenant_id
                  and is_active = true
                  and metadata ->> 'android_contract' = :contract
                returning id::text
            """),
            {"tenant_id": TENANT_ID, "contract": CONTRACT},
        ).mappings().all()
        db.commit()
        return {"deactivated_overrides": len(rows), "override_ids": [row["id"] for row in rows]}
    finally:
        db.close()


def get_json(client: TestClient, path: str, *, headers: dict | None = None) -> dict:
    response = client.get(path, headers=headers or {"X-Tenant-ID": TENANT_ID})
    check(response.status_code == 200, f"GET {path} returns 200", response.text[:1400])
    return response.json()


def verify_summary(client: TestClient, *, expect_source: str = "PROJECT_OVERRIDE") -> dict:
    path = (
        f"/api/v1/profile/land-intelligence-summary?pin_code={PIN_CODE}"
        f"&season_code={SEASON_CODE}&crop_code={CROP_CODE}&language_code={LANGUAGE_CODE}&project_id={PROJECT_ID}"
    )
    summary = get_json(client, path, headers={"X-Tenant-ID": TENANT_ID})
    check(summary["summary_source"] == expect_source, f"Runtime summary source is {expect_source}", summary)
    check(summary["android_contract"]["display_as_informational_only"] is True, "Runtime contract is informational only", summary["android_contract"])
    check(summary["android_contract"]["do_not_block_onboarding"] is True, "Runtime contract does not block onboarding", summary["android_contract"])
    if expect_source != "DEFAULT_GENERATED":
        payload = summary["summary_payload"]
        check(payload["title"]["en"] == OVERRIDE_TITLE, "Runtime title uses project override", payload["title"])
        check(payload["subtitle"]["en"] == OVERRIDE_SUBTITLE, "Runtime subtitle uses project override", payload["subtitle"])
        check(len(payload.get("cards") or []) == 4, "Runtime returns four informational cards", payload.get("cards"))
        cards = {row["key"]: row for row in payload["cards"]}
        check(cards["region"]["value"]["en"] == REGION_VALUE, "Region card uses override value", cards["region"])
        check(cards["soil_water"]["value"]["en"] == SOIL_WATER_VALUE, "Soil-water card uses override value", cards["soil_water"])
        check(payload["main_crops"][0]["crop_code"] == CROP_CODE, "Main crop starts with selected crop", payload["main_crops"])
        check(payload["caveats"][0]["en"] == CAVEAT_TEXT, "Caveat remains informational", payload["caveats"])
    return summary


def tag_override_metadata(override_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text("""
                update land_intelligence_summary_overrides
                set metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
                    'android_contract', :contract,
                    'android_flow', 'land_intelligence_override_delivery',
                    'pin_code', :pin_code,
                    'project_id', :project_id,
                    'crop_code', :crop_code,
                    'season_code', :season_code
                )
                where id = cast(:override_id as uuid)
            """),
            {
                "contract": CONTRACT,
                "pin_code": PIN_CODE,
                "project_id": str(PROJECT_ID),
                "crop_code": CROP_CODE,
                "season_code": SEASON_CODE,
                "override_id": override_id,
            },
        )
        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID LAND INTELLIGENCE OVERRIDE DELIVERY PREPARE")
    print("=" * 72)

    reset = {}
    if args.reset or args.cleanup:
        reset = cleanup_state()
        check(True, "Cleaned deterministic Android land-intelligence overrides", reset)
    if args.cleanup:
        print(json.dumps({
            "schema_version": CONTRACT,
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "reset": reset,
        }, indent=2, sort_keys=True))
        return 0

    client = TestClient(app)
    db = SessionLocal()
    admin_user = None
    try:
        admin_user, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
        created_override_id = None
        if args.apply:
            upsert = client.post(
                "/api/v1/admin/land-intelligence-summaries/overrides",
                headers=headers,
                json={
                    "tenant_id": TENANT_ID,
                    "project_id": str(PROJECT_ID),
                    "scope_type": "PIN",
                    "scope_code": PIN_CODE,
                    "language_code": LANGUAGE_CODE,
                    "summary_payload": SUMMARY_PAYLOAD,
                    "review_status": "PUBLISHED",
                    "review_notes": "Android land-intelligence override delivery smoke",
                    "reason": f"{CONTRACT}:project-pin-override",
                },
            )
            check(upsert.status_code == 200, "Admin project override upsert returns 200", upsert.text[:1600])
            upsert_body = upsert.json()
            created_override_id = upsert_body["override"]["id"]
            tag_override_metadata(created_override_id)
            check(upsert_body["effective"]["summary_source"] == "PROJECT_OVERRIDE", "Admin effective summary is project override", upsert_body["effective"])

        summary = verify_summary(client, expect_source="PROJECT_OVERRIDE")
        result = {
            "schema_version": CONTRACT,
            "mode": "APPLY" if args.apply else "VERIFY",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "scope_type": "PIN",
            "scope_code": PIN_CODE,
            "language_code": LANGUAGE_CODE,
            "season_code": SEASON_CODE,
            "crop_code": CROP_CODE,
            "created_override_id": created_override_id,
            "reset": reset,
            "verified": {
                "summary_source": summary["summary_source"],
                "title": summary["summary_payload"]["title"]["en"],
                "card_count": len(summary["summary_payload"].get("cards") or []),
                "main_crop_count": len(summary["summary_payload"].get("main_crops") or []),
                "alternate_crop_count": len(summary["summary_payload"].get("alternate_crops") or []),
                "informational_only": summary["android_contract"]["display_as_informational_only"],
                "do_not_block_onboarding": summary["android_contract"]["do_not_block_onboarding"],
            },
            "expected": {
                "title": OVERRIDE_TITLE,
                "subtitle": OVERRIDE_SUBTITLE,
                "region_value": REGION_VALUE,
                "soil_water_value": SOIL_WATER_VALUE,
                "caveat": CAVEAT_TEXT,
            },
            "readiness": {
                "admin_project_override_covered": True,
                "android_runtime_summary_override_covered": True,
                "informational_only_contract_covered": True,
                "main_and_alternate_crops_covered": True,
                "ready_for_android_land_intelligence_override_maestro": True,
            },
            "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --cleanup",
        }
        print("=" * 72)
        print("ANDROID LAND INTELLIGENCE OVERRIDE DELIVERY READY")
        print("=" * 72)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        if admin_user is not None:
            delete_test_admin(db, admin_user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
