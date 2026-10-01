#!/usr/bin/env python3
"""Static contract for the local admin-only lookup canary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANARY = (
    ROOT / "backend" / "scripts"
    / "run_nwdp_runtime_lookup_admin_pilot_canary.py"
)


def main() -> int:
    source = CANARY.read_text(encoding="utf-8")

    contracts = [
        (
            "nwdp_runtime_lookup_admin_pilot_canary.v1",
            "Canary schema is versioned",
        ),
        (
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
            "Authorization scope is exact",
        ),
        (
            "EXPECTED_ACTIVE_TOTAL = 467_397",
            "Runtime total is pinned",
        ),
        (
            "create_web_ui_smoke_session.py",
            "Existing authenticated session creator is reused",
        ),
        (
            "ENTERPRISE_ADMIN",
            "Admin-only session is required",
        ),
        (
            "ST_PointOnSurface",
            "In-boundary sample is database-derived",
        ),
        (
            "expected_feature_returned",
            "Expected feature identity is required",
        ),
        (
            "outside_unmatched",
            "Outside lookup is required",
        ),
        (
            "inside_tier_free",
            "FREE tier is required",
        ),
        (
            "inside_remaining_exact",
            "Actor budget decrement is exact",
        ),
        (
            "three_budget_keys_created",
            "Three-dimensional budget is required",
        ),
        (
            "budget_key_ttls_bounded",
            "Budget TTLs are bounded",
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
            '"token_logged": False',
            "Token is not logged",
        ),
        (
            '"key_material_reported": False',
            "Redis key material is not reported",
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
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false",
            "Rollback command is explicit",
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
        "flushdb(",
        "flushall(",
        "tenant.config =",
    ]
    lowered = source.lower()
    for token in forbidden:
        if token.lower() in lowered:
            raise AssertionError(
                f"Forbidden canary mutation: {token}"
            )

    print("PASS Canary contains no geography writes")
    print("PASS Canary contains no tenant-tier mutation")
    print(
        "NWDP LOCAL ADMIN-ONLY LOOKUP PILOT "
        "CANARY STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
