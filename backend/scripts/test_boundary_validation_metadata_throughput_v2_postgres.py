#!/usr/bin/env python3
"""Rollback-only PostgreSQL fixture for validation-metadata throughput V2."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
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
    EVENT_TABLE,
    SOURCE_TABLE,
    execute_apply_transaction,
    execute_rollback_transaction,
)


STATE_SLUG = "uttar_pradesh"
STATE_NAME = "Uttar Pradesh"
MARKER = "authorized_state_batch_validation_metadata_apply"


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def database_guardrail_counts(conn: Any) -> dict[str, int]:
    row = conn.execute(text(f"""
        select
          (
            select count(*)
            from {SOURCE_TABLE}
            where geometry_validation_status = 'NOT_VALIDATED'
          ) as not_validated_rows,
          (
            select count(*)
            from {SOURCE_TABLE}
            where geometry_validation_status = 'VALIDATED'
          ) as validated_rows,
          (
            select count(*)
            from {SOURCE_TABLE}
            where eligible_for_runtime_after_promotion = true
          ) as runtime_eligible_source_rows,
          (
            select count(*)
            from {EVENT_TABLE}
          ) as validation_event_rows,
          (
            select count(*)
            from geography_boundary_crosswalk_candidates
          ) as candidate_rows,
          (
            select count(*)
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidate_rows,
          (
            select count(*)
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidate_rows,
          (
            select count(*)
            from geography_boundary_runtime_sets
          ) as runtime_set_rows,
          (
            select count(*)
            from geography_boundary_runtime_features
          ) as runtime_feature_rows,
          (
            select count(*)
            from geography_boundary_runtime_crosswalks
          ) as runtime_crosswalk_rows
    """)).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def source_snapshots(
    conn: Any,
    feature_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(text(f"""
            select
              id::text as source_feature_id,
              import_batch_id::text as import_batch_id,
              source_feature_index,
              source_geometry_hash,
              source_bbox,
              transformed_bbox,
              transformed_centroid,
              geometry_validation_status,
              eligible_for_runtime_after_promotion,
              metadata
            from {SOURCE_TABLE}
            where id = any(cast(:ids as uuid[]))
            order by source_feature_index
        """), {"ids": feature_ids}).mappings()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def build_plan(output_dir: Path) -> dict[str, Any]:
    raw_dir = (
        ROOT
        / "data/raw/nwdp_boundary_all_state"
        / "20260824T110250Z"
    )
    source_path = raw_dir / f"{STATE_SLUG}.geojson"

    if not source_path.is_file():
        raise AssertionError(
            f"FIXTURE_SOURCE_FILE_NOT_FOUND:{source_path}"
        )

    expected_source_sha256 = sha256_file(source_path)

    command = [
        sys.executable,
        str(
            BACKEND
            / "scripts"
            / (
                "plan_boundary_geometry_validation_metadata_"
                "bounded_state.py"
            )
        ),
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--expected-source-sha256",
        expected_source_sha256,
        "--raw-dir",
        str(raw_dir),
        "--cursor-after-index",
        "-1",
        "--limit",
        "2",
        "--output-dir",
        str(output_dir),
    ]

    subprocess.run(command, check=True)

    path = (
        output_dir
        / (
            f"{STATE_SLUG}_"
            "bounded_validation_metadata_plan.json"
        )
    )
    plan = json.loads(
        path.read_text(encoding="utf-8")
    )

    if plan.get("healthy") is not True:
        raise AssertionError("FIXTURE_PLAN_NOT_HEALTHY")
    if len(plan.get("rows") or []) != 2:
        raise AssertionError(
            "FIXTURE_REQUIRES_EXACTLY_TWO_ROWS"
        )

    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-rollback-only-fixture",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_rollback_only_fixture:
        raise SystemExit(
            "ROLLBACK_ONLY_FIXTURE_CONFIRMATION_REQUIRED"
        )

    with tempfile.TemporaryDirectory(
        prefix="validation-metadata-v2-"
    ) as temporary:
        plan = build_plan(Path(temporary))

    plan_rows = plan["rows"]
    plan_checksum = plan["batch"]["plan_checksum"]
    import_batch_id = plan["scope"]["import_batch_id"]
    source_sha256 = plan["source"]["sha256"]

    rollback_token = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "agri-os:validation-metadata-throughput-v2:"
                f"{plan_checksum}:rollback-only-fixture"
            ),
        )
    )

    rows = []
    for planned in plan_rows:
        row = dict(planned)
        row["event_id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "agri-os:validation-metadata-throughput-v2:"
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

    common = {
        "state_or_ut": STATE_NAME,
        "source_sha256": source_sha256,
        "plan_checksum": plan_checksum,
        "rollback_token": rollback_token,
        "import_batch_id": import_batch_id,
        "marker": MARKER,
        "event_metadata": json.dumps({
            "fixture": True,
            "rollback_only": True,
            "schema_version":
                "boundary_validation_metadata_throughput_v2",
        }),
        "applied_by": "v2-postgres-fixture",
        "apply_report": json.dumps({
            "result": "APPLIED",
            "fixture": True,
        }),
    }

    rollback_parameters = {
        "plan_checksum": plan_checksum,
        "rollback_token": rollback_token,
        "rollback_report": json.dumps({
            "result": "ROLLED_BACK",
            "fixture": True,
        }),
        "operator": "v2-postgres-fixture",
    }

    with engine.connect() as connection:
        baseline_counts = database_guardrail_counts(
            connection
        )
        baseline_sources = source_snapshots(
            connection,
            feature_ids,
        )

    if len(baseline_sources) != 2:
        raise AssertionError(
            "FIXTURE_SOURCE_IDENTITY_COUNT_MISMATCH"
        )

    transaction_rolled_back = False

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            apply_result = execute_apply_transaction(
                connection,
                rows=rows,
                authorized_row_count=2,
                parameters=common,
            )

            applied_sources = source_snapshots(
                connection,
                feature_ids,
            )
            if not all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in applied_sources
            ):
                raise AssertionError(
                    "V2_FIXTURE_APPLY_STATUS_MISMATCH"
                )

            replay_result = execute_apply_transaction(
                connection,
                rows=rows,
                authorized_row_count=2,
                parameters=common,
            )
            if replay_result["status"] != "IDEMPOTENT_NO_OP":
                raise AssertionError(
                    "V2_FIXTURE_REPLAY_NOT_IDEMPOTENT"
                )

            active_events = int(
                connection.execute(text(f"""
                    select count(*)
                    from {EVENT_TABLE}
                    where plan_checksum = :plan_checksum
                      and rollback_token = :rollback_token
                      and apply_status = 'APPLIED'
                      and is_active = true
                """), rollback_parameters).scalar_one()
            )
            if active_events != 2:
                raise AssertionError(
                    "V2_FIXTURE_ACTIVE_EVENT_COUNT_MISMATCH"
                )

            rollback_result = (
                execute_rollback_transaction(
                    connection,
                    authorized_row_count=2,
                    parameters=rollback_parameters,
                )
            )

            restored_sources = source_snapshots(
                connection,
                feature_ids,
            )
            if (
                canonical(restored_sources)
                != canonical(baseline_sources)
            ):
                raise AssertionError(
                    "V2_FIXTURE_SOURCE_RESTORATION_MISMATCH"
                )

            rolled_back_events = int(
                connection.execute(text(f"""
                    select count(*)
                    from {EVENT_TABLE}
                    where plan_checksum = :plan_checksum
                      and rollback_token = :rollback_token
                      and apply_status = 'ROLLED_BACK'
                      and is_active = false
                """), rollback_parameters).scalar_one()
            )
            if rolled_back_events != 2:
                raise AssertionError(
                    "V2_FIXTURE_ROLLBACK_EVENT_COUNT_MISMATCH"
                )

            in_transaction_counts = (
                database_guardrail_counts(connection)
            )

            for key in (
                "runtime_eligible_source_rows",
                "candidate_rows",
                "active_candidate_rows",
                "promoted_candidate_rows",
                "runtime_set_rows",
                "runtime_feature_rows",
                "runtime_crosswalk_rows",
            ):
                if (
                    in_transaction_counts[key]
                    != baseline_counts[key]
                ):
                    raise AssertionError(
                        f"V2_GUARDRAIL_COUNT_CHANGED:{key}"
                    )

            transaction.rollback()
            transaction_rolled_back = True
        except BaseException:
            transaction.rollback()
            transaction_rolled_back = True
            raise

    forced_failure_observed = False

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            def fail_after_source_update(
                phase: str,
            ) -> None:
                if phase == "SOURCE_UPDATE":
                    raise RuntimeError(
                        "EXPECTED_V2_FORCED_FAILURE"
                    )

            execute_apply_transaction(
                connection,
                rows=rows,
                authorized_row_count=2,
                parameters=common,
                after_phase=fail_after_source_update,
            )
            raise AssertionError(
                "V2_FORCED_FAILURE_NOT_TRIGGERED"
            )
        except RuntimeError as exc:
            if str(exc) != "EXPECTED_V2_FORCED_FAILURE":
                transaction.rollback()
                raise
            forced_failure_observed = True
            transaction.rollback()
        except BaseException:
            transaction.rollback()
            raise

    with engine.connect() as connection:
        final_counts = database_guardrail_counts(
            connection
        )
        final_sources = source_snapshots(
            connection,
            feature_ids,
        )
        persisted_fixture_events = int(
            connection.execute(text(f"""
                select count(*)
                from {EVENT_TABLE}
                where plan_checksum = :plan_checksum
                  and rollback_token = :rollback_token
            """), rollback_parameters).scalar_one()
        )

    if not transaction_rolled_back:
        raise AssertionError(
            "OUTER_FIXTURE_TRANSACTION_NOT_ROLLED_BACK"
        )
    if not forced_failure_observed:
        raise AssertionError(
            "V2_FORCED_FAILURE_NOT_OBSERVED"
        )
    if final_counts != baseline_counts:
        raise AssertionError(
            "DATABASE_COUNTS_CHANGED_AFTER_FIXTURE"
        )
    if canonical(final_sources) != canonical(
        baseline_sources
    ):
        raise AssertionError(
            "SOURCE_ROWS_CHANGED_AFTER_FIXTURE"
        )
    if persisted_fixture_events != 0:
        raise AssertionError(
            "FIXTURE_EVENTS_PERSISTED"
        )

    print(json.dumps({
        "apply_result": apply_result,
        "rollback_result": rollback_result,
        "feature_ids": feature_ids,
        "database_counts_unchanged":
            final_counts == baseline_counts,
        "source_rows_unchanged":
            canonical(final_sources)
            == canonical(baseline_sources),
        "persisted_fixture_event_count":
            persisted_fixture_events,
        "outer_transaction_rolled_back":
            transaction_rolled_back,
        "idempotent_replay_status":
            replay_result["status"],
        "forced_failure_observed":
            forced_failure_observed,
        "healthy": True,
    }, indent=2, sort_keys=True))

    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "POSTGRES FIXTURE PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
