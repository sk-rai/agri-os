#!/usr/bin/env python3
"""Regression for the three-row transactional validation-metadata fixture."""

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
from scripts.apply_boundary_geometry_validation_metadata_multi_row_fixture import (  # noqa: E402
    FIXTURE_IDS,
    PLAN_CHECKSUM,
    SCHEMA_VERSION,
    SOURCE_SHA256,
    counts,
    load_source,
)

APPLY_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_multi_row_fixture.py"
)
PLANNER_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)

OUTPUT_ROOT = Path(
    "/tmp/boundary-validation-metadata-multi-row-fixture-regression"
)
PLAN_DIR = OUTPUT_ROOT / "plan"
PLAN_JSON = (
    PLAN_DIR
    / "andaman_and_nicobar_islands_"
    "bounded_validation_metadata_plan.json"
)
SOURCE_PATH = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)

ROLLBACK_TOKEN = "validation-metadata-multi-row-fixture-regression"
WRONG_TOKEN = "wrong-validation-metadata-token"

SAFE_COUNT_KEYS = [
    "source_feature_rows",
    "runtime_eligible_source_rows",
    "candidate_rows",
    "active_candidate_rows",
    "promoted_candidate_rows",
    "runtime_set_rows",
    "runtime_feature_rows",
    "runtime_crosswalk_rows",
]

SAFE_GUARDRAILS = [
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


def fixture_rows() -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            load_source(connection, feature_id)
            for feature_id in FIXTURE_IDS
        ]


def database_counts() -> dict[str, int]:
    with engine.connect() as connection:
        return counts(connection)


def cleanup_regression_events() -> None:
    """Delete only the three exact test events."""

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                delete from
                  geography_boundary_validation_metadata_events
                where rollback_token = :rollback_token
                  and plan_checksum = :plan_checksum
                  and source_feature_id =
                    any(cast(:source_feature_ids as uuid[]))
                """
            ),
            {
                "rollback_token": ROLLBACK_TOKEN,
                "plan_checksum": PLAN_CHECKSUM,
                "source_feature_ids": FIXTURE_IDS,
            },
        )


def assert_source_baseline(
    label: str,
) -> list[dict[str, Any]]:
    rows = fixture_rows()

    check(
        len(rows) == 3,
        f"{label}: exactly three fixture rows exist",
        rows,
    )
    check(
        all(
            row["geometry_validation_status"]
            == "NOT_VALIDATED"
            for row in rows
        ),
        f"{label}: fixture rows are NOT_VALIDATED",
        rows,
    )
    check(
        all(
            row["source_geometry_hash"] is None
            for row in rows
        ),
        f"{label}: fixture rows have no geometry hash",
        rows,
    )
    check(
        all(
            row["eligible_for_runtime_after_promotion"] is False
            for row in rows
        ),
        f"{label}: fixture rows remain runtime-ineligible",
        rows,
    )

    return rows


def generate_plan() -> dict[str, Any]:
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
            "--limit",
            "3",
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
        "Three-row planner exits zero",
        {
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        },
    )
    check(
        PLAN_JSON.is_file(),
        "Three-row planner writes JSON",
    )

    plan = json.loads(
        PLAN_JSON.read_text(encoding="utf-8")
    )

    check(
        plan["batch"]["selected_row_count"] == 3,
        "Plan selects exactly three rows",
        plan["batch"],
    )
    check(
        plan["batch"]["plan_checksum"] == PLAN_CHECKSUM,
        "Plan checksum is pinned",
        plan["batch"],
    )
    check(
        [
            row["source_feature_id"]
            for row in plan["rows"]
        ]
        == FIXTURE_IDS,
        "Plan selects exact fixture IDs",
        plan["rows"],
    )
    check(
        all(
            row["classification"]
            == "VALIDATED_NO_REPAIR"
            for row in plan["rows"]
        ),
        "Plan contains only valid-without-repair rows",
        plan["rows"],
    )
    check(
        all(
            row["runtime_eligibility_change_planned"]
            is False
            for row in plan["rows"]
        ),
        "Plan contains no runtime eligibility change",
        plan["rows"],
    )

    return plan


def invoke(
    name: str,
    operation: str,
    expected_returncode: int,
    expected_action: str,
    expected_error: str | None,
    *,
    rollback_token: str = ROLLBACK_TOKEN,
    omit_admin_confirmation: bool = False,
    force_failure_after: int = 0,
) -> dict[str, Any]:
    output_dir = OUTPUT_ROOT / name

    command = [
        sys.executable,
        str(APPLY_SCRIPT),
        "--plan-json",
        str(PLAN_JSON),
        "--plan-checksum",
        PLAN_CHECKSUM,
        "--source-sha256",
        SOURCE_SHA256,
        "--rollback-token",
        rollback_token,
        "--output-dir",
        str(output_dir),
        f"--{operation}",
        "--enable-validation-metadata-write",
        "--dry-run-reviewed",
        "--event-schema-reviewed",
    ]

    if not omit_admin_confirmation:
        command.append("--admin-confirmation")

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
        / "validation_metadata_multi_row_fixture_audit.json"
    )
    csv_path = (
        output_dir
        / "validation_metadata_multi_row_fixture_rows.csv"
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
        data,
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

    for guardrail in SAFE_GUARDRAILS:
        check(
            data["guardrails"][guardrail] is False,
            (
                f"{name}: guardrail remains false: "
                f"{guardrail}"
            ),
            data["guardrails"],
        )

    return data


def main() -> int:
    print("=" * 72)
    print(
        "BOUNDARY VALIDATION METADATA "
        "MULTI-ROW FIXTURE REGRESSION"
    )
    print("=" * 72)

    source_checksum_before = sha256_file(SOURCE_PATH)
    source_mtime_before = SOURCE_PATH.stat().st_mtime_ns
    baseline_rows = assert_source_baseline(
        "Initial baseline"
    )

    cleanup_regression_events()
    baseline_counts = database_counts()

    try:
        generate_plan()

        rejected = invoke(
            "missing-admin-confirmation",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "ADMIN_CONFIRMATION_REQUIRED",
            omit_admin_confirmation=True,
        )
        check(
            rejected["guardrails"]["db_writes_attempted"]
            is False,
            "Rejected invocation attempts no DB writes",
        )
        check(
            database_counts() == baseline_counts,
            "Rejected invocation leaves counts unchanged",
        )

        failed = invoke(
            "forced-mid-batch-failure",
            "apply",
            1,
            "ROLLED_BACK_TRANSACTION",
            "FORCED_MID_BATCH_FAILURE",
            force_failure_after=2,
        )
        check(
            failed["guardrails"]["db_writes_attempted"]
            is True,
            "Forced failure records attempted DB writes",
        )
        check(
            failed["guardrails"][
                "transaction_changes_persisted"
            ]
            is False,
            "Forced failure persists no transaction changes",
        )
        check(
            database_counts() == baseline_counts,
            "Forced failure restores database counts",
        )
        check(
            fixture_rows() == baseline_rows,
            "Forced failure restores exact source rows",
        )

        applied = invoke(
            "apply",
            "apply",
            0,
            "APPLIED",
            None,
        )
        check(
            applied["changed_source_row_count"] == 3,
            "Apply changes exactly three source rows",
            applied,
        )
        check(
            applied["changed_event_row_count"] == 3,
            "Apply creates exactly three events",
            applied,
        )
        check(
            all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in applied["final_rows"]
            ),
            "Apply validates all three rows",
            applied["final_rows"],
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
            applied["final_rows"],
        )
        check(
            applied["final_counts"]["not_validated_rows"]
            == baseline_counts["not_validated_rows"] - 3,
            "Apply decreases NOT_VALIDATED by three",
        )
        check(
            applied["final_counts"]["validated_rows"]
            == baseline_counts["validated_rows"] + 3,
            "Apply increases VALIDATED by three",
        )
        check(
            applied["final_counts"][
                "active_validation_event_rows"
            ]
            == baseline_counts[
                "active_validation_event_rows"
            ]
            + 3,
            "Apply activates three validation events",
        )

        for key in SAFE_COUNT_KEYS:
            check(
                applied["final_counts"][key]
                == baseline_counts[key],
                f"Apply leaves count unchanged: {key}",
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
            "Repeated apply leaves counts unchanged",
        )

        wrong_token = invoke(
            "wrong-token-rollback",
            "rollback",
            1,
            "ROLLED_BACK_TRANSACTION",
            "ACTIVE_APPLY_EVENT_SET_REQUIRED",
            rollback_token=WRONG_TOKEN,
        )
        check(
            wrong_token["guardrails"][
                "db_writes_attempted"
            ]
            is False,
            "Wrong rollback token attempts no DB writes",
        )
        check(
            all(
                row["geometry_validation_status"]
                == "VALIDATED"
                for row in wrong_token["final_rows"]
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
            rolled_back["changed_source_row_count"] == 3,
            "Rollback restores three source rows",
        )
        check(
            rolled_back["changed_event_row_count"] == 3,
            "Rollback closes three events",
        )
        check(
            rolled_back["final_rows"] == baseline_rows,
            "Rollback restores exact source baseline",
            {
                "expected": baseline_rows,
                "actual": rolled_back["final_rows"],
            },
        )
        check(
            rolled_back["final_counts"][
                "active_validation_event_rows"
            ]
            == baseline_counts[
                "active_validation_event_rows"
            ],
            "Rollback leaves no fixture event active",
        )
        check(
            rolled_back["final_counts"][
                "validation_event_rows"
            ]
            == baseline_counts["validation_event_rows"]
            + 3,
            "Rollback retains three immutable events",
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

        with engine.connect() as connection:
            event_rows = list(
                connection.execute(
                    text(
                        """
                        select apply_status, is_active
                        from
                          geography_boundary_validation_metadata_events
                        where rollback_token = :rollback_token
                          and plan_checksum = :plan_checksum
                          and source_feature_id =
                            any(
                              cast(
                                :source_feature_ids
                                as uuid[]
                              )
                            )
                        order by source_feature_index
                        """
                    ),
                    {
                        "rollback_token": ROLLBACK_TOKEN,
                        "plan_checksum": PLAN_CHECKSUM,
                        "source_feature_ids": FIXTURE_IDS,
                    },
                ).mappings()
            )

        check(
            len(event_rows) == 3,
            "Three immutable fixture events remain",
            event_rows,
        )
        check(
            all(
                row["apply_status"] == "ROLLED_BACK"
                and row["is_active"] is False
                for row in event_rows
            ),
            "All fixture events are rolled back and inactive",
            event_rows,
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

    finally:
        cleanup_regression_events()

    check(
        fixture_rows() == baseline_rows,
        "Regression cleanup preserves exact source baseline",
    )
    check(
        database_counts() == baseline_counts,
        "Regression cleanup restores database counts",
    )

    print("=" * 72)
    print(
        "BOUNDARY VALIDATION METADATA "
        "MULTI-ROW FIXTURE REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
