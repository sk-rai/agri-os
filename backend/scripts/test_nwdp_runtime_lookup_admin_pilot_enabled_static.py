#!/usr/bin/env python3
"""Static contract for the enabled local admin-only pilot audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT / "backend" / "scripts"
    / "audit_nwdp_runtime_lookup_admin_pilot_enabled.py"
)


def main() -> int:
    source = AUDIT.read_text(encoding="utf-8")

    contracts = [
        (
            "nwdp_runtime_lookup_admin_pilot_enabled_audit.v1",
            "Audit schema is versioned",
        ),
        (
            "EXPECTED_ACTIVE_TOTAL = 467_397",
            "Runtime total is pinned",
        ),
        (
            "run_nwdp_runtime_lookup_admin_pilot_canary.py",
            "Committed live canary is reused",
        ),
        (
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
            "Enabled scope is exact",
        ),
        (
            "namespace_started_clean",
            "Clean Redis namespace is required",
        ),
        (
            "canary_process_passed",
            "Canary process success is required",
        ),
        (
            "inside_lookup_unambiguous",
            "Matched lookup must be unambiguous",
        ),
        (
            "outside_lookup_unmatched",
            "Outside lookup must remain unmatched",
        ),
        (
            "anonymous_access_denied",
            "Anonymous access must be denied",
        ),
        (
            "free_budget_decrement_exact",
            "FREE budget decrement is exact",
        ),
        (
            "three_budget_keys_present",
            "Three-dimensional Redis budget is required",
        ),
        (
            "budget_ttls_bounded",
            "Redis TTLs are bounded",
        ),
        (
            "database_counts_unchanged",
            "Database counts are compared",
        ),
        (
            "candidate_state_unchanged",
            "Candidate state is protected",
        ),
        (
            "project_matches_unchanged",
            "Project state is protected",
        ),
        (
            '"customer_access_authorized": False',
            "Customer access remains unauthorized",
        ),
        (
            '"android_access_authorized": False',
            "Android access remains unauthorized",
        ),
        (
            '"public_access_authorized": False',
            "Public access remains unauthorized",
        ),
        (
            '"production_access_authorized": False',
            "Production access remains unauthorized",
        ),
        (
            '"database_writes_attempted": False',
            "Geography audit remains read-only",
        ),
        (
            "writes_are_transient_rate_limit_counters",
            "Transient Redis writes are explicit",
        ),
        (
            "runtime_data_deactivation_required",
            "Rollback preserves runtime data",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden = [
        "update geography_",
        "insert into ",
        "delete from ",
        "alter table ",
        "drop table ",
        "tenant.config =",
        "flushdb(",
        "flushall(",
    ]
    lowered = source.lower()
    for token in forbidden:
        if token.lower() in lowered:
            raise AssertionError(
                f"Forbidden audit mutation: {token}"
            )

    print("PASS Audit contains no geography mutations")
    print("PASS Audit contains no tenant-tier mutation")
    print(
        "NWDP LOCAL ADMIN-ONLY LOOKUP ENABLED "
        "AUDIT STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
