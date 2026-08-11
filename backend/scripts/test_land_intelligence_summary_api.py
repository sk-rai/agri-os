#!/usr/bin/env python3
"""Smoke test land-intelligence summary runtime and admin override API."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


TENANT_ID = "default"
PIN_CODE = "560001"


def check(condition: bool, label: str, payload=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if payload is not None:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")
    if payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main() -> int:
    client = TestClient(app)
    db = SessionLocal()
    admin_user = None

    try:
        admin_user, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT_ID)

        default_response = client.get(
            f"/api/v1/profile/land-intelligence-summary?pin_code={PIN_CODE}&season_code=KHARIF&crop_code=RICE&language_code=en",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(default_response.status_code == 200, "runtime default summary returns 200", default_response.text)
        default_body = default_response.json()
        check(default_body["summary_source"] == "DEFAULT_GENERATED", "runtime summary starts from generated default", default_body)
        check(default_body["android_contract"]["display_as_informational_only"] is True, "runtime contract is informational", default_body["android_contract"])

        override_title = f"Custom land summary {uuid.uuid4().hex[:8]}"
        override_payload = {
            "title": {"en": override_title},
            "subtitle": {"en": "Company reviewed local guidance"},
            "cards": [
                {"key": "region", "title": {"en": "Region"}, "value": {"en": "Bengaluru field demo"}, "detail": {"en": "Editable company summary."}},
                {"key": "soil_water", "title": {"en": "Soil & water"}, "value": {"en": "Check irrigation"}, "detail": {"en": "Ask farmer about water availability."}},
            ],
            "main_crops": [{"crop_code": "RICE", "label": {"en": "Rice"}, "reason": {"en": "Project-preferred crop."}}],
            "alternate_crops": [{"crop_code": "MAIZE", "label": {"en": "Maize"}, "reason": {"en": "Backup option."}}],
            "caveats": [{"en": "Human review required for final advisory."}],
            "version": "test-v1",
        }

        upsert = client.post(
            "/api/v1/admin/land-intelligence-summaries/overrides",
            headers=headers,
            json={
                "scope_type": "PIN",
                "scope_code": PIN_CODE,
                "language_code": "en",
                "summary_payload": override_payload,
                "review_status": "PUBLISHED",
                "review_notes": "Smoke test override",
                "reason": "Land intelligence summary API smoke",
            },
        )
        check(upsert.status_code == 200, "admin override upsert returns 200", upsert.text)
        upsert_body = upsert.json()
        override_id = upsert_body["override"]["id"]
        check(upsert_body["effective"]["summary_source"] == "TENANT_OVERRIDE", "admin effective source is tenant override", upsert_body["effective"])

        runtime_after = client.get(
            f"/api/v1/profile/land-intelligence-summary?pin_code={PIN_CODE}&season_code=KHARIF&crop_code=RICE&language_code=en",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(runtime_after.status_code == 200, "runtime after override returns 200", runtime_after.text)
        runtime_body = runtime_after.json()
        check(runtime_body["summary_source"] == "TENANT_OVERRIDE", "runtime uses tenant override", runtime_body)
        check(runtime_body["summary_payload"]["title"]["en"] == override_title, "runtime returns override payload", runtime_body["summary_payload"])

        admin_effective = client.get(
            f"/api/v1/admin/land-intelligence-summaries/effective?scope_type=PIN&scope_code={PIN_CODE}&language_code=en&season_code=KHARIF&crop_code=RICE",
            headers=headers,
        )
        check(admin_effective.status_code == 200, "admin effective summary returns 200", admin_effective.text)
        check(admin_effective.json()["effective_override"]["id"] == override_id, "admin effective exposes override id", admin_effective.json())

        deleted = client.request(
            "DELETE",
            f"/api/v1/admin/land-intelligence-summaries/overrides/{override_id}",
            headers=headers,
            json={"reason": "Smoke cleanup"},
        )
        check(deleted.status_code == 200, "admin override deactivate returns 200", deleted.text)

        final_response = client.get(
            f"/api/v1/profile/land-intelligence-summary?pin_code={PIN_CODE}&season_code=KHARIF&crop_code=RICE&language_code=en",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(final_response.status_code == 200, "runtime final summary returns 200", final_response.text)
        check(final_response.json()["summary_source"] == "DEFAULT_GENERATED", "runtime returns to default after deactivate", final_response.json())

        print("=" * 72)
        print("Land intelligence summary API smoke validated")
        print("=" * 72)
        print(json.dumps({
            "schema_version": "land_intelligence_summary_api_smoke.v1",
            "tenant_id": TENANT_ID,
            "scope_type": "PIN",
            "scope_code": PIN_CODE,
            "override_lifecycle": "DEFAULT_GENERATED -> TENANT_OVERRIDE -> DEFAULT_GENERATED",
            "db_writes_made": True,
            "external_calls_made": False,
            "ready_for_admin_screen": True,
            "ready_for_android_informational_card": True,
        }, indent=2, sort_keys=True))
        return 0
    finally:
        if admin_user is not None:
            delete_test_admin(db, admin_user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
