#!/usr/bin/env python3
"""Regression check for the committed NWDP x CoRE full national overlay summary.

This test intentionally validates the compact summary artifact only. It does not
rerun the long spatial overlay, write database rows, activate candidates, enable
lookup APIs, or change Android/runtime behavior.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = (
    ROOT
    / "data/staged/core_stack/nwdp_full_overlay_runs/"
    / "20260829_full_national_2worker/combined_national_overlay_summary.json"
)

EXPECTED_EXCLUDED_ZERO_ELIGIBLE_STATES = {
    "Dadra and Nagar Haveli and Daman Diu",
    "Jammu Kashmir",
}

EXPECTED_GUARDRAILS = {
    "android_behavior_changed",
    "core_zone_mappings_written",
    "db_writes_attempted",
    "lookup_api_enabled",
    "nwdp_candidates_activated",
    "nwdp_candidates_promoted",
    "project_matching_records_written",
    "runtime_tables_written",
}


def fail(message: str, evidence: object | None = None) -> int:
    print(f"FAIL {message}")
    if evidence is not None:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    return 1


def pass_check(message: str, evidence: object | None = None) -> None:
    print(f"PASS {message}")
    if evidence is not None:
        print(json.dumps(evidence, indent=2, sort_keys=True))


def main() -> int:
    print("=" * 72)
    print("NWDP CORE AGRO-ZONE FULL NATIONAL SUMMARY REGRESSION")
    print("=" * 72)

    if not SUMMARY_PATH.exists():
        return fail("Summary artifact exists", {"path": str(SUMMARY_PATH)})

    data = json.loads(SUMMARY_PATH.read_text())
    aggregate = data.get("aggregate", {})
    guardrails = data.get("guardrail_true_counts", {})

    checks = [
        ("Summary schema", data.get("schema_version") == "nwdp_core_agro_zone_full_national_2worker_summary.v1"),
        ("Summary healthy", data.get("healthy") is True),
        ("Two worker reports", aggregate.get("worker_report_count") == 2),
        ("Two state summaries", aggregate.get("state_summary_count") == 2),
        ("34 states processed", aggregate.get("state_count") == 34),
        ("34 states healthy", aggregate.get("healthy_state_count") == 34),
        ("Eligible equals overlaid", aggregate.get("eligible_candidate_count") == aggregate.get("overlaid_count")),
        ("Expected full eligible/overlaid rows", aggregate.get("overlaid_count") == 452930),
        ("No invalid or missing geometry", aggregate.get("invalid_or_missing_geometry_count") == 0),
        ("No duplicate states", data.get("duplicate_states") == []),
        ("No unhealthy states", data.get("unhealthy_states") == []),
        (
            "Excluded zero-eligible states recorded",
            set(data.get("excluded_zero_eligible_states", [])) == EXPECTED_EXCLUDED_ZERO_ELIGIBLE_STATES,
        ),
        (
            "Expected guardrails present",
            set(guardrails.keys()) == EXPECTED_GUARDRAILS,
        ),
        (
            "Guardrails all false",
            all(value == 0 for value in guardrails.values()),
        ),
    ]

    for label, ok in checks:
        if not ok:
            return fail(label, {
                "summary_path": str(SUMMARY_PATH),
                "aggregate": aggregate,
                "excluded_zero_eligible_states": data.get("excluded_zero_eligible_states"),
                "duplicate_states": data.get("duplicate_states"),
                "unhealthy_states": data.get("unhealthy_states"),
                "guardrail_true_counts": guardrails,
            })
        pass_check(label)

    pass_check("Committed summary artifact validated", {
        "summary_path": str(SUMMARY_PATH),
        "overlaid_count": aggregate.get("overlaid_count"),
        "wall_clock_elapsed_hours_lower_bound": aggregate.get("wall_clock_elapsed_hours_lower_bound"),
        "worker_cpu_time_hours_approx": aggregate.get("worker_cpu_time_hours_approx"),
    })

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE FULL NATIONAL SUMMARY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
