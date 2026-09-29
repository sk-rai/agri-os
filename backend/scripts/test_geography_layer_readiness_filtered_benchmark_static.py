#!/usr/bin/env python3
"""Static safety contract for filtered readiness benchmark."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "benchmark_geography_layer_readiness_filtered.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")

    checks = [
        (
            "_build_geography_layer_readiness_matrix",
            "Existing readiness builder is benchmarked",
        ),
        (
            'default="Andaman And Nicobar Islands"',
            "Default state fixture is explicit",
        ),
        (
            'default="Nicobars"',
            "Default district fixture is explicit",
        ),
        (
            'default=3',
            "Cold and warm samples are collected",
        ),
        (
            "before_cursor_execute",
            "SQL statements are observed",
        ),
        (
            "after_cursor_execute",
            "SQL durations are recorded",
        ),
        (
            "slowest_statements",
            "Slow statements are summarized",
        ),
        (
            "national_raw_totals",
            "National totals are distinguished",
        ),
        (
            "no_sql_mutations",
            "SQL mutation safety is checked",
        ),
        (
            "protected_counts_unchanged",
            "Protected row counts are checked",
        ),
        (
            '"latency_threshold_enforced": False',
            "Baseline does not invent a latency threshold",
        ),
        (
            "main_matrix_ctes_may_scan_national_tables",
            "Known filter-pushdown risk is explicit",
        ),
    ]

    for needle, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    lowered = source.lower()
    forbidden = [
        "db.commit(",
        "db.flush(",
        "db.add(",
        "db.delete(",
        "insert into ",
        "update geography_",
        "delete from geography_",
    ]
    present = [needle for needle in forbidden if needle in lowered]
    if present:
        raise AssertionError(
            f"Benchmark contains database mutations: {present}"
        )

    print("PASS Benchmark is read-only")
    print(
        "GEOGRAPHY LAYER READINESS FILTERED BENCHMARK "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
