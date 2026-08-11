#!/usr/bin/env python3
"""Verify published admin localization overrides flow into Android-facing payloads."""

from __future__ import annotations

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


TENANT_ID = "default"


def check(condition: bool, label: str, payload=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if payload is not None:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")
    if payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def get_key_id(db, content_key: str) -> str:
    row = db.execute(
        text("select id::text from localized_content_keys where content_key = :content_key and is_active = true"),
        {"content_key": content_key},
    ).mappings().first()
    if not row:
        raise AssertionError(f"Missing seeded content key: {content_key}")
    return row["id"]


def main() -> int:
    client = TestClient(app)
    db = SessionLocal()
    admin_user = None
    created_override_ids: list[str] = []

    try:
        admin_user, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)

        form_title_key = get_key_id(db, "profile_form.farmer_registration.title")
        option_label_key = get_key_id(db, "profile_option_set.languages.option.kn.label")

        form_override = f"Farmer Registration KN override {uuid.uuid4().hex[:8]}"
        option_override = f"Kannada option override {uuid.uuid4().hex[:8]}"

        for key_id, override_text in [(form_title_key, form_override), (option_label_key, option_override)]:
            response = client.post(
                f"/api/v1/admin/localization/content-keys/{key_id}/overrides",
                headers=headers,
                json={
                    "language_code": "kn",
                    "override_text": override_text,
                    "review_status": "PUBLISHED",
                    "reason": "Android delivery smoke test",
                },
            )
            check(response.status_code == 200, "override upsert returns 200", response.text)
            created_override_ids.append(response.json()["override"]["id"])

        form = client.get("/api/v1/forms/farmer_registration", headers={"X-Tenant-ID": TENANT_ID})
        check(form.status_code == 200, "form endpoint returns 200", form.text)
        form_body = form.json()
        check(form_body["title"]["kn"] == form_override, "form endpoint overlays title override", form_body["title"])

        option = client.get("/api/v1/forms/options/languages", headers={"X-Tenant-ID": TENANT_ID})
        check(option.status_code == 200, "option-set endpoint returns 200", option.text)
        option_body = option.json()
        kn_options = [item for item in option_body["options"] if item["value"] == "kn"]
        check(len(kn_options) == 1, "language option kn exists", option_body["options"])
        check(kn_options[0]["label"]["kn"] == option_override, "option-set endpoint overlays option label override", kn_options[0])

        bootstrap = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": TENANT_ID})
        check(bootstrap.status_code == 200, "app bootstrap returns 200", bootstrap.text)
        bootstrap_body = bootstrap.json()
        check(
            bootstrap_body["profile_forms"]["farmer_registration"]["title"]["kn"] == form_override,
            "bootstrap profile form summary overlays title override",
            bootstrap_body["profile_forms"]["farmer_registration"],
        )
        forms = {row["form_id"]: row for row in bootstrap_body["forms"]}
        check(forms["farmer_registration"]["title"]["kn"] == form_override, "bootstrap forms list overlays title override", forms["farmer_registration"])

        print("=" * 72)
        print("Android localization override delivery validated")
        print("=" * 72)
        print(json.dumps({
            "schema_version": "android_localization_override_delivery.v1",
            "tenant_id": TENANT_ID,
            "form_title_override_delivered": True,
            "option_label_override_delivered": True,
            "android_label_resolution": "labels[currentLanguageCode] ?: labels['en']",
            "db_writes_made": True,
            "external_calls_made": False,
        }, indent=2, sort_keys=True))
        return 0
    finally:
        for override_id in created_override_ids:
            client.request(
                "DELETE",
                f"/api/v1/admin/localization/overrides/{override_id}",
                headers=headers,
                json={"reason": "Android delivery smoke cleanup"},
            )
        if admin_user is not None:
            delete_test_admin(db, admin_user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
