#!/usr/bin/env python3
"""Regression for district readiness snapshot coverage."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from sqlalchemy import event, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal, engine
from app.modules.master_data.api.geography import (
    _read_geography_layer_readiness_snapshot_coverage,
)


def main() -> int:
    statements: list[str] = []
    starts: dict[int, float] = {}
    durations_ms: list[float] = []

    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        statements.append(" ".join(statement.lower().split()))
        starts[id(context)] = time.perf_counter()

    def after_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        started = starts.pop(id(context))
        durations_ms.append(
            round((time.perf_counter() - started) * 1000, 3)
        )

    with SessionLocal() as db:
        state_id = db.execute(
            text(
                """
                select id
                from geography_states
                where canonical_name =
                  'Andaman And Nicobar Islands'
                  and is_active = true
                """
            )
        ).scalar_one()

        protected_before = {
            "snapshots": db.execute(
                text(
                    "select count(*) "
                    "from geography_layer_readiness_snapshots"
                )
            ).scalar_one(),
            "districts": db.execute(
                text(
                    "select count(*) "
                    "from geography_districts"
                )
            ).scalar_one(),
        }

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

        started = time.perf_counter()
        try:
            payload = (
                _read_geography_layer_readiness_snapshot_coverage(
                    db=db,
                    state_id=state_id,
                    stale_after_days=7,
                )
            )
        finally:
            elapsed_ms = round(
                (time.perf_counter() - started) * 1000,
                3,
            )
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

        protected_after = {
            "snapshots": db.execute(
                text(
                    "select count(*) "
                    "from geography_layer_readiness_snapshots"
                )
            ).scalar_one(),
            "districts": db.execute(
                text(
                    "select count(*) "
                    "from geography_districts"
                )
            ).scalar_one(),
        }

    rows = payload["rows"]
    by_district = {
        row["district"]: row
        for row in rows
    }
    summary = payload["summary"]

    mutation_prefixes = (
        "insert ",
        "update ",
        "delete ",
        "merge ",
        "alter ",
        "create ",
        "drop ",
        "truncate ",
    )
    mutations = [
        statement
        for statement in statements
        if statement.startswith(mutation_prefixes)
    ]

    checks = {
        "coverage_schema_exact": (
            payload["schema_version"]
            == "geography_layer_readiness_snapshot_coverage.v1"
        ),
        "state_exact": (
            payload["state"]["state_or_ut"]
            == "Andaman And Nicobar Islands"
        ),
        "district_partition_exact": (
            summary["canonical_district_count"]
            == summary["available_count"]
            + summary["stale_count"]
            + summary["missing_count"]
        ),
        "offline_refresh_count_exact": (
            summary["offline_refresh_required_count"]
            == summary["stale_count"]
            + summary["missing_count"]
        ),
        "nicobars_available": (
            by_district["Nicobars"]["availability_status"]
            == "AVAILABLE"
            and by_district["Nicobars"][
                "offline_refresh_required"
            ]
            is False
            and bool(by_district["Nicobars"]["snapshot_id"])
        ),
        "missing_districts_explicit": all(
            row["offline_refresh_required"]
            for row in rows
            if row["availability_status"] == "MISSING"
        ),
        "single_sql_statement": len(statements) == 1,
        "canonical_and_snapshot_tables_only": (
            len(statements) == 1
            and "geography_states" in statements[0]
            and "geography_districts" in statements[0]
            and "geography_layer_readiness_snapshots"
                in statements[0]
        ),
        "sub_second_read": elapsed_ms < 1000,
        "no_sql_mutations": not mutations,
        "protected_counts_unchanged": (
            protected_before == protected_after
        ),
        "interactive_computation_absent": (
            payload["guardrails"][
                "interactive_computation_attempted"
            ]
            is False
        ),
        "geometry_computation_absent": (
            payload["guardrails"][
                "geometry_computation_attempted"
            ]
            is False
        ),
    }

    for label, passed in checks.items():
        if not passed:
            raise AssertionError(
                f"{label}: failed; payload={payload!r}; "
                f"statements={statements!r}"
            )
        print(f"PASS {label.replace('_', ' ').title()}")

    print(json.dumps({
        "schema_version":
            "geography_layer_readiness_snapshot_coverage_regression.v1",
        "status": "PASSED",
        "elapsed_ms": elapsed_ms,
        "sql_statement_count": len(statements),
        "sql_durations_ms": durations_ms,
        "state": payload["state"],
        "summary": summary,
        "districts": [
            {
                "district": row["district"],
                "district_lgd_code":
                    row["district_lgd_code"],
                "availability_status":
                    row["availability_status"],
                "offline_refresh_required":
                    row["offline_refresh_required"],
            }
            for row in rows
        ],
        "protected_counts_before": protected_before,
        "protected_counts_after": protected_after,
        "checks": checks,
    }, indent=2, sort_keys=True))

    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "COVERAGE REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
