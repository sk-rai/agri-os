#!/usr/bin/env python3
"""Regression stitching one-state demographic apply to admin preview.

The test applies a tiny state-scoped batch, verifies the admin preview sees it,
then cleans up only rows inserted by this test run. If the rows already exist
from a future persistent apply, it verifies preview/idempotency and leaves them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


PYTHON = ROOT / "venv" / "bin" / "python"
APPLY_SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_import.py"
OUTPUT = Path("/tmp/nwdp-demographic-one-state-apply-admin-preview-regression.json")
ENDPOINT = "/api/v1/master-data/geography/nwdp-demographic-profiles/preview"

STATE = "Andaman & Nicobar Island"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SOURCE_VERSION = "20260824T110250Z"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
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


def cleanup_inserted(source_feature_ids: list[str]) -> None:
    if not source_feature_ids:
        return

    with SessionLocal() as db:
        db.execute(
            text("""
                delete from geography_village_demographic_profiles
                where source_system = :source_system
                  and source_version = :source_version
                  and source_feature_id = any(cast(:source_feature_ids as uuid[]))
            """),
            {
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
                "source_feature_ids": source_feature_ids,
            },
        )
        db.commit()


def run_apply() -> dict:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(APPLY_SCRIPT),
            "--state-or-ut",
            STATE,
            "--apply",
            "--limit",
            "5",
            "--max-rows",
            "10",
            "--output",
            str(OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Apply writes audit output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    check(proc.returncode == 0, "Guarded one-state apply exits zero", data)
    return data


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE APPLY ADMIN PREVIEW REGRESSION")
    print("=" * 72)

    before = profile_counts()
    inserted_ids: list[str] = []
    admin = None

    try:
        apply_data = run_apply()
        result = apply_data["apply_result"]

        check(result["planned_insert_count"] == 5, "Apply plans five scoped rows", result)
        check(result["inserted_count"] in (0, 5), "Apply either inserts or idempotently skips five rows", result)
        check(result["skipped_existing_count"] in (0, 5), "Apply skip count is expected", result)
        check(result["inserted_count"] + result["skipped_existing_count"] == 5, "Apply accounts for all five rows", result)
        check(len(result["state_district_summary"]) > 0, "Apply returns state/district summary", result["state_district_summary"])

        inserted_ids = result["sample_inserted_source_feature_ids"]
        check(len(inserted_ids) == result["inserted_count"], "Inserted source feature ids match inserted count", inserted_ids)

        client = TestClient(app)
        unauth = client.get(ENDPOINT, params={"state_or_ut": STATE})
        check(unauth.status_code in (401, 403), "Unauthenticated preview is denied", unauth.text)

        with SessionLocal() as db:
            admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        response = client.get(ENDPOINT, headers=headers, params={"state_or_ut": STATE})
        check(response.status_code == 200, "Admin preview returns 200 after apply", response.text)

        preview = response.json()
        check(preview["schema_version"] == "nwdp_demographic_profiles_admin_preview.v1", "Preview schema is stable", preview)
        check(preview["healthy"] is True, "Preview is healthy", preview)
        check(preview["enabled"] is True, "Preview is enabled when scoped rows exist", preview)
        check(preview["filters"]["state_or_ut"] == STATE, "Preview echoes state filter", preview["filters"])
        check(preview["profile_row_count"] >= 5, "Preview sees at least five scoped rows", preview)
        summary = preview["summary"]
        reviewed_or_candidate_count = (
            summary["auto_candidate_count"]
            + summary["approved_for_promotion_count"]
            + summary["manual_review_count"]
            + summary["rejected_count"]
            + summary["blocked_count"]
        )
        check(reviewed_or_candidate_count == summary["profile_row_count"], "Preview review buckets account for scoped rows", summary)
        check(summary["active_profile_row_count"] == summary["promoted_profile_row_count"], "Preview active count matches promoted count", summary)
        check(preview["approved_vs_manual_review"]["approved_for_promotion_count"] == summary["approved_for_promotion_count"], "Preview approved count matches summary", preview["approved_vs_manual_review"])
        check(preview["approved_vs_manual_review"]["manual_review_count"] == summary["manual_review_count"], "Preview manual-review count matches summary", preview["approved_vs_manual_review"])
        check(len(preview["state_district_summary"]) > 0, "Preview returns state/district grouped rows", preview["state_district_summary"])
        check(len(preview["items"]) >= 5, "Preview returns applied rows as items", preview["items"])

        guardrails = preview["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Preview endpoint remains read-only", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Preview does not enable runtime lookup", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Preview does not change Android", guardrails)
        check(guardrails["official_census_claimed_imported"] is False, "Preview does not claim official Census", guardrails)

    finally:
        cleanup_inserted(inserted_ids)
        if admin is not None:
            with SessionLocal() as db:
                delete_test_admin(db, admin.id)

    after = profile_counts()
    expected_after = {
        "profile_row_count": before["profile_row_count"],
        "active_profile_row_count": before["active_profile_row_count"],
        "promoted_profile_row_count": before["promoted_profile_row_count"],
    }
    check(after == expected_after, "Regression returns profile table to pre-test counts", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE APPLY ADMIN PREVIEW REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
