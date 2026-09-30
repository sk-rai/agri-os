#!/usr/bin/env python3
"""Static contract for state/district-gated readiness lookup."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/src/app/(admin)/geography-layer-readiness/page.tsx"


def check(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")


def main() -> int:
    source = PAGE.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "geographyApi .listStates()",
            "Canonical states are loaded independently",
        ),
        (
            "geographyApi.listDistricts(stateId)",
            "Districts load only for the selected state",
        ),
        (
            "!selectedState || !selectedDistrict || !snapshotAvailable",
            "Readiness lookup is gated by snapshot availability",
        ),
        (
            "state_or_ut: selectedState.canonical_name",
            "Canonical state filter is sent",
        ),
        (
            "district: selectedDistrict.canonical_name",
            "Canonical district filter is sent",
        ),
        (
            'limit: "50"',
            "Readiness response is narrowly limited",
        ),
        (
            "disabled={!stateId || loadingDistricts}",
            "District selection requires a state",
        ),
        (
            "!snapshotAvailable || loading",
            "Load requires an available snapshot",
        ),
        (
            "Select a state and district to load readiness",
            "Empty-state guidance is explicit",
        ),
    ]

    for needle, label in checks:
        check(normalized, needle, label)

    panel = "<CoreLayerProjectOverridePanel />"
    if source.count(panel) != 1:
        raise AssertionError(
            "Core override panel must render exactly once"
        )
    print("PASS Core override panel renders exactly once")

    panel_index = source.index(panel)
    data_gate_index = source.index("{data && (")

    if panel_index > data_gate_index:
        raise AssertionError(
            "Core override panel remains dependent on readiness data"
        )
    print("PASS Core override panel is independent of readiness data")

    forbidden = [
        'params.set("limit", String(limit))',
        "void loadMatrix();\n  }, [loadMatrix]);",
        '<option value="">All states</option>',
        '<option value="">All districts</option>',
    ]
    present = [needle for needle in forbidden if needle in source]
    if present:
        raise AssertionError(
            f"Legacy broad readiness lookup remains: {present}"
        )
    print("PASS Broad unfiltered readiness lookup is removed")

    print(
        "GEOGRAPHY LAYER READINESS GATED LOOKUP "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
