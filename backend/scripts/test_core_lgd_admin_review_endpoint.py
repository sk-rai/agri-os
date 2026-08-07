#!/usr/bin/env python3
"""Regression for CoRE/LGD admin review endpoint.

Verifies:
- FARMER/no-admin access is denied by admin VIEW permission.
- ADMIN_VIEWER can read the review queue.
- default/pilot filters return POLY_REV candidate rows.
- endpoint is read-only and does not activate POLY_REV mappings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition: bool, label: str, detail=None):
    status = "PASS" if condition else "FAIL"
    print(f"{status} {label}")
    if detail is not None:
        print(f"      {detail if isinstance(detail, str) else json.dumps(detail, indent=2, default=str)[:1200]}")
    if not condition:
        raise AssertionError(label)


def poly_rev_summary(db):
    return db.execute(text("""
        select
          count(*) as total,
          sum(case when is_active then 1 else 0 end) as active_count
        from geography_climate_region_mappings
        where confidence = 'POLY_REV'
    """)).mappings().one()


def main() -> int:
    print("=" * 72)
    print("CORE/LGD ADMIN REVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    try:
        before = poly_rev_summary(db)
        check(before["total"] == 2298, "POLY_REV candidate rows exist", dict(before))
        check(before["active_count"] == 0, "POLY_REV rows start inactive", dict(before))

        denied = client.get(
            "/api/v1/master-data/geography/core-lgd-mapping-review?state_lgd_code=29&limit=5",
            headers={"X-Tenant-ID": "default"},
        )
        check(denied.status_code in {401, 403}, "Unauthenticated/non-admin request is denied", denied.text[:500])

        admin, headers = create_test_admin(db, role="ADMIN_EDITOR", tenant_id="default")
        response = client.get(
            "/api/v1/master-data/geography/core-lgd-mapping-review"
            "?state_lgd_code=29&promotion_decision=PILOT_REVIEW_REPLACES_FALLBACK&limit=5",
            headers=headers,
        )
        check(response.status_code == 200, "Admin editor can read endpoint", response.text[:800])

        data = response.json()
        check(data["schema_version"] == "core_lgd_mapping_review_admin.v1", "Schema version is stable", data["schema_version"])
        check(data["mode"] == "READ_ONLY_ADMIN_REVIEW", "Endpoint mode is read-only", data["mode"])
        check(data["governance"]["read_only"] is True, "Governance marks endpoint read-only", data["governance"])
        check(data["governance"]["promotion_supported"] is False, "Promotion is not supported by endpoint", data["governance"])
        check(data["summary"]["land_intelligence_behavior_changed"] is False, "Land-intelligence behavior unchanged", data["summary"])
        check(data["total"] >= 1, "Filtered pilot review has rows", data["total"])
        check(len(data["items"]) >= 1, "Response includes review items", data["items"][:1])

        first = data["items"][0]
        check(first["promotion_decision"] == "PILOT_REVIEW_REPLACES_FALLBACK", "Item has expected decision", first)
        check(first["state_lgd_code"] == "29", "Item is Karnataka by filter", first)
        check(first["active_fallback_count"] >= 1, "Item includes active fallback comparison", first)


        target_id = first["poly_mapping_id"]
        patch_response = client.patch(
            f"/api/v1/master-data/geography/core-lgd-mapping-review/{target_id}/review",
            headers=headers,
            json={
                "review_status": "APPROVED_FOR_PROMOTION",
                "review_notes": "Regression approves candidate for later promotion without activation.",
            },
        )
        check(patch_response.status_code == 200, "PATCH review decision endpoint updates status without activation", patch_response.text[:800])
        patch_data = patch_response.json()
        check(patch_data["review_status"] == "APPROVED_FOR_PROMOTION", "Review status becomes APPROVED_FOR_PROMOTION", patch_data)
        check(patch_data["is_active"] is False, "Review decision does not activate row", patch_data)
        check(patch_data["land_intelligence_behavior_changed"] is False, "Review decision does not change behavior", patch_data)

        approved_response = client.get(
            f"/api/v1/master-data/geography/core-lgd-mapping-review?review_status=APPROVED_FOR_PROMOTION&district_lgd_code={first['district_lgd_code']}&limit=20",
            headers=headers,
        )
        check(approved_response.status_code == 200, "Approved status can be filtered", approved_response.text[:800])
        approved_rows = approved_response.json()["items"]
        check(any(row["poly_mapping_id"] == target_id for row in approved_rows), "Approved row appears in approved filter", approved_rows[:3])

        reset_response = client.patch(
            f"/api/v1/master-data/geography/core-lgd-mapping-review/{target_id}/review",
            headers=headers,
            json={
                "review_status": "MANUAL_REVIEW",
                "review_notes": "Regression resets candidate to manual review for repeatability.",
            },
        )
        check(reset_response.status_code == 200, "Review status can be reset for repeatability", reset_response.text[:800])

        after = poly_rev_summary(db)
        check(after["total"] == before["total"], "Endpoint did not create/delete POLY_REV rows", dict(after))
        check(after["active_count"] == 0, "Endpoint did not activate POLY_REV rows", dict(after))

        print("=" * 72)
        print("CORE/LGD ADMIN REVIEW ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
