#!/usr/bin/env python3
"""Regression for the approved bounded-state validation metadata apply."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402

APPLY_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_bounded_state.py"
)
PLANNER_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)

OUTPUT_ROOT = Path(
    "/tmp/boundary-validation-metadata-bounded-state-apply-regression"
)
PLAN_DIR = OUTPUT_ROOT / "plan"
PLAN_PATH = (
    PLAN_DIR
    / "andaman_and_nicobar_islands_"
    "bounded_validation_metadata_plan.json"
)

SOURCE_PATH = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)

SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
PLAN_CHECKSUM = (
    "822ed7575c67de714e1599de243d7ecbd77828471de308c1a087ff38de12ef4d"
)
ROLLBACK_TOKEN = (
    "andaman-boundary-validation-metadata-batch-1-20260909"
)
OPERATOR = "admin-regression"
APPROVER = "admin-regression"
APPROVAL_REFERENCE = "user-authorization-2026-09-09"

SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_bounded_state_apply.v1"
)
EVENT_TABLE = (
    "geography_boundary_validation_metadata_events"
)
SOURCE_TABLE = "geography_boundary_source_features"

FALSE_GUARDRAILS = [
    "source_files_changed",
    "geometry_repair_persisted",
    "source_runtime_eligibility_changed",
    "boundary_candidates_promoted",
    "boundary_candidates_activated",
    "runtime_tables_written",
    "runtime_lookup_enabled",
    "lgd_geography_overwritten",
    "android_behavior_changed",
]

UNCHANGED_COUNT_KEYS = [
    "source_feature_rows",
    "runtime_eligible_source_rows",
    "candidate_rows",
    "active_candidate_rows",
    "promoted_candidate_rows",
    "runtime_set_rows",
    "runtime_feature_rows",
    "runtime_crosswalk_rows",
]


def check(
    condition: bool,
    label: str,
    value: Any = None,
) -> None:
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(
                json.dumps(
                    value,
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
            )
        raise AssertionError(label)

    print(f"PASS {label}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def counts() -> dict[str, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                f"""
                select
                  (
                    select count(*)
                    from {SOURCE_TABLE}
                  ) as source_feature_rows,
                  (
                    select count(*)
                    from {SOURCE_TABLE}
                    where geometry_validation_status =
                      'NOT_VALIDATED'
                  ) as not_validated_rows,
                  (
                    select count(*)
                    from {SOURCE_TABLE}
                    where geometry_validation_status =
                      'VALIDATED'
                  ) as validated_rows,
                  (
                    select count(*)
                    from {SOURCE_TABLE}
                    where
                      eligible_for_runtime_after_promotion
                      = true
                  ) as runtime_eligible_source_rows,
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
                  ) as runtime_crosswalk_rows,
                  (
                    select count(*)
                    from {EVENT_TABLE}
                  ) as validation_event_rows,
                  (
                    select count(*)
                    from {EVENT_TABLE}
                    where is_active = true
                  ) as active_validation_event_rows
                """
            )
        ).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def rows(
    feature_ids: list[str],
) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                f"""
                select
                  id::text as source_feature_id,
                  import_batch_id::text as import_batch_id,
                  source_feature_index,
                  source_vlcode,
                  source_geometry_hash,
                  source_bbox,
                  transformed_bbox,
                  transformed_centroid,
                  geometry_validation_status,
                  eligible_for_runtime_after_promotion,
                  metadata
                from {SOURCE_TABLE}
                where id = any(
                  cast(:feature_ids as uuid[])
                )
                order by source_feature_index, id
                """
            ),
            {"feature_ids": feature_ids},
        ).mappings()

        return [dict(row) for row in result]


def event_summary(
    feature_ids: list[str],
) -> dict[str, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                f"""
                select
                  count(*) as event_count,
                  count(*) filter (
                    where apply_status = 'APPLIED'
                  ) as applied_count,
                  count(*) filter (
                    where apply_status = 'ROLLED_BACK'
                  ) as rolled_back_count,
                  count(*) filter (
                    where is_active = true
                  ) as active_count
                from {EVENT_TABLE}
                where rollback_token = :rollback_token
                  and plan_checksum = :plan_checksum
                  and source_feature_id = any(
                    cast(:feature_ids as uuid[])
                  )
                """
            ),
            {
                "rollback_token": ROLLBACK_TOKEN,
                "plan_checksum": PLAN_CHECKSUM,
                "feature_ids": feature_ids,
            },
        ).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def cleanup_events(
    feature_ids: list[str],
) -> None:
    summary = event_summary(feature_ids)

    if summary["active_count"]:
        raise RuntimeError(
            "Refusing to delete active regression events"
        )

    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                delete from {EVENT_TABLE}
                where rollback_token = :rollback_token
                  and plan_checksum = :plan_checksum
                  and source_feature_id = any(
                    cast(:feature_ids as uuid[])
                  )
                """
            ),
            {
                "rollback_token": ROLLBACK_TOKEN,
                "plan_checksum": PLAN_CHECKSUM,
                "feature_ids": feature_ids,
            },
        )


def generate_plan() -> tuple[dict[str, Any], list[str]]:
    completed = subprocess.run(
        [
            sys.executable,
            str(PLANNER_SCRIPT),
            "--state-slug",
            "andaman_and_nicobar_islands",
            "--state-or-ut",
            "Andaman and Nicobar Islands",
            "--expected-source-sha256",
            SOURCE_SHA256,
            "--cursor-after-index",
            "-1",
            "--limit",
            "500",
            "--output-dir",
            str(PLAN_DIR),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    check(
        completed.returncode == 0,
        "Approved plan exits zero",
        {
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        },
    )
    check(
        PLAN_PATH.is_file(),
        "Approved plan JSON is written",
    )

    plan = json.loads(
        PLAN_PATH.read_text(encoding="utf-8")
    )
    feature_ids = [
        row["source_feature_id"]
        for row in plan["rows"]
    ]

    check(
        plan["batch"]["selected_row_count"] == 500,
        "Approved plan selects 500 rows",
    )
    check(
        plan["batch"]["plan_checksum"]
        == PLAN_CHECKSUM,
        "Approved plan checksum matches",
    )
    check(
        len(set(feature_ids)) == 500,
        "Approved feature IDs are unique",
    )
    check(
        all(
            row["classification"]
            == "VALIDATED_NO_REPAIR"
            for row in plan["rows"]
        ),
        "Approved plan excludes repair-required rows",
    )
    check(
        all(
            row["runtime_eligibility_change_planned"]
            is False
            for row in plan["rows"]
        ),
        "Approved plan contains no runtime eligibility change",
    )

    return plan, feature_ids


def common_arguments(
    output_dir: Path,
) -> list[str]:
    return [
        "--plan-json",
        str(PLAN_PATH),
        "--plan-checksum",
        PLAN_CHECKSUM,
        "--source-sha256",
        SOURCE_SHA256,
        "--rollback-token",
        ROLLBACK_TOKEN,
        "--operator",
        OPERATOR,
        "--approver",
        APPROVER,
        "--approval-reference",
        APPROVAL_REFERENCE,
        "--output-dir",
        str(output_dir),
        "--enable-validation-metadata-write",
        "--dry-run-reviewed",
        "--event-schema-reviewed",
        "--admin-confirmation",
    ]


def invoke(
    name: str,
    operation: str,
    expected_returncode: int,
    expected_action: str,
    expected_error: str | None,
    *,
    override: dict[str, str] | None = None,
    force_failure_after: int = 0,
) -> dict[str, Any]:
    output_dir = OUTPUT_ROOT / name
    arguments = common_arguments(output_dir)

    replacements = override or {}

    option_indexes = {
        arguments[index]: index + 1
        for index in range(0, len(arguments) - 1)
        if arguments[index].startswith("--")
        and not arguments[index + 1].startswith("--")
    }

    for option, value in replacements.items():
        arguments[option_indexes[option]] = value

    command = [
        sys.executable,
        str(APPLY_SCRIPT),
        *arguments,
        f"--{operation}",
    ]

    if force_failure_after:
        command.extend(
            [
                "--force-failure-after",
                str(force_failure_after),
            ]
        )

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    json_path = (
        output_dir
        / "boundary_validation_metadata_"
        "bounded_state_apply_audit.json"
    )
    csv_path = (
        output_dir
        / "boundary_validation_metadata_"
        "bounded_state_apply_rows.csv"
    )

    check(
        completed.returncode == expected_returncode,
        f"{name}: expected exit code",
        {
            "expected": expected_returncode,
            "actual": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        },
    )
    check(
        json_path.is_file(),
        f"{name}: JSON audit is written",
    )
    check(
        csv_path.is_file(),
        f"{name}: CSV audit is written",
    )

    data = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    check(
        data["schema_version"] == SCHEMA_VERSION,
        f"{name}: schema version is stable",
    )
    check(
        data["action"] == expected_action,
        f"{name}: expected action",
        data,
    )
    check(
        data["error"] == expected_error,
        f"{name}: expected error",
        data,
    )

    for guardrail in FALSE_GUARDRAILS:
        check(
            data["guardrails"][guardrail] is False,
            (
                f"{name}: guardrail remains false: "
                f"{guardrail}"
            ),
        )

    return data


def recover_if_active(
    feature_ids: list[str],
) -> None:
    if event_summary(feature_ids)["active_count"] == 0:
        return

    completed = subprocess.run(
        [
            sys.executable,
            str(APPLY_SCRIPT),
            *common_arguments(
                OUTPUT_ROOT / "emergency-cleanup-rollback"
            ),
            "--rollback",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "Emergency regression rollback failed:\n"
            + completed.stderr[-2000:]
        )


def main() -> int:
    print("=" * 72)
    print(
        "BOUNDED STATE VALIDATION METADATA "
        "ENABLED APPLY REGRESSION"
    )
    print("=" * 72)

    source_checksum_before = sha256_file(
        SOURCE_PATH
    )
    source_mtime_before = (
        SOURCE_PATH.stat().st_mtime_ns
    )

    plan, feature_ids = generate_plan()
    baseline_rows = rows(feature_ids)

    check(
        len(baseline_rows) == 500,
        "All 500 database rows exist",
    )
    check(
        all(
            row["geometry_validation_status"]
            == "NOT_VALIDATED"
            for row in baseline_rows
        ),
        "All 500 rows begin NOT_VALIDATED",
    )
    check(
        all(
            row[
                "eligible_for_runtime_after_promotion"
            ]
            is False
            for row in baseline_rows
        ),
        "All 500 rows begin runtime-ineligible",
    )

    recover_if_active(feature_ids)
    cleanup_events(feature_ids)
    baseline_counts = counts()

    try:
        wrong_operator = invoke(
            "wrong-operator",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "APPROVED_OPERATOR_MISMATCH",
            override={
                "--operator": "wrong-operator",
            },
        )
        check(
            wrong_operator["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong operator attempts no DB writes",
        )

        wrong_approver = invoke(
            "wrong-approver",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "APPROVED_APPROVER_MISMATCH",
            override={
                "--approver": "wrong-approver",
            },
        )
        check(
            wrong_approver["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong approver attempts no DB writes",
        )

        wrong_reference = invoke(
            "wrong-reference",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "APPROVAL_REFERENCE_MISMATCH",
            override={
                "--approval-reference": "wrong-reference",
            },
        )
        check(
            wrong_reference["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong approval reference attempts no writes",
        )

        wrong_token = invoke(
            "wrong-token-apply",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "APPROVED_ROLLBACK_TOKEN_MISMATCH",
            override={
                "--rollback-token": "wrong-token",
            },
        )
        check(
            wrong_token["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong apply token attempts no writes",
        )

        wrong_checksum = invoke(
            "wrong-checksum",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "PLAN_CHECKSUM_MISMATCH",
            override={
                "--plan-checksum": "0" * 64,
            },
        )
        check(
            wrong_checksum["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong checksum attempts no writes",
        )

        check(
            counts() == baseline_counts,
            "Rejected invocations leave counts unchanged",
        )

        forced = invoke(
            "forced-failure",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "FORCED_MID_BATCH_FAILURE",
            force_failure_after=2,
        )
        check(
            forced["guardrails"][
                "db_writes_attempted"
            ]
            is True,
            "Forced failure records attempted writes",
        )
        check(
            forced["guardrails"][
                "transaction_changes_persisted"
            ]
            is False,
            "Forced failure persists no changes",
        )
        check(
            counts() == baseline_counts,
            "Forced failure restores counts",
        )
        check(
            rows(feature_ids) == baseline_rows,
            "Forced failure restores exact rows",
        )

        applied = invoke(
            "apply",
            "apply",
            0,
            "APPLIED",
            None,
        )
        check(
            applied["changed_source_row_count"]
            == 500,
            "Apply changes exactly 500 source rows",
        )
        check(
            applied["changed_event_row_count"]
            == 500,
            "Apply creates exactly 500 events",
        )
        check(
            all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in applied["final_rows"]
            ),
            "Apply validates all 500 rows",
        )
        check(
            all(
                row[
                    "eligible_for_runtime_after_promotion"
                ]
                is False
                for row in applied["final_rows"]
            ),
            "Apply leaves runtime eligibility false",
        )
        check(
            applied["final_counts"][
                "not_validated_rows"
            ]
            == baseline_counts["not_validated_rows"]
            - 500,
            "Apply decreases NOT_VALIDATED by 500",
        )
        check(
            applied["final_counts"]["validated_rows"]
            == baseline_counts["validated_rows"]
            + 500,
            "Apply increases VALIDATED by 500",
        )
        check(
            applied["final_counts"][
                "validation_event_rows"
            ]
            == baseline_counts["validation_event_rows"]
            + 500,
            "Apply creates 500 validation events",
        )
        check(
            applied["final_counts"][
                "active_validation_event_rows"
            ]
            == baseline_counts[
                "active_validation_event_rows"
            ]
            + 500,
            "Apply activates 500 validation events",
        )

        for key in UNCHANGED_COUNT_KEYS:
            check(
                applied["final_counts"][key]
                == baseline_counts[key],
                f"Apply leaves count unchanged: {key}",
            )

        event_state = event_summary(feature_ids)
        check(
            event_state["event_count"] == 500,
            "Exactly 500 batch events exist",
        )
        check(
            event_state["applied_count"] == 500,
            "All 500 batch events are APPLIED",
        )
        check(
            event_state["active_count"] == 500,
            "All 500 batch events are active",
        )

        repeated_apply = invoke(
            "idempotent-apply",
            "apply",
            0,
            "IDEMPOTENT_NO_OP",
            None,
        )
        check(
            repeated_apply[
                "changed_source_row_count"
            ]
            == 0,
            "Repeated apply changes no source rows",
        )
        check(
            repeated_apply[
                "changed_event_row_count"
            ]
            == 0,
            "Repeated apply changes no events",
        )
        check(
            repeated_apply["before_counts"]
            == repeated_apply["final_counts"],
            "Repeated apply preserves counts",
        )

        rejected_rollback = invoke(
            "wrong-token-rollback",
            "rollback",
            1,
            "ROLLED_BACK_TRANSACTION",
            "APPROVED_ROLLBACK_TOKEN_MISMATCH",
            override={
                "--rollback-token": "wrong-token",
            },
        )
        check(
            rejected_rollback["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong rollback token attempts no writes",
        )
        check(
            all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in rejected_rollback[
                    "final_rows"
                ]
            ),
            "Wrong rollback token leaves rows validated",
        )

        rolled_back = invoke(
            "rollback",
            "rollback",
            0,
            "ROLLED_BACK",
            None,
        )
        check(
            rolled_back["changed_source_row_count"]
            == 500,
            "Rollback restores 500 source rows",
        )
        check(
            rolled_back["changed_event_row_count"]
            == 500,
            "Rollback closes 500 events",
        )
        check(
            rolled_back["final_rows"]
            == baseline_rows,
            "Rollback restores exact source baseline",
        )
        check(
            rolled_back["final_counts"][
                "not_validated_rows"
            ]
            == baseline_counts["not_validated_rows"],
            "Rollback restores NOT_VALIDATED count",
        )
        check(
            rolled_back["final_counts"][
                "validated_rows"
            ]
            == baseline_counts["validated_rows"],
            "Rollback restores VALIDATED count",
        )
        check(
            rolled_back["final_counts"][
                "active_validation_event_rows"
            ]
            == baseline_counts[
                "active_validation_event_rows"
            ],
            "Rollback leaves no batch event active",
        )

        rolled_event_state = event_summary(
            feature_ids
        )
        check(
            rolled_event_state["event_count"] == 500,
            "Rollback retains 500 immutable events",
        )
        check(
            rolled_event_state["rolled_back_count"]
            == 500,
            "All 500 events are ROLLED_BACK",
        )
        check(
            rolled_event_state["active_count"] == 0,
            "All rolled-back events are inactive",
        )

        repeated_rollback = invoke(
            "idempotent-rollback",
            "rollback",
            0,
            "IDEMPOTENT_ROLLBACK_NO_OP",
            None,
        )
        check(
            repeated_rollback[
                "changed_source_row_count"
            ]
            == 0,
            "Repeated rollback changes no source rows",
        )
        check(
            repeated_rollback[
                "changed_event_row_count"
            ]
            == 0,
            "Repeated rollback changes no events",
        )

    finally:
        recover_if_active(feature_ids)
        cleanup_events(feature_ids)

    check(
        rows(feature_ids) == baseline_rows,
        "Regression restores exact 500-row baseline",
    )
    check(
        counts() == baseline_counts,
        "Regression restores database counts",
    )
    check(
        sha256_file(SOURCE_PATH)
        == source_checksum_before,
        "Source checksum is unchanged",
    )
    check(
        SOURCE_PATH.stat().st_mtime_ns
        == source_mtime_before,
        "Source modification time is unchanged",
    )

    print("=" * 72)
    print(
        "BOUNDED STATE VALIDATION METADATA "
        "ENABLED APPLY REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
