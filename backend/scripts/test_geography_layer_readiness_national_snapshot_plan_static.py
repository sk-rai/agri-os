#!/usr/bin/env python3
"""Static contract for national readiness snapshot planner."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "plan_geography_layer_readiness_national_snapshots.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")

    checks = [
        (
            "EXPECTED_DISTRICT_COUNT = 779",
            "Canonical district count is pinned",
        ),
        (
            "_build_geography_layer_readiness_matrix",
            "Existing calculation is reused offline",
        ),
        (
            "state_or_ut=None",
            "National state scope is explicit",
        ),
        (
            "district=None",
            "National district scope is explicit",
        ),
        (
            "national_calculation_count",
            "Single national calculation is reported",
        ),
        (
            "canonical_partition_exact",
            "Canonical district partition is exact",
        ),
        (
            "readiness_identity_unique",
            "Readiness identities must be unique",
        ),
        (
            "all_candidates_single_row",
            "Each candidate contains one district row",
        ),
        (
            "shared_national_context_fields",
            "Shared context is explicitly labelled",
        ),
        (
            "REFERENCE_ONLY_NOT_DISTRICT_GEOMETRY_COMPUTATION",
            "Shared context semantics are explicit",
        ),
        (
            "INSERT_NEW_ACTIVE_SNAPSHOT",
            "New snapshot action is planned",
        ),
        (
            "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT",
            "Identical snapshot reuse is planned",
        ),
        (
            "REPLACE_CHANGED_ACTIVE_SNAPSHOT",
            "Changed snapshot replacement is planned",
        ),
        (
            "database_writes_attempted",
            "Database write status is explicit",
        ),
        (
            "not_authorized_for_apply",
            "Apply remains unauthorized",
        ),
        (
            "interactive_computation_disabled",
            "Interactive computation remains disabled",
        ),
        (
            "runtime_activation_unchanged",
            "Runtime activation remains unchanged",
        ),
        (
            "android_behavior_unchanged",
            "Android behavior remains unchanged",
        ),
    ]

    for needle, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    lowered = " ".join(source.lower().split())
    forbidden = [
        "insert into ",
        "update geography_",
        "delete from geography_",
        "db.commit(",
        "db.flush(",
        "db.add(",
        "db.delete(",
    ]
    present = [
        needle for needle in forbidden
        if needle in lowered
    ]
    if present:
        raise AssertionError(
            f"Planner contains database writes: {present}"
        )

    print("PASS Planner contains no database writes")
    print(
        "GEOGRAPHY LAYER READINESS NATIONAL "
        "SNAPSHOT PLAN STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
