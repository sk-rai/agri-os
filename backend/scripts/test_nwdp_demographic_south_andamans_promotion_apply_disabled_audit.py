#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

STATE = "Andaman & Nicobar Island"
DISTRICT = "South Andamans"
OUT = Path("/tmp/nwdp-demographic-south-andamans-promotion-apply-disabled-audit-regression.json")


def check(condition, label, detail=None):
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True))
        return
    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True))
    raise AssertionError(label)


def scoped_counts():
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  COUNT(*)::bigint AS profile_row_count,
                  COUNT(*) FILTER (WHERE review_status = 'AUTO_CANDIDATE')::bigint AS auto_candidate_count,
                  COUNT(*) FILTER (WHERE review_status = 'APPROVED_FOR_PROMOTION')::bigint AS approved_for_promotion_count,
                  COUNT(*) FILTER (
                    WHERE review_status = 'APPROVED_FOR_PROMOTION'
                      AND promotion_status = 'NOT_PROMOTED'
                      AND is_active = false
                  )::bigint AS promotion_eligible_count,
                  COUNT(*) FILTER (WHERE is_active = true)::bigint AS active_profile_row_count,
                  COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count
                FROM geography_village_demographic_profiles
                WHERE source_system = :source_system
                  AND source_version = :source_version
                  AND source_state_name = :state
                  AND source_district_name = :district
                """
            ),
            {
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
                "state": STATE,
                "district": DISTRICT,
            },
        ).mappings().one()
    return dict(row)


def main():
    print("=" * 72)
    print("NWDP DEMOGRAPHIC SOUTH ANDAMANS PROMOTION APPLY DISABLED AUDIT REGRESSION")
    print("=" * 72)

    before = scoped_counts()
    check(before["profile_row_count"] == 123, "South Andamans profile count is stable", before)
    check(before["auto_candidate_count"] == 0, "No South Andamans auto-candidates remain after full admin rollout", before)
    check(before["approved_for_promotion_count"] == before["profile_row_count"], "All South Andamans rows are approved after full admin rollout", before)
    check(before["promotion_eligible_count"] == 0, "No rows remain eligible for promotion audit after promotion", before)
    check(before["active_profile_row_count"] == before["approved_for_promotion_count"], "Approved South Andamans rows are active before audit", before)
    check(before["promoted_profile_row_count"] == before["active_profile_row_count"], "Active South Andamans rows are promoted before audit", before)

    if OUT.exists():
        OUT.unlink()

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "backend/scripts/apply_nwdp_demographic_profile_promotion.py"),
            "--apply",
            "--state-or-ut",
            STATE,
            "--district",
            DISTRICT,
            "--limit",
            "20",
            "--output",
            str(OUT),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    check(proc.returncode != 0, "Disabled promotion apply exits non-zero", {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    check(OUT.exists(), "Disabled promotion audit writes JSON output", str(OUT))

    audit = json.loads(OUT.read_text())
    check(audit["schema_version"] == "nwdp_demographic_profile_promotion_apply.v1", "Audit schema version is stable", audit)
    check(audit["healthy"] is False, "Disabled audit is unhealthy by design", audit)
    check(audit["error"] == "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_DISABLED_BY_POLICY", "Promotion apply remains disabled by policy", audit)
    check(audit["apply"] is True, "Audit records explicit apply attempt", audit)
    check(audit["enable_policy"] is False, "Policy override is not enabled", audit)
    check(audit["scope"]["state_and_district_scope_present"] is True, "Audit is state/district scoped", audit["scope"])
    check(audit["eligible_summary"]["eligible_profile_row_count"] == 0, "Audit sees no remaining eligible scoped rows", audit["eligible_summary"])
    check(audit["apply_result"]["planned_promotion_count"] == 0, "Audit plans no remaining promotions", audit["apply_result"])
    check(audit["apply_result"]["apply_implemented"] is False, "Promotion apply is not implemented without policy enablement", audit["apply_result"])
    check(audit["apply_result"]["promoted_count"] == 0, "Audit promotes zero rows", audit["apply_result"])
    check(audit["apply_result"]["activated_count"] == 0, "Audit activates zero rows", audit["apply_result"])
    check(len(audit["sample_items"]) == 0, "Audit samples no remaining eligible rows", audit["sample_items"])

    guardrails = audit["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Disabled audit attempts no DB writes", guardrails)
    check(guardrails["profiles_promoted"] is False, "Disabled audit promotes no profiles", guardrails)
    check(guardrails["profile_rows_activated"] is False, "Disabled audit activates no rows", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Runtime lookup remains disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Android remains unchanged", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Official Census remains unclaimed", guardrails)

    after = scoped_counts()
    check(after == before, "Scoped DB state is unchanged after disabled audit", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC SOUTH ANDAMANS PROMOTION APPLY DISABLED AUDIT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
