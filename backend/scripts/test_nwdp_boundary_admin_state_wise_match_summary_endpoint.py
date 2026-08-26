#!/usr/bin/env python3
"""Regression for read-only NWDP boundary state-wise match summary endpoint."""

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
        print(f"      {detail if isinstance(detail, str) else json.dumps(detail, indent=2, default=str)[:1600]}")
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
    print("NWDP BOUNDARY ADMIN STATE-WISE MATCH SUMMARY ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        before = staging_summary(db)

        denied = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-state-wise-match-summary",
            headers={"X-Tenant-ID": "default"},
        )
        check(denied.status_code in {401, 403}, "Unauthenticated state-wise summary is denied", denied.text[:500])

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        response = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-state-wise-match-summary",
            headers=headers,
        )
        data = response.json()

        check(response.status_code == 200, "Admin viewer can read state-wise summary", response.text[:800])
        check(data["schema_version"] == "nwdp_boundary_admin_state_wise_match_summary.v1", "Schema version is stable", data)
        check(data["healthy"] is True, "Summary is healthy", data)
        check(data["totals"]["state_count"] == 36, "Summary sees 36 states/UTs", data["totals"])
        check(data["totals"]["source_features"] == 654285, "Summary sees all source features", data["totals"])
        check(data["totals"]["candidates"] == 654285, "Summary sees all candidates", data["totals"])
        check(data["totals"]["future_match_ready_candidates"] > 0, "Summary reports future match-ready candidates", data["totals"])
        check(data["totals"]["manual_review_candidates"] > 0, "Summary reports manual review queue", data["totals"])
        check(data["totals"]["blocked_candidates"] > 0, "Summary reports blocked queue", data["totals"])
        check(data["totals"]["active_source_features"] == 0, "Summary keeps source features inactive", data["totals"])
        check(data["totals"]["active_candidates"] == 0, "Summary keeps candidates inactive", data["totals"])
        check(data["totals"]["promoted_candidates"] == 0, "Summary keeps candidates unpromoted", data["totals"])
        check(data["runtime_tables_written"] is False, "Endpoint writes no runtime tables", data)
        check(data["runtime_spatial_matching_changed"] is False, "Endpoint keeps spatial matching disabled", data)
        check(data["lookup_api_enabled"] is False, "Endpoint keeps lookup disabled", data)
        check(data["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", data)
        check(data["readiness"]["ready_for_future_project_matching_design"] is True, "Endpoint is ready for future project matching design", data["readiness"])
        check(data["readiness"]["ready_for_runtime_spatial_matching"] is False, "Endpoint is not runtime matching", data["readiness"])
        check(len(data["states"]) == 36, "Endpoint returns state rows", data["states"][:3])
        check(any(item["state_or_ut"] == "Karnataka" for item in data["states"]), "Endpoint includes Karnataka pilot lineage", data["states"][:8])

        after = staging_summary(db)
        check(after["candidates"] == before["candidates"], "Endpoint did not create/delete candidates", dict(after))
        check(after["active_candidates"] == 0, "Endpoint did not activate candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Endpoint did not promote candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY ADMIN STATE-WISE MATCH SUMMARY ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
