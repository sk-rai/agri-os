#!/usr/bin/env python3
"""Smoke test admin localization API contract."""

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

        summary = client.get("/api/v1/admin/localization/summary", headers=headers)
        check(summary.status_code == 200, "summary returns 200", summary.text)
        summary_body = summary.json()
        check(summary_body["active_override_count"] >= 0, "summary includes active override count", summary_body)

        listing = client.get(
            "/api/v1/admin/localization/content-keys?language_code=kn&q=activity_log.title&include_overrides=true&limit=10",
            headers=headers,
        )
        check(listing.status_code == 200, "content key listing returns 200", listing.text)
        listing_body = listing.json()
        check(listing_body["count"] >= 1, "listing returns at least one key", listing_body)

        key = listing_body["content_keys"][0]
        known_sources = {"EN_FALLBACK", "PLATFORM_DEFAULT", "TENANT_OVERRIDE", "PROJECT_OVERRIDE"}
        check(key["effective"]["source"] in known_sources, "effective source is known", key)
        content_key_id = key["id"]

        override_text = f"Kannada smoke override {uuid.uuid4().hex[:8]}"
        upsert = client.post(
            f"/api/v1/admin/localization/content-keys/{content_key_id}/overrides",
            headers=headers,
            json={
                "language_code": "kn",
                "override_text": override_text,
                "review_status": "PUBLISHED",
                "review_notes": "Smoke test Kannada override",
                "reason": "Admin localization API smoke test",
            },
        )
        check(upsert.status_code == 200, "override upsert returns 200", upsert.text)
        upsert_body = upsert.json()
        check(upsert_body["override"]["override_text"] == override_text, "upsert stores override text", upsert_body)
        override_id = upsert_body["override"]["id"]

        after = client.get(
            "/api/v1/admin/localization/content-keys?language_code=kn&q=activity_log.title&include_overrides=true&limit=10",
            headers=headers,
        )
        check(after.status_code == 200, "listing after override returns 200", after.text)
        after_key = after.json()["content_keys"][0]
        check(after_key["effective"]["text"] == override_text, "effective text uses override", after_key)
        check(after_key["effective"]["source"] == "TENANT_OVERRIDE", "effective source is tenant override", after_key)

        deleted = client.request(
            "DELETE",
            f"/api/v1/admin/localization/overrides/{override_id}",
            headers=headers,
            json={"reason": "Smoke test cleanup"},
        )
        check(deleted.status_code == 200, "override deactivate returns 200", deleted.text)

        final = client.get(
            "/api/v1/admin/localization/content-keys?language_code=kn&q=activity_log.title&include_overrides=true&limit=10",
            headers=headers,
        )
        check(final.status_code == 200, "listing after deactivate returns 200", final.text)
        final_key = final.json()["content_keys"][0]
        check(final_key["effective"]["source"] in {"EN_FALLBACK", "PLATFORM_DEFAULT"}, "effective source falls back after deactivate", final_key)

        print("=" * 72)
        print("Admin localization API smoke validated")
        print("=" * 72)
        return 0
    finally:
        if admin_user is not None:
            delete_test_admin(db, admin_user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
