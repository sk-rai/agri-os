#!/usr/bin/env python3
"""Static contract for the readiness snapshot API read path."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend/app/modules/master_data/api/geography.py"


def main() -> int:
    source = API.read_text(encoding="utf-8")
    helper_start = source.index(
        "def _read_geography_layer_readiness_snapshot("
    )
    route_start = source.index(
        '@router.get("/layer-readiness")',
        helper_start,
    )
    next_route = source.index(
        '@router.get("/nwdp-demographic-profiles/filter-options")',
        route_start,
    )

    helper = source[helper_start:route_start]
    route = source[route_start:next_route]
    combined = helper + route
    normalized = " ".join(combined.split())

    checks = [
        (
            "geography_layer_readiness_snapshots",
            "Dedicated snapshot table is read",
        ),
        (
            "snapshot.is_active = true",
            "Only active snapshots are read",
        ),
        (
            "snapshot.calculation_status = 'READY'",
            "Only ready snapshots are read",
        ),
        (
            "state_or_ut: str = Query(",
            "State filter is required",
        ),
        (
            "district: str = Query(",
            "District filter is required",
        ),
        (
            "limit: int = Query(50, ge=1, le=100)",
            "Response limit is narrowly bounded",
        ),
        (
            "DISTRICT_READINESS_SNAPSHOT_REQUIRED",
            "Missing snapshot fails closed",
        ),
        (
            "READ_ONLY_PRECOMPUTED_DISTRICT_READINESS_SNAPSHOT",
            "Snapshot read mode is explicit",
        ),
        (
            "interactive_computation_attempted",
            "Interactive computation guardrail is explicit",
        ),
        (
            "geometry_computation_attempted",
            "Geometry computation guardrail is explicit",
        ),
        (
            '"snapshot"',
            "Snapshot freshness and provenance are returned",
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
        "geography_village_demographic_profiles",
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
        needle for needle in forbidden
        if needle.lower() in lowered
    ]
    if present:
        raise AssertionError(
            f"Interactive read contains computation/writes: {present}"
        )

    print("PASS Interactive read performs no analytical computation")
    print("PASS Interactive read performs no database writes")
    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "READ STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
