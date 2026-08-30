#!/usr/bin/env python3
"""Regression for disabled NWDP demographic profile import apply guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_import.py"
OUTPUT = Path("/tmp/nwdp-demographic-profile-import-apply-disabled-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def profile_counts() -> dict:
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        return dict(db.execute(text("""
            select
              count(*) as profile_row_count,
              count(*) filter (where is_active = true) as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED') as promoted_profile_row_count
            from geography_village_demographic_profiles
        """)).mappings().first())


def run_guard(*args: str) -> dict:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output", str(OUTPUT), *args],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Disabled apply writes audit output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    check(proc.returncode != 0, "Disabled apply exits non-zero", data)
    return data


def assert_common_guardrails(data: dict) -> None:
    check(data["schema_version"] == "nwdp_demographic_profile_import_apply.v1", "Schema version is stable", data)
    check(data["healthy"] is False, "Disabled apply is unhealthy by design", data)
    check(data["mode"] == "APPLY_DISABLED_GUARDRAIL", "Mode is apply-disabled guardrail", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Target table is explicit", data)
    check(data["apply_result"]["policy_flag_present"] is True, "Policy flag is present", data["apply_result"])
    check(data["apply_result"]["requires_state_scope"] is True, "State scope is required", data["apply_result"])
    check(data["apply_result"]["apply_implemented"] is True, "Apply implementation is present but gated", data["apply_result"])

    scope = data["planned_scope"]
    check(scope["allowed_future_scope"] == "single state/UT inactive profile rows only", "Future apply scope is state-scoped", scope)
    check(scope["candidate_bucket_required"] == "DIRECT_VLCODE_MATCH", "Future apply requires direct-code candidates", scope)
    check(scope["candidate_review_status_required"] == "AUTO_CANDIDATE", "Future apply requires auto candidates", scope)
    check(scope["candidate_promotion_status_required"] == "NOT_PROMOTED", "Future apply requires not-promoted candidates", scope)
    check(scope["profile_review_status"] == "AUTO_CANDIDATE", "Future profiles remain auto candidates", scope)
    check(scope["profile_promotion_status"] == "NOT_PROMOTED", "Future profiles remain not promoted", scope)
    check(scope["profile_is_active"] is False, "Future profiles remain inactive", scope)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Apply guard attempts no DB writes", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Apply guard writes no profiles", guardrails)
    check(guardrails["profiles_promoted"] is False, "Apply guard promotes no profiles", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Apply guard does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Apply guard does not claim official Census", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Apply guard activates no candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Apply guard promotes no candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "Apply guard writes no project matching records", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Apply guard keeps runtime lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Apply guard keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_profile_apply"] is False, "Not ready for profile apply", readiness)
    check(readiness["ready_for_state_scoped_apply_design"] is True, "Ready for state-scoped apply design", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android change", readiness)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE IMPORT APPLY DISABLED REGRESSION")
    print("=" * 72)

    before = profile_counts()

    no_scope = run_guard()
    check(no_scope["error"] == "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_REQUIRES_STATE_SCOPE", "No-scope apply reports state-scope error", no_scope)
    check(no_scope["apply_result"]["state_scope_present"] is False, "No-scope apply records missing state scope", no_scope["apply_result"])
    assert_common_guardrails(no_scope)

    scoped = run_guard("--state-or-ut", "Chandigarh")
    check(scoped["error"] == "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_FLAG_REQUIRED", "Scoped apply still requires explicit apply flag", scoped)
    check(scoped["state_or_ut"] == "Chandigarh", "Scoped apply echoes state scope", scoped)
    check(scoped["apply_result"]["state_scope_present"] is True, "Scoped apply records state scope", scoped["apply_result"])
    assert_common_guardrails(scoped)

    after = profile_counts()
    check(after == before, "Disabled apply did not mutate profile table", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC PROFILE IMPORT APPLY DISABLED REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
