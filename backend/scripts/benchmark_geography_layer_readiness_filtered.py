#!/usr/bin/env python3
"""Benchmark one district-scoped geography readiness request.

This diagnostic is read-only. It records overall latency and individual SQL
statement timings so filter-pushdown work can target the actual bottlenecks.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import event, text

from app.core.database import SessionLocal, engine
from app.modules.master_data.api.geography import (
    _build_geography_layer_readiness_matrix,
)


MUTATION_PREFIXES = (
    "insert ",
    "update ",
    "delete ",
    "merge ",
    "alter ",
    "create ",
    "drop ",
    "truncate ",
)


def classify_statement(statement: str) -> str:
    normalized = " ".join(statement.lower().split())

    if "with base as" in normalized:
        return "readiness_matrix"
    if "raw_boundary_candidate_count" in normalized:
        return "national_raw_totals"
    if "geography_boundary_project_matches" in normalized:
        return "project_boundary_rollup"
    if "geometry_validation_status" in normalized:
        return "boundary_geometry_validation_rollup"
    if "repair_class" in normalized:
        return "boundary_geometry_repair_rollup"
    if "geography_boundary_runtime_promotion" in normalized:
        return "runtime_promotion_rollup"
    if "provider" in normalized or "weather" in normalized:
        return "external_api_rollup"
    return "other_read_query"


def protected_counts(db) -> dict[str, int]:
    return {
        "climate_mappings": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_climate_region_mappings"
                )
            ).scalar_one()
        ),
        "core_project_overrides": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_core_layer_project_overrides"
                )
            ).scalar_one()
        ),
        "boundary_candidates": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_boundary_crosswalk_candidates"
                )
            ).scalar_one()
        ),
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * fraction)),
    )
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        default="Andaman And Nicobar Islands",
    )
    parser.add_argument("--district", default="Nicobars")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.iterations < 1 or args.iterations > 10:
        raise SystemExit("--iterations must be between 1 and 10")

    statement_events: list[dict[str, Any]] = []
    active_starts: dict[int, tuple[float, str]] = {}
    mutations: list[str] = []

    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        normalized = " ".join(statement.lower().split())
        prefix = normalized.lstrip()
        if prefix.startswith(MUTATION_PREFIXES):
            mutations.append(prefix[:160])

        active_starts[id(context)] = (
            time.perf_counter(),
            classify_statement(statement),
        )

    def after_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        started, label = active_starts.pop(
            id(context),
            (time.perf_counter(), "unknown"),
        )
        statement_events.append(
            {
                "label": label,
                "elapsed_ms": round(
                    (time.perf_counter() - started) * 1000,
                    3,
                ),
            }
        )

    with SessionLocal() as db:
        before = protected_counts(db)

        event.listen(
            engine,
            "before_cursor_execute",
            before_cursor_execute,
        )
        event.listen(
            engine,
            "after_cursor_execute",
            after_cursor_execute,
        )

        samples = []
        payloads = []

        try:
            for iteration in range(1, args.iterations + 1):
                event_start = len(statement_events)
                started = time.perf_counter()

                payload = _build_geography_layer_readiness_matrix(
                    db=db,
                    state_or_ut=args.state,
                    district=args.district,
                    limit=args.limit,
                )

                elapsed_ms = round(
                    (time.perf_counter() - started) * 1000,
                    3,
                )
                iteration_events = statement_events[event_start:]

                samples.append(
                    {
                        "iteration": iteration,
                        "classification": (
                            "FIRST_RUN"
                            if iteration == 1
                            else "WARM_RUN"
                        ),
                        "elapsed_ms": elapsed_ms,
                        "sql_statement_count": len(iteration_events),
                        "sql_elapsed_ms": round(
                            sum(
                                item["elapsed_ms"]
                                for item in iteration_events
                            ),
                            3,
                        ),
                        "slowest_statements": sorted(
                            iteration_events,
                            key=lambda item: item["elapsed_ms"],
                            reverse=True,
                        )[:8],
                    }
                )
                payloads.append(payload)
        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                before_cursor_execute,
            )
            event.remove(
                engine,
                "after_cursor_execute",
                after_cursor_execute,
            )

        after = protected_counts(db)

    durations = [sample["elapsed_ms"] for sample in samples]
    warm_durations = durations[1:] or durations

    aggregate_by_label: dict[str, list[float]] = defaultdict(list)
    for item in statement_events:
        aggregate_by_label[item["label"]].append(
            item["elapsed_ms"]
        )

    statement_summary = {
        label: {
            "executions": len(values),
            "total_ms": round(sum(values), 3),
            "mean_ms": round(statistics.mean(values), 3),
            "max_ms": round(max(values), 3),
        }
        for label, values in sorted(
            aggregate_by_label.items(),
            key=lambda item: sum(item[1]),
            reverse=True,
        )
    }

    filter_checks = [
        payload.get("filters") == {
            "state_or_ut": args.state,
            "district": args.district,
            "limit": args.limit,
        }
        for payload in payloads
    ]
    row_checks = [
        len(payload.get("rows", [])) == 1
        and payload["rows"][0].get("state_or_ut") == args.state
        and payload["rows"][0].get("district") == args.district
        for payload in payloads
    ]

    checks = {
        "district_filter_exact": all(filter_checks),
        "one_scoped_row_returned": all(row_checks),
        "no_sql_mutations": not mutations,
        "protected_counts_unchanged": before == after,
        "timing_samples_complete": len(samples) == args.iterations,
        "sql_timings_recorded": all(
            sample["sql_statement_count"] > 0
            for sample in samples
        ),
    }

    report = {
        "schema_version":
            "geography_layer_readiness_filtered_benchmark.v1",
        "status": (
            "FILTERED_READINESS_BENCHMARK_COMPLETE"
            if all(checks.values())
            else "FILTERED_READINESS_BENCHMARK_INVALID"
        ),
        "healthy": all(checks.values()),
        "scope": {
            "state_or_ut": args.state,
            "district": args.district,
            "limit": args.limit,
        },
        "iterations": args.iterations,
        "latency_ms": {
            "first_run": durations[0],
            "warm_min": round(min(warm_durations), 3),
            "warm_mean": round(
                statistics.mean(warm_durations),
                3,
            ),
            "warm_p95": round(
                percentile(warm_durations, 0.95),
                3,
            ),
            "maximum": round(max(durations), 3),
        },
        "samples": samples,
        "statement_summary": statement_summary,
        "checks": checks,
        "mutations_detected": mutations,
        "protected_counts_before": before,
        "protected_counts_after": after,
        "observations": {
            "latency_threshold_enforced": False,
            "purpose":
                "Establish evidence before filter-pushdown changes",
            "national_rollups_present": (
                "national_raw_totals" in statement_summary
            ),
            "main_matrix_is_district_filtered": True,
            "main_matrix_ctes_may_scan_national_tables": True,
        },
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
