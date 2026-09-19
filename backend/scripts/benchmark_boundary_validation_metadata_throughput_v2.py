#!/usr/bin/env python3
"""Rollback-only benchmark for validation-metadata throughput V2."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from app.core.database import engine  # noqa: E402
from boundary_validation_metadata_throughput_v2 import (  # noqa: E402
    MAXIMUM_ROWS_PER_STATE_TRANSACTION,
    execute_apply_transaction,
    execute_rollback_transaction,
)
from test_boundary_validation_metadata_throughput_v2_postgres import (  # noqa: E402
    MARKER,
    STATE_NAME,
    build_plan,
    canonical,
    database_guardrail_counts,
    source_snapshots,
)


def wal_lsn(conn: Any) -> str:
    return str(
        conn.execute(
            text("select pg_current_wal_lsn()::text")
        ).scalar_one()
    )


def wal_bytes(
    conn: Any,
    finish: str,
    start: str,
) -> int:
    return int(
        conn.execute(
            text("""
                select pg_wal_lsn_diff(
                    cast(:finish as pg_lsn),
                    cast(:start as pg_lsn)
                )::bigint
            """),
            {
                "finish": finish,
                "start": start,
            },
        ).scalar_one()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--confirm-rollback-only-benchmark",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_rollback_only_benchmark:
        raise SystemExit(
            "ROLLBACK_ONLY_BENCHMARK_CONFIRMATION_REQUIRED"
        )
    if not (
        1
        <= args.rows
        <= MAXIMUM_ROWS_PER_STATE_TRANSACTION
    ):
        raise SystemExit(
            "BENCHMARK_ROW_COUNT_OUT_OF_RANGE"
        )

    planning_started = time.perf_counter()
    with tempfile.TemporaryDirectory(
        prefix=f"validation-metadata-v2-{args.rows}-"
    ) as temporary:
        plan = build_plan(
            Path(temporary),
            args.rows,
        )
    planning_seconds = (
        time.perf_counter() - planning_started
    )

    plan_rows = plan["rows"]
    plan_checksum = plan["batch"]["plan_checksum"]
    import_batch_id = plan["scope"]["import_batch_id"]
    source_sha256 = plan["source"]["sha256"]

    rollback_token = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "agri-os:validation-metadata-throughput-v2:"
                f"benchmark:{args.rows}:{plan_checksum}"
            ),
        )
    )

    rows: list[dict[str, Any]] = []
    for planned in plan_rows:
        row = dict(planned)
        row["event_id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "agri-os:validation-metadata-throughput-v2:"
                    f"benchmark:{args.rows}:"
                    f"{plan_checksum}:"
                    f"{planned['source_feature_id']}"
                ),
            )
        )
        rows.append(row)

    feature_ids = [
        row["source_feature_id"]
        for row in rows
    ]

    apply_parameters = {
        "state_or_ut": STATE_NAME,
        "source_sha256": source_sha256,
        "plan_checksum": plan_checksum,
        "rollback_token": rollback_token,
        "import_batch_id": import_batch_id,
        "marker": MARKER,
        "event_metadata": json.dumps({
            "benchmark": True,
            "rollback_only": True,
            "row_count": args.rows,
        }),
        "applied_by": "v2-rollback-only-benchmark",
        "apply_report": json.dumps({
            "result": "APPLIED",
            "benchmark": True,
        }),
    }

    rollback_parameters = {
        "plan_checksum": plan_checksum,
        "rollback_token": rollback_token,
        "rollback_report": json.dumps({
            "result": "ROLLED_BACK",
            "benchmark": True,
        }),
        "operator": "v2-rollback-only-benchmark",
    }

    with engine.connect() as connection:
        baseline_counts = database_guardrail_counts(
            connection
        )
        baseline_sources = source_snapshots(
            connection,
            feature_ids,
        )
        starting_lsn = wal_lsn(connection)

    if len(baseline_sources) != args.rows:
        raise AssertionError(
            "BENCHMARK_SOURCE_ROW_COUNT_MISMATCH"
        )

    apply_result: dict[str, Any] | None = None
    rollback_result: dict[str, Any] | None = None
    apply_seconds = 0.0
    rollback_seconds = 0.0
    transaction_seconds = 0.0

    transaction_started = time.perf_counter()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            apply_started = time.perf_counter()
            apply_result = execute_apply_transaction(
                connection,
                rows=rows,
                authorized_row_count=args.rows,
                parameters=apply_parameters,
            )
            apply_seconds = (
                time.perf_counter() - apply_started
            )

            rollback_started = time.perf_counter()
            rollback_result = (
                execute_rollback_transaction(
                    connection,
                    authorized_row_count=args.rows,
                    parameters=rollback_parameters,
                )
            )
            rollback_seconds = (
                time.perf_counter() - rollback_started
            )

            restored = source_snapshots(
                connection,
                feature_ids,
            )
            if canonical(restored) != canonical(
                baseline_sources
            ):
                raise AssertionError(
                    "BENCHMARK_SOURCE_RESTORATION_MISMATCH"
                )

            transaction.rollback()
        except BaseException:
            transaction.rollback()
            raise

    transaction_seconds = (
        time.perf_counter() - transaction_started
    )

    with engine.connect() as connection:
        final_counts = database_guardrail_counts(
            connection
        )
        final_sources = source_snapshots(
            connection,
            feature_ids,
        )
        persisted_events = int(
            connection.execute(text("""
                select count(*)
                from geography_boundary_validation_metadata_events
                where plan_checksum = :plan_checksum
                  and rollback_token = :rollback_token
            """), rollback_parameters).scalar_one()
        )
        ending_lsn = wal_lsn(connection)
        generated_wal_bytes = wal_bytes(
            connection,
            ending_lsn,
            starting_lsn,
        )

    if final_counts != baseline_counts:
        raise AssertionError(
            "BENCHMARK_DATABASE_COUNTS_CHANGED"
        )
    if canonical(final_sources) != canonical(
        baseline_sources
    ):
        raise AssertionError(
            "BENCHMARK_SOURCE_ROWS_CHANGED"
        )
    if persisted_events != 0:
        raise AssertionError(
            "BENCHMARK_EVENTS_PERSISTED"
        )

    result = {
        "schema_version":
            "boundary_validation_metadata_throughput_v2_benchmark.v1",
        "mode": "ROLLBACK_ONLY",
        "state_or_ut": STATE_NAME,
        "row_count": args.rows,
        "planning_seconds": round(
            planning_seconds,
            3,
        ),
        "apply_seconds": round(
            apply_seconds,
            3,
        ),
        "rollback_seconds": round(
            rollback_seconds,
            3,
        ),
        "transaction_seconds": round(
            transaction_seconds,
            3,
        ),
        "apply_rows_per_second": round(
            args.rows / apply_seconds,
            2,
        ),
        "rollback_rows_per_second": round(
            args.rows / rollback_seconds,
            2,
        ),
        "wal_bytes_observed": generated_wal_bytes,
        "wal_bytes_per_row": round(
            generated_wal_bytes / args.rows,
            2,
        ),
        "apply_result": apply_result,
        "rollback_result": rollback_result,
        "database_counts_unchanged":
            final_counts == baseline_counts,
        "source_rows_unchanged":
            canonical(final_sources)
            == canonical(baseline_sources),
        "persisted_event_count": persisted_events,
        "healthy": True,
    }

    print(json.dumps(
        result,
        indent=2,
        sort_keys=True,
    ))
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        f"{args.rows}-ROW BENCHMARK PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
