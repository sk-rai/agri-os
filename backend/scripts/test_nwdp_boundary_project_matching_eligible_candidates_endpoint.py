#!/usr/bin/env python3
"""Regression for read-only NWDP boundary project matching eligible candidates endpoint."""

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
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def staging_summary(db):
    return db.execute(text("""
        select
          count(*) as candidates,
          sum(case when is_active then 1 else 0 end) as active_candidates,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidates
        from geography_boundary_crosswalk_candidates
    """)).mappings().one()


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING ELIGIBLE CANDIDATES ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        before = staging_summary(db)

        denied = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates?state_or_ut=Karnataka&limit=5",
            headers={"X-Tenant-ID": "default"},
        )
        check(denied.status_code in {401, 403}, "Unauthenticated eligible-candidates request is denied", denied.text[:500])

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        missing_scope = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates",
            headers=headers,
        )
        check(missing_scope.status_code == 400, "Endpoint requires bounded state or village scope", missing_scope.text[:500])

        response = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates?state_or_ut=Karnataka&limit=5",
            headers=headers,
        )
        data = response.json()

        check(response.status_code == 200, "Admin viewer can query eligible candidates", response.text[:1000])
        check(data["schema_version"] == "nwdp_boundary_project_matching_eligible_candidates.v1", "Schema version is stable", data)
        check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_ELIGIBLE_CANDIDATES", "Endpoint is read-only mode", data)
        check(data["filters"]["state_or_ut"] == "Karnataka", "Endpoint applies state filter", data["filters"])
        check(data["summary"]["eligible_candidate_count"] > 0, "Endpoint finds eligible Karnataka candidates", data["summary"])
        check(data["summary"]["returned_count"] <= 5, "Endpoint honors limit", data["summary"])
        check(data["summary"]["manual_review_excluded"] is True, "Manual review candidates are excluded", data["summary"])
        check(data["summary"]["blocked_excluded"] is True, "Blocked candidates are excluded", data["summary"])
        check(data["summary"]["runtime_tables_written"] is False, "Endpoint writes no runtime tables", data["summary"])
        check(data["summary"]["runtime_spatial_matching_changed"] is False, "Endpoint keeps spatial matching disabled", data["summary"])
        check(data["summary"]["lookup_api_enabled"] is False, "Endpoint keeps lookup disabled", data["summary"])
        check(data["summary"]["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", data["summary"])
        check(data["readiness"]["ready_for_project_matching_apply"] is False, "Endpoint is not project matching apply", data["readiness"])
        check(data["readiness"]["ready_for_runtime_spatial_matching"] is False, "Endpoint is not runtime matching", data["readiness"])
        check(len(data["items"]) > 0, "Endpoint returns eligible rows", data["items"])

        first = data["items"][0]
        check(first["candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Returned rows are direct-code matches", first)
        check(first["review_status"] == "AUTO_CANDIDATE", "Returned rows are auto candidates", first)
        check(first["promotion_status"] == "NOT_PROMOTED", "Returned rows are not promoted", first)
        check(first["proposed_village_id"], "Returned rows include proposed village id", first)

        village_response = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-project-matching/eligible-candidates?village_id={first['proposed_village_id']}&limit=10",
            headers=headers,
        )
        village_data = village_response.json()
        check(village_response.status_code == 200, "Admin viewer can query by village_id", village_response.text[:1000])
        check(village_data["summary"]["eligible_candidate_count"] >= 1, "Village query returns eligible candidates", village_data["summary"])
        check(all(item["proposed_village_id"] == first["proposed_village_id"] for item in village_data["items"]), "Village query is scoped", village_data["items"])

        after = staging_summary(db)
        check(after["candidates"] == before["candidates"], "Endpoint did not create/delete candidates", dict(after))
        check(after["active_candidates"] == 0, "Endpoint did not activate candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Endpoint did not promote candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY PROJECT MATCHING ELIGIBLE CANDIDATES ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
