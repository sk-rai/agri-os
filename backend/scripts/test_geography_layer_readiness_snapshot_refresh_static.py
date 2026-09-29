#!/usr/bin/env python3
"""Static contract for offline district readiness snapshot refresh."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "refresh_geography_layer_readiness_snapshot.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "_build_geography_layer_readiness_matrix",
            "Existing calculation is confined to offline refresh",
        ),
        (
            'parser.add_argument("--state", required=True)',
            "State scope is explicit",
        ),
        (
            'parser.add_argument("--district", required=True)',
            "District scope is explicit",
        ),
        (
            '"--apply"',
            "Apply mode is explicit",
        ),
        (
            "REFRESH_DISTRICT_READINESS_SNAPSHOT",
            "Apply confirmation is explicit",
        ),
        (
            "if args.apply and args.confirm != CONFIRMATION",
            "Unconfirmed apply fails closed",
        ),
        (
            "geography_layer_readiness_snapshots",
            "Dedicated snapshot table is used",
        ),
        (
            "set is_active = false",
            "Prior snapshot deactivation is explicit",
        ),
        (
            "insert into geography_layer_readiness_snapshots",
            "Replacement snapshot insertion is explicit",
        ),
        (
            "db.commit()",
            "Apply commits atomically",
        ),
        (
            "readiness_payload_sha256",
            "Payload evidence is checksummed",
        ),
        (
            "OFFLINE_PRECOMPUTED_DISTRICT_SNAPSHOT",
            "Offline computation mode is explicit",
        ),
        (
            "protected_counts_unchanged",
            "Protected domain counts are checked",
        ),
        (
            "interactive_geometry_computation_authorized",
            "Interactive geometry prohibition is explicit",
        ),
        (
            "runtime_activation_authorized",
            "Runtime activation guardrail is explicit",
        ),
        (
            "android_behavior_change_authorized",
            "Android guardrail is explicit",
        ),
    ]

    for needle, label in checks:
        if needle not in source and needle not in normalized:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    normalized_lower = normalized.lower()
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
        mutation
        for mutation in protected_mutations
        if mutation in normalized_lower
    ]
    if present:
        raise AssertionError(
            f"Protected domain mutations found: {present}"
        )

    print("PASS Writes are confined to the snapshot table")
    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "REFRESH STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
