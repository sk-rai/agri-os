#!/usr/bin/env python3
"""Regression for read-only NWDP demographic profiles admin preview endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


ENDPOINT = "/api/v1/master-data/geography/nwdp-demographic-profiles/preview"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def profile_counts() -> dict:
    with SessionLocal() as db:
        return dict(db.execute(text("""
            select
              count(*) as profile_row_count,
              count(*) filter (where is_active = true) as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED') as promoted_profile_row_count
            from geography_village_demographic_profiles
        """)).mappings().first())


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN PREVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    before = profile_counts()
    admin = None

    unauth = client.get(ENDPOINT)
    check(unauth.status_code in (401, 403), "Unauthenticated preview is denied", unauth.text)

    with SessionLocal() as db:
        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

    try:
        response = client.get(ENDPOINT, headers=headers)
        check(response.status_code == 200, "Admin preview endpoint returns 200", response.text)

        data = response.json()
        check(data["schema_version"] == "nwdp_demographic_profiles_admin_preview.v1", "Schema version is stable", data)
        check(data["healthy"] is True, "Preview response is healthy", data)
        check(data["enabled"] is False, "Preview remains disabled while empty", data)
        check(data["reason"] == "NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED", "Disabled reason is explicit", data)
        check(data["target_table"] == "geography_village_demographic_profiles", "Target table is reported", data)
        check(data["profile_row_count"] == 0, "Profile row count is zero", data)
        check(data["active_profile_row_count"] == 0, "Active profile count is zero", data)
        check(data["promoted_profile_row_count"] == 0, "Promoted profile count is zero", data)

        fields = set(data["future_preview_fields"])
        for field in ["source_system", "source_version", "source_vlcode", "total_population", "total_households", "promotion_status", "is_active"]:
            check(field in fields, f"Future preview field present: {field}", data["future_preview_fields"])

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["demographic_profile_rows_written"] is False, "Endpoint writes no profiles", guardrails)
        check(guardrails["profiles_promoted"] is False, "Endpoint promotes no profiles", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Endpoint keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", guardrails)
        check(guardrails["official_census_claimed_imported"] is False, "Endpoint does not claim official Census", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_profile_apply"] is False, "Endpoint is not apply", readiness)
        check(readiness["ready_for_runtime_lookup_enablement"] is False, "Endpoint is not runtime lookup", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Endpoint is not Android change", readiness)
        check(readiness["ready_for_official_census_import"] is False, "Endpoint is not Census import", readiness)

    finally:
        if admin is not None:
            with SessionLocal() as db:
                delete_test_admin(db, admin.id)

    after = profile_counts()
    check(after == before, "Endpoint did not mutate profile table", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN PREVIEW ENDPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
