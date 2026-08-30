#!/usr/bin/env python3
"""Regression for read-only NWDP demographic profiles admin preview endpoint."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


ENDPOINT = "/api/v1/master-data/geography/nwdp-demographic-profiles/preview"
FIXTURE_SOURCE_SYSTEM = "TEST_NWDP_DEMOGRAPHIC_PREVIEW"
FIXTURE_SOURCE_VERSION = "20260830T_POSITIVE_PREVIEW_FIXTURE"


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


def cleanup_fixture_profiles() -> None:
    with SessionLocal() as db:
        db.execute(
            text("""
                delete from geography_village_demographic_profiles
                where source_system = :source_system
                  and source_version = :source_version
            """),
            {
                "source_system": FIXTURE_SOURCE_SYSTEM,
                "source_version": FIXTURE_SOURCE_VERSION,
            },
        )
        db.commit()


def insert_fixture_profiles() -> None:
    with SessionLocal() as db:
        village_ids = [
            str(row["id"])
            for row in db.execute(
                text("select id from geography_villages order by id limit 3")
            ).mappings()
        ]

        check(len(village_ids) >= 1, "At least one canonical village exists for fixture", village_ids)

        while len(village_ids) < 3:
            village_ids.append(village_ids[0])

        rows = [
            {
                "id": str(uuid.uuid4()),
                "village_id": village_ids[0],
                "source_feature_id": str(uuid.uuid4()),
                "source_feature_index": 1,
                "source_vlcode": "TEST001",
                "source_state_name": "Fixture State",
                "source_district_name": "Fixture District",
                "source_subdistrict_name": "Fixture Block",
                "source_village_name": "Fixture Approved Village",
                "total_population": 1200,
                "total_households": 240,
                "review_status": "APPROVED_FOR_PROMOTION",
            },
            {
                "id": str(uuid.uuid4()),
                "village_id": village_ids[1],
                "source_feature_id": str(uuid.uuid4()),
                "source_feature_index": 2,
                "source_vlcode": "TEST002",
                "source_state_name": "Fixture State",
                "source_district_name": "Fixture District",
                "source_subdistrict_name": "Fixture Block",
                "source_village_name": "Fixture Manual Village A",
                "total_population": 800,
                "total_households": 160,
                "review_status": "MANUAL_REVIEW",
            },
            {
                "id": str(uuid.uuid4()),
                "village_id": village_ids[2],
                "source_feature_id": str(uuid.uuid4()),
                "source_feature_index": 3,
                "source_vlcode": "TEST003",
                "source_state_name": "Fixture State",
                "source_district_name": "Fixture District",
                "source_subdistrict_name": "Fixture Block",
                "source_village_name": "Fixture Manual Village B",
                "total_population": 600,
                "total_households": 120,
                "review_status": "MANUAL_REVIEW",
            },
        ]

        for row in rows:
            db.execute(
                text("""
                    insert into geography_village_demographic_profiles (
                        id,
                        village_id,
                        source_system,
                        source_version,
                        source_feature_id,
                        source_feature_index,
                        source_vlcode,
                        source_state_name,
                        source_district_name,
                        source_subdistrict_name,
                        source_village_name,
                        total_population,
                        total_households,
                        rural_urban,
                        source_properties,
                        match_evidence,
                        review_status,
                        is_active,
                        promotion_status
                    )
                    values (
                        cast(:id as uuid),
                        cast(:village_id as uuid),
                        :source_system,
                        :source_version,
                        cast(:source_feature_id as uuid),
                        :source_feature_index,
                        :source_vlcode,
                        :source_state_name,
                        :source_district_name,
                        :source_subdistrict_name,
                        :source_village_name,
                        :total_population,
                        :total_households,
                        'Rural',
                        cast(:source_properties as jsonb),
                        cast(:match_evidence as jsonb),
                        :review_status,
                        false,
                        'NOT_PROMOTED'
                    )
                """),
                {
                    **row,
                    "source_system": FIXTURE_SOURCE_SYSTEM,
                    "source_version": FIXTURE_SOURCE_VERSION,
                    "source_properties": json.dumps({"fixture": True}),
                    "match_evidence": json.dumps({"fixture": True, "scope": "admin_preview_positive_regression"}),
                },
            )

        db.commit()


def assert_empty_table_contract(client: TestClient, headers: dict) -> None:
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
    check(data["filters"] == {"state_or_ut": None, "district": None, "limit": 50}, "Default filters are present", data["filters"])

    fields = set(data["future_preview_fields"])
    for field in [
        "source_system",
        "source_version",
        "source_vlcode",
        "total_population",
        "total_households",
        "review_status",
        "promotion_status",
        "is_active",
    ]:
        check(field in fields, f"Future preview field present: {field}", data["future_preview_fields"])

    summary = data["summary"]
    check(summary["auto_candidate_count"] == 0, "Summary auto candidate count is zero", summary)
    check(summary["manual_review_count"] == 0, "Summary manual review count is zero", summary)
    check(summary["approved_for_promotion_count"] == 0, "Summary approved count is zero", summary)
    check(data["approved_vs_manual_review"] == {"approved_for_promotion_count": 0, "manual_review_count": 0}, "Approved versus manual review summary is empty", data["approved_vs_manual_review"])
    check(data["state_district_summary"] == [], "State/district summary is empty before import", data["state_district_summary"])
    check(data["items"] == [], "Preview items are empty before import", data["items"])

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


def assert_positive_state_district_analysis(client: TestClient, headers: dict) -> None:
    response = client.get(
        ENDPOINT,
        headers=headers,
        params={"state_or_ut": "Fixture State", "district": "Fixture District"},
    )
    check(response.status_code == 200, "Filtered admin preview endpoint returns 200", response.text)

    data = response.json()
    check(data["enabled"] is True, "Preview is enabled when matching fixture profiles exist", data)
    check(data["reason"] is None, "Enabled preview has no disabled reason", data)
    check(data["filters"]["state_or_ut"] == "Fixture State", "Filtered state is echoed", data["filters"])
    check(data["filters"]["district"] == "Fixture District", "Filtered district is echoed", data["filters"])
    check(data["profile_row_count"] == 3, "Filtered profile count includes fixture rows", data)

    summary = data["summary"]
    check(summary["profile_row_count"] == 3, "Summary profile count includes fixture rows", summary)
    check(summary["approved_for_promotion_count"] == 1, "Summary approved count is correct", summary)
    check(summary["manual_review_count"] == 2, "Summary manual review count is correct", summary)
    check(summary["auto_candidate_count"] == 0, "Summary auto candidate count is correct", summary)
    check(summary["promoted_profile_row_count"] == 0, "Summary promoted count remains zero", summary)
    check(summary["active_profile_row_count"] == 0, "Summary active count remains zero", summary)

    check(
        data["approved_vs_manual_review"] == {
            "approved_for_promotion_count": 1,
            "manual_review_count": 2,
        },
        "Approved versus manual review summary is correct",
        data["approved_vs_manual_review"],
    )

    check(len(data["state_district_summary"]) == 1, "One state/district summary row returned", data["state_district_summary"])
    district_row = data["state_district_summary"][0]
    check(district_row["state_or_ut"] == "Fixture State", "State/district row state is correct", district_row)
    check(district_row["district"] == "Fixture District", "State/district row district is correct", district_row)
    check(district_row["profile_row_count"] == 3, "State/district profile count is correct", district_row)
    check(district_row["approved_for_promotion_count"] == 1, "State/district approved count is correct", district_row)
    check(district_row["manual_review_count"] == 2, "State/district manual review count is correct", district_row)

    check(len(data["items"]) == 3, "Filtered preview items include fixture rows", data["items"])
    statuses = sorted(item["review_status"] for item in data["items"])
    check(statuses == ["APPROVED_FOR_PROMOTION", "MANUAL_REVIEW", "MANUAL_REVIEW"], "Preview item review statuses are correct", statuses)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN PREVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    cleanup_fixture_profiles()

    client = TestClient(app)
    before = profile_counts()
    admin = None

    unauth = client.get(ENDPOINT)
    check(unauth.status_code in (401, 403), "Unauthenticated preview is denied", unauth.text)

    with SessionLocal() as db:
        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

    try:
        assert_empty_table_contract(client, headers)

        insert_fixture_profiles()
        assert_positive_state_district_analysis(client, headers)

    finally:
        cleanup_fixture_profiles()
        if admin is not None:
            with SessionLocal() as db:
                delete_test_admin(db, admin.id)

    after = profile_counts()
    check(after == before, "Endpoint regression cleaned up fixture profile rows", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ADMIN PREVIEW ENDPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
