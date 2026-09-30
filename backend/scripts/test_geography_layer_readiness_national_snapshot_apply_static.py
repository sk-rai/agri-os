#!/usr/bin/env python3
"""Static contract for national readiness snapshot apply."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "apply_geography_layer_readiness_national_snapshots.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "EXPECTED_DISTRICT_COUNT = 779",
            "District count is pinned",
        ),
        (
            "APPLY_NATIONAL_DISTRICT_READINESS_SNAPSHOTS",
            "Apply confirmation is explicit",
        ),
        (
            "--expected-plan-id",
            "Reviewed plan ID is required",
        ),
        (
            "rows_sha256_pinned",
            "Rows hash is pinned",
        ),
        (
            "candidate_payload_hashes_valid",
            "Every payload hash is validated",
        ),
        (
            "canonical_partition_exact",
            "Canonical district partition is validated",
        ),
        (
            "existing_snapshot_state_matches_plan",
            "Existing snapshot state is validated",
        ),
        (
            "update geography_layer_readiness_snapshots",
            "Replacement deactivation is snapshot-only",
        ),
        (
            "insert into geography_layer_readiness_snapshots",
            "Insertion is snapshot-only",
        ),
        (
            "active_after_count != EXPECTED_DISTRICT_COUNT",
            "Active coverage is verified before commit",
        ),
        (
            "db.rollback()",
            "Failed apply rolls back",
        ),
        (
            "db.commit()",
            "Successful apply commits once",
        ),
        (
            "historical_snapshots_preserved",
            "Historical rows are preserved",
        ),
        (
            "readiness_recomputation_authorized",
            "Readiness recomputation is forbidden",
        ),
        (
            "geometry_computation_authorized",
            "Geometry computation is forbidden",
        ),
        (
            "runtime_activation_authorized",
            "Runtime activation remains unchanged",
        ),
        (
            "android_behavior_change_authorized",
            "Android behavior remains unchanged",
        ),
    ]

    for needle, label in checks:
        if needle not in source and needle not in normalized:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    lowered = normalized.lower()
    protected_mutations = [
        "update geography_states",
        "update geography_districts",
        "update geography_villages",
        "update geography_climate_region_mappings",
        "update geography_boundary_crosswalk_candidates",
        "update geography_core_layer_project_overrides",
        "insert into geography_climate_region_mappings",
        "insert into geography_boundary_crosswalk_candidates",
    ]
    present = [
        item for item in protected_mutations
        if item in lowered
    ]
    if present:
        raise AssertionError(
            f"Protected domain mutations found: {present}"
        )

    forbidden_computation = [
        "_build_geography_layer_readiness_matrix",
        "st_intersection",
        "st_area",
        "st_union",
    ]
    present = [
        item for item in forbidden_computation
        if item in lowered
    ]
    if present:
        raise AssertionError(
            f"Apply contains readiness/geometry computation: {present}"
        )

    print("PASS Writes are confined to the snapshot table")
    print("PASS Apply performs no readiness or geometry computation")
    print(
        "GEOGRAPHY LAYER READINESS NATIONAL "
        "SNAPSHOT APPLY STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
