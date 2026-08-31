#!/usr/bin/env python3
"""Regression for fast all-state inactive NWDP demographic apply plan."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from scripts.apply_nwdp_demographic_profile_import import state_key_aliases  # noqa: E402

PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_all_state_inactive_apply.py"
OUTPUT = Path("/tmp/nwdp-demographic-all-state-inactive-apply-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ALL-STATE INACTIVE APPLY PLAN REGRESSION")
    print("=" * 72)

    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--output",
            str(OUTPUT),
            "--max-rows-per-state",
            "200000",
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )

    check(OUTPUT.exists(), "All-state plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "All-state plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_all_state_inactive_apply_plan.v2", "Schema version is stable", data)
    check(data["mode"] == "FAST_DB_AGGREGATE_PLAN_ONLY_ALL_STATE_INACTIVE_PROFILE_APPLY", "Mode is fast DB aggregate plan-only", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Target table is explicit", data)
    check(data["state_count"] >= 30, "Plan includes national state/UT coverage", data)
    check(data["total_planned_profile_rows"] >= 450000, "Plan sees national planned profile rows", data)
    check(data["total_existing_profile_rows"] >= 512, "Plan accounts for existing Andaman profiles", data)
    check(data["total_remaining_insert_rows"] == data["total_planned_profile_rows"] - data["total_existing_profile_rows"], "Remaining rows are planned minus existing", data)

    national = data["national_overlay_summary"]
    check(national["available"] is True, "National overlay summary is linked", national)
    check(national.get("overlaid_count") in (None, 452930), "National overlay overlaid count is stable when exposed", national)

    andaman_aliases = set(state_key_aliases("Andaman & Nicobar Island"))
    andaman = [
        row for row in data["state_plans"]
        if set(state_key_aliases(row["state_or_ut"])) & andaman_aliases
    ]
    check(len(andaman) == 1, "Plan includes Andaman state row by normalized alias", data["state_plans"][:8])
    check(andaman[0]["planned_profile_rows"] == 512, "Andaman planned rows are stable", andaman[0])
    check(andaman[0]["existing_profile_rows"] == 512, "Andaman existing rows are accounted for", andaman[0])
    check(andaman[0]["remaining_insert_rows"] == 0, "Andaman has no remaining inserts", andaman[0])

    performance = data["performance_policy"]
    check(performance["raw_geojson_scanned"] is False, "Plan does not scan raw GeoJSON", performance)
    check(performance["db_aggregate_only"] is True, "Plan uses DB aggregates only", performance)

    recommended = data["recommended_execution"]
    check(recommended["execution_model"] == "one state/UT at a time", "Execution remains one-state-at-a-time", recommended)
    check(recommended["all_state_single_transaction_allowed"] is False, "Single all-state transaction is blocked", recommended)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Plan writes no profiles", guardrails)
    check(guardrails["profiles_promoted"] is False, "Plan promotes no profiles", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Plan does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Plan does not claim official Census", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Plan keeps runtime lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_one_state_at_a_time_apply"] is True, "Plan is ready for one-state-at-a-time apply", readiness)
    check(readiness["ready_for_single_all_state_apply"] is False, "Plan is not ready for single all-state apply", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Plan is not runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Plan is not Android change", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ALL-STATE INACTIVE APPLY PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
