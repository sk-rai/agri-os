#!/usr/bin/env python3
"""Stateful Android prepare for admin localization override delivery.

Creates deterministic Kannada overrides for backend-driven Android payloads and leaves
those overrides active until --cleanup is run.
"""

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
ACTOR_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000002099")
LANGUAGE_CODE = "kn"
CONTRACT = "android_localization_override_delivery.v1"

FORM_TITLE_KEY = "profile_form.activity_log.title"
OPTION_LABEL_KEY = "profile_option_set.languages.option.kn.label"
FORM_TITLE_OVERRIDE = "ಚಟುವಟಿಕೆ ದಾಖಲಿಸಿ - Android override smoke"
OPTION_LABEL_OVERRIDE = "ಕನ್ನಡ - Android override smoke"


def check(condition: bool, label: str, payload=None) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str) if not isinstance(payload, str) else payload)
    if not condition:
        raise AssertionError(label)


def content_key_id(db, content_key: str) -> str:
    row = db.execute(
        text("""
            select id::text
            from localized_content_keys
            where content_key = :content_key
              and is_active = true
            limit 1
        """),
        {"content_key": content_key},
    ).mappings().first()
    if not row:
        raise AssertionError(f"Missing localized content key: {content_key}. Run seed_admin_localization_content_keys.py --apply first.")
    return row["id"]


def cleanup_state() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                update localized_content_overrides
                set is_active = false,
                    metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('cleanup_reason', 'Android localization override smoke cleanup'),
                    updated_at = now()
                where tenant_id = :tenant_id
                  and language_code = :language_code
                  and is_active = true
                  and metadata ->> 'android_contract' = :contract
                returning id::text
            """),
            {"tenant_id": TENANT_ID, "language_code": LANGUAGE_CODE, "contract": CONTRACT},
        ).mappings().all()
        db.commit()
        return {"deactivated_overrides": len(rows), "override_ids": [row["id"] for row in rows]}
    finally:
        db.close()


def upsert_override(client: TestClient, headers: dict, key_id: str, content_key: str, text_value: str) -> dict:
    response = client.post(
        f"/api/v1/admin/localization/content-keys/{key_id}/overrides",
        headers=headers,
        json={
            "tenant_id": TENANT_ID,
            "project_id": None,
            "language_code": LANGUAGE_CODE,
            "override_text": text_value,
            "review_status": "PUBLISHED",
            "review_notes": "Android localization override delivery smoke",
            "reason": f"{CONTRACT}:{content_key}",
        },
    )
    check(response.status_code == 200, f"Published override for {content_key}", response.text[:1200])
    payload = response.json()
    override_id = payload["override"]["id"]
    db = SessionLocal()
    try:
        db.execute(
            text("""
                update localized_content_overrides
                set metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
                    'android_contract', :contract,
                    'android_flow', 'localization_override_delivery',
                    'content_key', :content_key,
                    'project_id', :project_id,
                    'scope', 'TENANT'
                )
                where id = cast(:override_id as uuid)
            """),
            {"contract": CONTRACT, "content_key": content_key, "project_id": str(PROJECT_ID), "override_id": override_id},
        )
        db.commit()
    finally:
        db.close()
    return payload


def get_json(client: TestClient, path: str, *, headers: dict | None = None) -> dict:
    response = client.get(path, headers=headers or {"X-Tenant-ID": TENANT_ID})
    check(response.status_code == 200, f"GET {path} returns 200", response.text[:1200])
    return response.json()


def verify_android_payloads(client: TestClient) -> dict:
    form = get_json(client, "/api/v1/forms/activity_log", headers={"X-Tenant-ID": TENANT_ID})
    check(form["title"][LANGUAGE_CODE] == FORM_TITLE_OVERRIDE, "Activity-log form title uses Kannada override", form["title"])

    options = get_json(client, "/api/v1/forms/options/languages", headers={"X-Tenant-ID": TENANT_ID})
    kn_options = [row for row in options.get("options", []) if row.get("value") == "kn"]
    check(len(kn_options) == 1, "Kannada language option exists", options.get("options"))
    check(kn_options[0]["label"][LANGUAGE_CODE] == OPTION_LABEL_OVERRIDE, "Language option label uses Kannada override", kn_options[0])

    bootstrap = get_json(client, f"/api/v1/app-config/bootstrap?project_id={PROJECT_ID}", headers={"X-Tenant-ID": TENANT_ID})
    forms = {row["form_id"]: row for row in bootstrap.get("forms", [])}
    check(forms["activity_log"]["title"][LANGUAGE_CODE] == FORM_TITLE_OVERRIDE, "Bootstrap forms list carries Kannada override", forms["activity_log"])
    return {"form": form, "options": options, "bootstrap_activity_log": forms["activity_log"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("ANDROID LOCALIZATION OVERRIDE DELIVERY PREPARE")
    print("=" * 72)

    reset = {}
    if args.reset or args.cleanup:
        reset = cleanup_state()
        check(True, "Cleaned deterministic Android localization overrides", reset)
    if args.cleanup:
        print(json.dumps({
            "schema_version": CONTRACT,
            "mode": "CLEANUP",
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "reset": reset,
        }, indent=2, sort_keys=True))
        return 0

    db = SessionLocal()
    admin_user = None
    try:
        form_key_id = content_key_id(db, FORM_TITLE_KEY)
        option_key_id = content_key_id(db, OPTION_LABEL_KEY)
        admin_user, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)
        client = TestClient(app)

        created = {}
        if args.apply:
            created[FORM_TITLE_KEY] = upsert_override(client, headers, form_key_id, FORM_TITLE_KEY, FORM_TITLE_OVERRIDE)
            created[OPTION_LABEL_KEY] = upsert_override(client, headers, option_key_id, OPTION_LABEL_KEY, OPTION_LABEL_OVERRIDE)

        verified = verify_android_payloads(client)
        result = {
            "schema_version": CONTRACT,
            "mode": "APPLY" if args.apply else "VERIFY",
            "tenant_id": TENANT_ID,
            "project_id": None,
            "language_code": LANGUAGE_CODE,
            "content_keys": {
                "form_title": FORM_TITLE_KEY,
                "option_label": OPTION_LABEL_KEY,
            },
            "expected": {
                "form_title_override": FORM_TITLE_OVERRIDE,
                "option_label_override": OPTION_LABEL_OVERRIDE,
                "fallback_rule": "labels[currentLanguageCode] ?: labels['en']",
            },
            "reset": reset,
            "created_override_ids": [payload["override"]["id"] for payload in created.values()],
            "verified": {
                "form_title_kn": verified["form"]["title"][LANGUAGE_CODE],
                "option_label_kn": [row for row in verified["options"]["options"] if row["value"] == "kn"][0]["label"][LANGUAGE_CODE],
                "bootstrap_title_kn": verified["bootstrap_activity_log"]["title"][LANGUAGE_CODE],
                "localization_overrides_applied": verified["bootstrap_activity_log"].get("metadata", {}).get("localization_overrides_applied"),
                "metadata_count_informational": True,
            },
            "readiness": {
                "admin_published_override_covered": True,
                "android_form_payload_override_covered": True,
                "android_option_payload_override_covered": True,
                "bootstrap_override_delivery_covered": True,
                "ready_for_android_localization_override_maestro": True,
            },
            "cleanup_command": "cd ~/projects/farmint/backend && ../venv/bin/python scripts/prepare_android_localization_override_delivery.py --cleanup",
        }
        print("=" * 72)
        print("ANDROID LOCALIZATION OVERRIDE DELIVERY READY")
        print("=" * 72)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        if admin_user is not None:
            delete_test_admin(db, admin_user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
