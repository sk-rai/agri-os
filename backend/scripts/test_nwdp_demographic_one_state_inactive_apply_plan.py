#!/usr/bin/env python3
"""Regression for one-state inactive NWDP demographic profile apply plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_one_state_inactive_apply.py"
OUTPUT = Path("/tmp/nwdp-demographic-one-state-inactive-apply-plan-regression.json")


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


def run_plan(*args: str) -> tuple[int, dict]:
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

    check(OUTPUT.exists(), "Plan writes audit output", proc.stdout)
    return proc.returncode, json.loads(OUTPUT.read_text(encoding="utf-8"))


def assert_common_contract(data: dict) -> None:
    check(data["schema_version"] == "nwdp_demographic_one_state_inactive_apply_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "PLAN_ONLY_ONE_STATE_INACTIVE_PROFILE_APPLY", "Mode is plan-only", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Target table is explicit", data)

    selection = data["selection_policy"]
    check(selection["state_scope_required"] is True, "State scope is required", selection)
    check(selection["all_state_apply_allowed"] is False, "All-state apply is blocked", selection)
    check(selection["candidate_bucket_required"] == "DIRECT_VLCODE_MATCH", "Requires direct-code candidate bucket", selection)
    check(selection["candidate_review_status_required"] == "AUTO_CANDIDATE", "Requires auto-candidate review status", selection)
    check(selection["candidate_promotion_status_required"] == "NOT_PROMOTED", "Requires not-promoted candidates", selection)
    check(selection["candidate_proposed_village_id_required"] is True, "Requires proposed village id", selection)
    check(selection["raw_feature_required"] is True, "Requires raw feature", selection)

    insert = data["insert_policy"]
    check(insert["profile_review_status"] == "AUTO_CANDIDATE", "Inserted profiles stay auto-candidate", insert)
    check(insert["profile_promotion_status"] == "NOT_PROMOTED", "Inserted profiles stay not promoted", insert)
    check(insert["profile_is_active"] is False, "Inserted profiles stay inactive", insert)
    check(insert["runtime_table_write_allowed"] is False, "Runtime table writes blocked", insert)
    check(insert["candidate_activation_allowed"] is False, "Candidate activation blocked", insert)
    check(insert["candidate_promotion_allowed"] is False, "Candidate promotion blocked", insert)

    idempotency = data["idempotency_policy"]
    check(idempotency["primary_dedupe_key"] == ["source_system", "source_version", "source_feature_id"], "Primary dedupe key is source feature", idempotency)
    check(idempotency["skip_existing_source_feature"] is True, "Existing source features are skipped", idempotency)
    check(idempotency["do_not_update_existing_profiles"] is True, "Existing profiles are not updated", idempotency)
    check(idempotency["do_not_delete_existing_profiles"] is True, "Existing profiles are not deleted", idempotency)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Plan writes no profiles", guardrails)
    check(guardrails["profiles_promoted"] is False, "Plan promotes no profiles", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Plan does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Plan does not claim official Census", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "Plan activates no candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "Plan promotes no candidates", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Plan keeps runtime lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE INACTIVE APPLY PLAN REGRESSION")
    print("=" * 72)

    before = profile_counts()

    no_scope_code, no_scope = run_plan()
    check(no_scope_code != 0, "No-scope plan exits non-zero", no_scope)
    check(no_scope["healthy"] is False, "No-scope plan is unhealthy", no_scope)
    check(no_scope["error"] == "NWDP_DEMOGRAPHIC_ONE_STATE_APPLY_PLAN_REQUIRES_STATE_SCOPE", "No-scope plan reports missing scope", no_scope)
    assert_common_contract(no_scope)

    scoped_code, scoped = run_plan("--state-or-ut", "Chandigarh")
    check(scoped_code == 0, "Scoped plan exits zero", scoped)
    check(scoped["healthy"] is True, "Scoped plan is healthy", scoped)
    check(scoped["state_or_ut"] == "Chandigarh", "Scoped plan echoes state", scoped)
    check(scoped["error"] is None, "Scoped plan has no error", scoped)
    check(scoped["readiness"]["ready_for_one_state_inactive_apply_implementation"] is True, "Scoped plan is ready for implementation design", scoped["readiness"])
    check(scoped["readiness"]["ready_for_demographic_profile_apply"] is False, "Scoped plan still does not apply", scoped["readiness"])
    assert_common_contract(scoped)

    after = profile_counts()
    check(after == before, "Plan did not mutate profile table", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE INACTIVE APPLY PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
