#!/usr/bin/env python3
"""Transactional regression for the readiness snapshot read path."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import event, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal, engine
from app.modules.master_data.api.geography import (
    _read_geography_layer_readiness_snapshot,
)


def main() -> int:
    statements: list[str] = []
    durations_ms: list[float] = []
    starts: dict[int, float] = {}

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
        protected_before = {
            "snapshots": db.execute(
                text(
                    "select count(*) "
                    "from geography_layer_readiness_snapshots"
                )
            ).scalar_one(),
            "climate_mappings": db.execute(
                text(
                    "select count(*) "
                    "from geography_climate_region_mappings"
                )
            ).scalar_one(),
            "boundary_candidates": db.execute(
                text(
                    "select count(*) "
                    "from geography_boundary_crosswalk_candidates"
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
            payload = _read_geography_layer_readiness_snapshot(
                db=db,
                state_or_ut="Andaman And Nicobar Islands",
                district="Nicobars",
                limit=50,
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
            "climate_mappings": db.execute(
                text(
                    "select count(*) "
                    "from geography_climate_region_mappings"
                )
            ).scalar_one(),
            "boundary_candidates": db.execute(
                text(
                    "select count(*) "
                    "from geography_boundary_crosswalk_candidates"
                )
            ).scalar_one(),
        }

        missing_failed_closed = False
        try:
            _read_geography_layer_readiness_snapshot(
                db=db,
                state_or_ut="Andaman And Nicobar Islands",
                district="DISTRICT_WITHOUT_SNAPSHOT",
                limit=50,
            )
        except HTTPException as exc:
            missing_failed_closed = (
                exc.status_code == 409
                and exc.detail.get("status")
                == "DISTRICT_READINESS_SNAPSHOT_REQUIRED"
                and exc.detail.get(
                    "interactive_computation_attempted"
                )
                is False
            )

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

    checks: dict[str, Any] = {
        "snapshot_schema_retained": (
            payload["schema_version"]
            == "geography_layer_readiness_matrix.v1"
        ),
        "snapshot_mode_exact": (
            payload["mode"]
            == "READ_ONLY_PRECOMPUTED_DISTRICT_READINESS_SNAPSHOT"
        ),
        "scope_exact": payload["filters"] == {
            "state_or_ut": "Andaman And Nicobar Islands",
            "district": "Nicobars",
            "limit": 50,
        },
        "one_district_row": (
            len(payload["rows"]) == 1
            and payload["rows"][0]["district_lgd_code"] == "603"
        ),
        "snapshot_provenance_present": bool(
            payload["snapshot"]["snapshot_id"]
            and payload["snapshot"]["computed_at"]
            and payload["snapshot"]["refresh_run_id"]
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
        "single_sql_statement": len(statements) == 1,
        "snapshot_table_only": (
            len(statements) == 1
            and "geography_layer_readiness_snapshots"
            in statements[0]
        ),
        "no_sql_mutations": not mutations,
        "protected_counts_unchanged": (
            protected_before == protected_after
        ),
        "sub_second_read": elapsed_ms < 1000,
        "missing_snapshot_fails_closed":
            missing_failed_closed,
    }

    for label, passed in checks.items():
        if not passed:
            raise AssertionError(
                f"{label}: failed; "
                f"statements={statements!r}, "
                f"elapsed_ms={elapsed_ms}"
            )
        print(f"PASS {label.replace('_', ' ').title()}")

    print(json.dumps({
        "schema_version":
            "geography_layer_readiness_snapshot_read_regression.v1",
        "status": "PASSED",
        "elapsed_ms": elapsed_ms,
        "sql_statement_count": len(statements),
        "sql_durations_ms": durations_ms,
        "snapshot_id": payload["snapshot"]["snapshot_id"],
        "computed_at": payload["snapshot"]["computed_at"],
        "age_seconds": payload["snapshot"]["age_seconds"],
        "row_count": len(payload["rows"]),
        "protected_counts_before": protected_before,
        "protected_counts_after": protected_after,
        "checks": checks,
    }, indent=2, sort_keys=True))

    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "READ PATH REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
