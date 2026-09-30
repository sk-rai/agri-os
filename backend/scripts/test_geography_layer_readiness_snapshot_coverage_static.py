#!/usr/bin/env python3
"""Static contract for readiness snapshot coverage API."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend/app/modules/master_data/api/geography.py"


def main() -> int:
    source = API.read_text(encoding="utf-8")

    start = source.index(
        "def _read_geography_layer_readiness_snapshot_coverage("
    )
    end = source.index(
        "def _read_geography_layer_readiness_snapshot(",
        start,
    )
    helper = source[start:end]

    route_start = source.index(
        '@router.get("/layer-readiness/snapshot-coverage")'
    )
    route_end = source.index(
        '@router.get("/layer-readiness")',
        route_start,
    )
    route = source[route_start:route_end]
    combined = helper + route
    normalized = " ".join(combined.split())

    checks = [
        (
            "geography_states",
            "Canonical states are read",
        ),
        (
            "geography_districts",
            "Canonical districts are read",
        ),
        (
            "geography_layer_readiness_snapshots",
            "Snapshot availability is joined",
        ),
        (
            "state_id: UUID = Query(",
            "State UUID is required",
        ),
        (
            "stale_after_days: int = Query(7, ge=1, le=365)",
            "Freshness window is bounded",
        ),
        (
            '"AVAILABLE"',
            "Available status is explicit",
        ),
        (
            '"STALE"',
            "Stale status is explicit",
        ),
        (
            '"MISSING"',
            "Missing status is explicit",
        ),
        (
            "offline_refresh_required_count",
            "Offline refresh workload is counted",
        ),
        (
            "SNAPSHOT_COVERAGE_READ_ONLY",
            "Read-only mode is explicit",
        ),
        (
            "interactive_computation_attempted",
            "Interactive computation guardrail is explicit",
        ),
        (
            "geometry_computation_attempted",
            "Geometry guardrail is explicit",
        ),
        (
            "snapshot_refresh_attempted",
            "Refresh guardrail is explicit",
        ),
    ]

    for needle, label in checks:
        if needle not in combined and needle not in normalized:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden = [
        "_build_geography_layer_readiness_matrix(",
        "geography_boundary_crosswalk_candidates",
        "geography_boundary_source_features",
        "st_intersection",
        "st_area",
        "st_union",
        "insert into",
        "update ",
        "delete from",
        "db.commit",
        "db.flush",
    ]
    lowered = combined.lower()
    present = [
        needle
        for needle in forbidden
        if needle.lower() in lowered
    ]
    if present:
        raise AssertionError(
            "Coverage path contains computation or writes: "
            f"{present}"
        )

    print("PASS Coverage path performs no readiness computation")
    print("PASS Coverage path performs no database writes")
    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "COVERAGE STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
