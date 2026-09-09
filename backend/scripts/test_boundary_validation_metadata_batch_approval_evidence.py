#!/usr/bin/env python3
"""Regression for bounded validation-metadata approval evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402
from scripts.report_boundary_validation_metadata_batch_approval_evidence import (  # noqa: E402
    SCHEMA_VERSION,
    recompute_plan_checksum,
)

REPORT_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "report_boundary_validation_metadata_batch_approval_evidence.py"
)
PLANNER_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)

OUTPUT_ROOT = Path(
    "/tmp/boundary-validation-metadata-approval-evidence-regression"
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
EVENT_TOKEN = "approval-evidence-regression-conflict"


FALSE_GUARDRAILS = [
    "db_writes_attempted",
    "source_files_changed",
    "source_features_changed",
    "validation_metadata_written",
    "validation_events_written",
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


def database_counts() -> dict[str, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                select
                  (
                    select count(*)
                    from geography_boundary_source_features
                  ) as source_feature_rows,
                  (
                    select count(*)
                    from geography_boundary_source_features
                    where geometry_validation_status =
                      'NOT_VALIDATED'
                  ) as not_validated_rows,
                  (
                    select count(*)
                    from geography_boundary_source_features
                    where geometry_validation_status =
                      'VALIDATED'
                  ) as validated_rows,
                  (
                    select count(*)
                    from geography_boundary_source_features
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
                    from
                      geography_boundary_validation_metadata_events
                  ) as validation_event_rows,
                  (
                    select count(*)
                    from
                      geography_boundary_validation_metadata_events
                    where is_active = true
                  ) as active_validation_event_rows
                """
            )
        ).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def build_plan() -> dict[str, Any]:
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
        "Pinned bounded plan exits zero",
        {
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        },
    )
    check(
        PLAN_PATH.is_file(),
        "Pinned bounded plan is written",
    )

    plan = json.loads(
        PLAN_PATH.read_text(encoding="utf-8")
    )

    check(
        plan["batch"]["selected_row_count"] == 500,
        "Pinned plan selects 500 rows",
        plan["batch"],
    )
    check(
        plan["batch"]["plan_checksum"]
        == PLAN_CHECKSUM,
        "Pinned plan checksum matches",
        plan["batch"],
    )

    return plan


def write_variant(
    name: str,
    plan: dict[str, Any],
) -> tuple[Path, str]:
    variant = copy.deepcopy(plan)
    checksum = recompute_plan_checksum(variant)
    variant["batch"]["plan_checksum"] = checksum

    path = OUTPUT_ROOT / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            variant,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return path, checksum


def run_report(
    name: str,
    plan_path: Path,
    plan_checksum: str,
    source_checksum: str,
    expected_returncode: int,
) -> dict[str, Any]:
    output_dir = OUTPUT_ROOT / name

    completed = subprocess.run(
        [
            sys.executable,
            str(REPORT_SCRIPT),
            "--plan-json",
            str(plan_path),
            "--expected-plan-checksum",
            plan_checksum,
            "--expected-source-sha256",
            source_checksum,
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    json_path = (
        output_dir
        / "boundary_validation_metadata_"
        "batch_approval_evidence.json"
    )
    csv_path = (
        output_dir
        / "boundary_validation_metadata_"
        "batch_approval_evidence_rows.csv"
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
        f"{name}: JSON evidence is written",
    )
    check(
        csv_path.is_file(),
        f"{name}: CSV evidence is written",
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
        data["database_counts"]["unchanged"] is True,
        f"{name}: report leaves counts unchanged",
        data["database_counts"],
    )
    check(
        data["readiness"]["approved_for_apply"]
        is False,
        f"{name}: report never grants approval",
    )
    check(
        data["readiness"]["ready_for_enabled_apply"]
        is False,
        f"{name}: enabled apply remains disabled",
    )

    for guardrail in FALSE_GUARDRAILS:
        check(
            data["guardrails"][guardrail] is False,
            (
                f"{name}: guardrail remains false: "
                f"{guardrail}"
            ),
            data["guardrails"],
        )

    return data


def cleanup_conflict_event() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                delete from
                  geography_boundary_validation_metadata_events
                where rollback_token = :rollback_token
                """
            ),
            {"rollback_token": EVENT_TOKEN},
        )


def create_conflict_event(
    plan: dict[str, Any],
) -> None:
    first = plan["rows"][0]
    feature_id = first["source_feature_id"]

    with engine.begin() as connection:
        source = connection.execute(
            text(
                """
                select
                  import_batch_id::text as import_batch_id,
                  source_feature_index
                from geography_boundary_source_features
                where id = cast(:feature_id as uuid)
                """
            ),
            {"feature_id": feature_id},
        ).mappings().one()

        connection.execute(
            text(
                """
                insert into
                  geography_boundary_validation_metadata_events
                (
                  id,
                  source_feature_id,
                  import_batch_id,
                  source_system,
                  state_or_ut,
                  source_feature_index,
                  source_sha256,
                  plan_checksum,
                  geometry_hash_algorithm,
                  rollback_token,
                  apply_status,
                  before_values,
                  planned_values,
                  after_values,
                  apply_report,
                  rollback_report,
                  metadata,
                  applied_by,
                  applied_at,
                  is_active,
                  version
                )
                values
                (
                  cast(:id as uuid),
                  cast(:source_feature_id as uuid),
                  cast(:import_batch_id as uuid),
                  'NWDP_GSI_VILLAGE_BOUNDARY',
                  'Andaman and Nicobar Islands',
                  :source_feature_index,
                  :source_sha256,
                  :plan_checksum,
                  'NWDP_GEOJSON_GEOMETRY_CANONICAL_V1',
                  :rollback_token,
                  'PLANNED',
                  '{}'::jsonb,
                  '{}'::jsonb,
                  '{}'::jsonb,
                  '{}'::jsonb,
                  '{}'::jsonb,
                  '{"regression_fixture": true}'::jsonb,
                  'approval-evidence-regression',
                  now(),
                  false,
                  'v1.0'
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "source_feature_id": feature_id,
                "import_batch_id": source[
                    "import_batch_id"
                ],
                "source_feature_index": source[
                    "source_feature_index"
                ],
                "source_sha256": SOURCE_SHA256,
                "plan_checksum": PLAN_CHECKSUM,
                "rollback_token": EVENT_TOKEN,
            },
        )


def restore_status(
    feature_id: str,
    status: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                update geography_boundary_source_features
                set geometry_validation_status = :status
                where id = cast(:feature_id as uuid)
                """
            ),
            {
                "feature_id": feature_id,
                "status": status,
            },
        )


def main() -> int:
    print("=" * 72)
    print(
        "BOUNDARY VALIDATION METADATA "
        "APPROVAL EVIDENCE REGRESSION"
    )
    print("=" * 72)

    source_checksum_before = sha256_file(SOURCE_PATH)
    source_mtime_before = SOURCE_PATH.stat().st_mtime_ns
    cleanup_conflict_event()
    baseline_counts = database_counts()
    plan = build_plan()

    first_feature_id = (
        plan["rows"][0]["source_feature_id"]
    )
    original_status = "NOT_VALIDATED"

    try:
        healthy = run_report(
            "healthy",
            PLAN_PATH,
            PLAN_CHECKSUM,
            SOURCE_SHA256,
            0,
        )
        check(
            healthy["healthy"] is True,
            "Healthy evidence passes",
            healthy["checks"],
        )
        check(
            healthy["readiness"][
                "ready_for_admin_decision"
            ]
            is True,
            "Healthy evidence is ready for admin decision",
        )
        check(
            healthy["summary"][
                "selected_row_count"
            ]
            == 500,
            "Healthy evidence selects 500 rows",
        )
        check(
            healthy["summary"][
                "identity_aligned_count"
            ]
            == 500,
            "All 500 identities align",
        )
        check(
            healthy["summary"][
                "status_aligned_count"
            ]
            == 500,
            "All 500 statuses align",
        )
        check(
            healthy["summary"][
                "runtime_ineligible_count"
            ]
            == 500,
            "All 500 rows remain runtime-ineligible",
        )
        check(
            healthy["summary"][
                "event_conflict_count"
            ]
            == 0,
            "Healthy evidence has no event conflicts",
        )
        check(
            healthy["summary"][
                "technical_check_count"
            ]
            == healthy["summary"][
                "technical_check_pass_count"
            ],
            "All technical checks pass",
        )

        wrong_plan_checksum = run_report(
            "wrong-plan-checksum",
            PLAN_PATH,
            "0" * 64,
            SOURCE_SHA256,
            1,
        )
        check(
            wrong_plan_checksum["healthy"] is False,
            "Wrong plan checksum is unhealthy",
        )
        check(
            wrong_plan_checksum["checks"][
                "expected_plan_checksum_matches_recorded"
            ]
            is False,
            "Wrong plan checksum is detected",
        )

        tampered = copy.deepcopy(plan)
        tampered["rows"][0][
            "source_vlcode"
        ] = "TAMPERED"
        tampered_path = OUTPUT_ROOT / "tampered.json"
        tampered_path.write_text(
            json.dumps(
                tampered,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        tampered_result = run_report(
            "tampered-content",
            tampered_path,
            PLAN_CHECKSUM,
            SOURCE_SHA256,
            1,
        )
        check(
            tampered_result["checks"][
                "plan_content_checksum_matches"
            ]
            is False,
            "Tampered plan content is detected",
        )

        wrong_source = run_report(
            "wrong-source-checksum",
            PLAN_PATH,
            PLAN_CHECKSUM,
            "0" * 64,
            1,
        )
        check(
            wrong_source["checks"][
                "expected_source_checksum_matches_recorded"
            ]
            is False,
            "Wrong recorded source checksum is detected",
        )
        check(
            wrong_source["checks"][
                "source_file_checksum_matches"
            ]
            is False,
            "Wrong current source checksum is detected",
        )

        duplicate = copy.deepcopy(plan)
        duplicate["rows"][1][
            "source_feature_id"
        ] = duplicate["rows"][0][
            "source_feature_id"
        ]
        duplicate["rows"][1][
            "source_feature_index"
        ] = duplicate["rows"][0][
            "source_feature_index"
        ]
        duplicate_path, duplicate_checksum = (
            write_variant(
                "duplicate-plan",
                duplicate,
            )
        )
        duplicate_result = run_report(
            "duplicate-identities",
            duplicate_path,
            duplicate_checksum,
            SOURCE_SHA256,
            1,
        )
        check(
            duplicate_result["checks"][
                "source_feature_ids_unique"
            ]
            is False,
            "Duplicate feature IDs are detected",
        )
        check(
            duplicate_result["checks"][
                "source_feature_indexes_unique"
            ]
            is False,
            "Duplicate feature indexes are detected",
        )

        unsafe = copy.deepcopy(plan)
        unsafe["rows"][0][
            "classification"
        ] = "REPAIRABLE_MAKE_VALID"
        unsafe_path, unsafe_checksum = write_variant(
            "unsafe-classification-plan",
            unsafe,
        )
        unsafe_result = run_report(
            "unsafe-classification",
            unsafe_path,
            unsafe_checksum,
            SOURCE_SHA256,
            1,
        )
        check(
            unsafe_result["checks"][
                "all_rows_validated_without_repair"
            ]
            is False,
            "Repair-required classification is rejected",
        )

        runtime_change = copy.deepcopy(plan)
        runtime_change["rows"][0][
            "runtime_eligibility_change_planned"
        ] = True
        runtime_path, runtime_checksum = (
            write_variant(
                "runtime-change-plan",
                runtime_change,
            )
        )
        runtime_result = run_report(
            "runtime-eligibility-change",
            runtime_path,
            runtime_checksum,
            SOURCE_SHA256,
            1,
        )
        check(
            runtime_result["checks"][
                "no_runtime_eligibility_change_planned"
            ]
            is False,
            "Runtime eligibility change is rejected",
        )

        missing = copy.deepcopy(plan)
        missing["rows"][0][
            "source_feature_id"
        ] = str(uuid.uuid4())
        missing_path, missing_checksum = write_variant(
            "missing-database-row-plan",
            missing,
        )
        missing_result = run_report(
            "missing-database-row",
            missing_path,
            missing_checksum,
            SOURCE_SHA256,
            1,
        )
        check(
            missing_result["checks"][
                "all_database_rows_present"
            ]
            is False,
            "Missing database row is detected",
        )
        check(
            missing_result["checks"][
                "all_database_identities_aligned"
            ]
            is False,
            "Missing row fails identity alignment",
        )

        restore_status(
            first_feature_id,
            "VALIDATION_REVIEW",
        )
        drift_result = run_report(
            "database-status-drift",
            PLAN_PATH,
            PLAN_CHECKSUM,
            SOURCE_SHA256,
            1,
        )
        check(
            drift_result["checks"][
                "all_database_statuses_not_validated"
            ]
            is False,
            "Database status drift is detected",
        )
        restore_status(
            first_feature_id,
            original_status,
        )

        create_conflict_event(plan)
        conflict_result = run_report(
            "active-event-conflict",
            PLAN_PATH,
            PLAN_CHECKSUM,
            SOURCE_SHA256,
            1,
        )
        check(
            conflict_result["checks"][
                "no_active_or_incomplete_event_conflicts"
            ]
            is False,
            "Incomplete event conflict is detected",
        )
        check(
            conflict_result["summary"][
                "event_conflict_count"
            ]
            == 1,
            "Exactly one event conflict is reported",
        )
        cleanup_conflict_event()

    finally:
        restore_status(
            first_feature_id,
            original_status,
        )
        cleanup_conflict_event()

    check(
        database_counts() == baseline_counts,
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

    source = REPORT_SCRIPT.read_text(
        encoding="utf-8"
    ).lower()

    for mutation in [
        "insert into geography_",
        "update geography_",
        "delete from geography_",
        "truncate geography_",
    ]:
        check(
            mutation not in source,
            f"Evidence generator contains no mutation SQL: {mutation}",
        )

    print("=" * 72)
    print(
        "BOUNDARY VALIDATION METADATA "
        "APPROVAL EVIDENCE REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
