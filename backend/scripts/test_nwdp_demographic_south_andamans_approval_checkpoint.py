#!/usr/bin/env python3
"""Read-only checkpoint for South Andamans NWDP demographic approval state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin  # noqa: E402
from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

TARGET_TABLE = "geography_village_demographic_profiles"
STATE = "Andaman & Nicobar Island"
DISTRICT = "South Andamans"
DRY_RUN_ENDPOINT = "/api/v1/master-data/geography/nwdp-demographic-profiles/promotion/dry-run"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def scoped_counts() -> dict:
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        return dict(conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'REJECTED')::bigint as rejected_count,
              count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
              count(*) filter (
                where review_status = 'APPROVED_FOR_PROMOTION'
                  and promotion_status = 'NOT_PROMOTED'
                  and is_active = false
              )::bigint as promotion_dry_run_eligible_count
            from {TARGET_TABLE}
            where source_system = :source_system
              and source_version = :source_version
              and source_state_name = :state
              and source_district_name = :district
        """), {
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
            "state": STATE,
            "district": DISTRICT,
        }).mappings().one())


def dry_run_summary() -> dict:
    with SessionLocal() as db:
        user, headers = create_test_admin(db)
        try:
            client = TestClient(app)
            response = client.get(
                DRY_RUN_ENDPOINT,
                headers=headers,
                params={
                    "state_or_ut": STATE,
                    "district": DISTRICT,
                    "limit": 20,
                },
            )
            data = response.json()
            data["status_code"] = response.status_code
            return data
        finally:
            delete_test_admin(db, user.id)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC SOUTH ANDAMANS APPROVAL CHECKPOINT REGRESSION")
    print("=" * 72)

    counts = scoped_counts()

    check(counts["profile_row_count"] == 123, "South Andamans profile row count is stable", counts)
    check(counts["approved_for_promotion_count"] == 5, "Five South Andamans rows are approved", counts)
    check(counts["auto_candidate_count"] == 118, "Remaining South Andamans rows stay auto-candidate", counts)
    check(counts["manual_review_count"] == 0, "No South Andamans rows are manual review", counts)
    check(counts["rejected_count"] == 0, "No South Andamans rows are rejected", counts)
    check(counts["blocked_count"] == 0, "No South Andamans rows are blocked", counts)
    check(counts["active_profile_row_count"] == 0, "No South Andamans demographic profiles are active", counts)
    check(counts["promoted_profile_row_count"] == 0, "No South Andamans demographic profiles are promoted", counts)
    check(counts["promotion_dry_run_eligible_count"] == 5, "Five rows are eligible for promotion dry-run", counts)

    dry_run = dry_run_summary()
    summary = dry_run["summary"]
    guardrails = dry_run["guardrails"]

    check(dry_run["status_code"] == 200, "Promotion dry-run endpoint returns 200", dry_run)
    check(dry_run["healthy"] is True, "Promotion dry-run is healthy", dry_run)
    check(summary["eligible_profile_row_count"] == 5, "Promotion dry-run reports five eligible rows", summary)
    check(summary["approved_for_promotion_count"] == 5, "Promotion dry-run reports five approved rows", summary)
    check(summary["active_profile_row_count"] == 0, "Promotion dry-run sees no active rows", summary)
    check(summary["promoted_profile_row_count"] == 0, "Promotion dry-run sees no promoted rows", summary)
    check(len(dry_run["items"]) == 5, "Promotion dry-run returns five items", dry_run["items"])

    check(guardrails["db_writes_attempted"] is False, "Dry-run writes no DB rows", guardrails)
    check(guardrails["profile_review_status_changed"] is False, "Dry-run changes no review status", guardrails)
    check(guardrails["profiles_promoted"] is False, "Dry-run promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Dry-run activates no rows", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Official Census remains unclaimed", guardrails)

    result = {
        "schema_version": "nwdp_demographic_south_andamans_approval_checkpoint.v1",
        "healthy": True,
        "state_or_ut": STATE,
        "district": DISTRICT,
        "counts": counts,
        "promotion_dry_run_summary": summary,
        "guardrails": guardrails,
        "readiness": {
            "ready_for_more_scoped_review_approval": True,
            "ready_for_promotion_dry_run": True,
            "ready_for_profile_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    print("=" * 72)
    print("NWDP DEMOGRAPHIC SOUTH ANDAMANS APPROVAL CHECKPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
