#!/usr/bin/env python3
"""Static contract for snapshot coverage in the readiness admin UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/src/app/(admin)/geography-layer-readiness/page.tsx"
API = ROOT / "web/src/lib/api.ts"
SMOKE = ROOT / "web/smoke/geography_layer_readiness_gated_smoke.mjs"


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    smoke = SMOKE.read_text(encoding="utf-8")
    normalized_page = " ".join(page.split())

    checks = [
        (
            "GeographyReadinessSnapshotCoverageResponse",
            api,
            "Coverage response contract exists",
        ),
        (
            "getLayerReadinessSnapshotCoverage",
            api,
            "Coverage API client exists",
        ),
        (
            "stale_after_days",
            api,
            "Freshness window is sent",
        ),
        (
            "Promise.all([ geographyApi.listDistricts(stateId), "
            "geographyApi.getLayerReadinessSnapshotCoverage(stateId)",
            normalized_page,
            "Districts and coverage load together",
        ),
        (
            'availability_status === "AVAILABLE"',
            page,
            "Available snapshots are explicit",
        ),
        (
            'availability_status !== "AVAILABLE"',
            page,
            "Unavailable snapshots are explicit",
        ),
        (
            "!snapshotAvailable || loading",
            normalized_page,
            "Readiness load requires an available snapshot",
        ),
        (
            "Offline snapshot refresh required",
            page,
            "Offline refresh guidance is explicit",
        ),
        (
            "Interactive geometry computation and readiness "
            "aggregation are disabled",
            normalized_page,
            "Interactive computation prohibition is explicit",
        ),
        (
            "project-specific manual assignment",
            page,
            "Manual project assignment route is explicit",
        ),
        (
            "geography-readiness-snapshot-coverage",
            page,
            "Coverage summary has a stable UI boundary",
        ),
        (
            "coverageRequests",
            smoke,
            "Playwright observes coverage requests",
        ),
        (
            "geography_layer_readiness_snapshot_coverage.v1",
            smoke,
            "Playwright validates coverage schema",
        ),
        (
            'option.label.endsWith("· MISSING")',
            smoke,
            "Playwright selects a missing district",
        ),
        (
            "Missing district allowed an interactive "
            "readiness request",
            smoke,
            "Missing district is blocked before lookup",
        ),
        (
            "missing_district_blocked",
            smoke,
            "Missing district result is reported",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    if "_build_geography_layer_readiness_matrix" in page:
        raise AssertionError(
            "Admin UI references offline readiness computation"
        )

    print("PASS Admin UI performs no offline computation")
    print(
        "GEOGRAPHY READINESS SNAPSHOT COVERAGE "
        "ADMIN UI STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
