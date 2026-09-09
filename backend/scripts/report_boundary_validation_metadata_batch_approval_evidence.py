#!/usr/bin/env python3
"""Read-only approval evidence for a bounded validation-metadata batch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402
from scripts.plan_boundary_geometry_validation_metadata_bounded_state import (  # noqa: E402
    canonical_checksum,
)

SCHEMA_VERSION = (
    "boundary_validation_metadata_batch_approval_evidence.v1"
)
PLAN_SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_bounded_state_plan.v1"
)
SOURCE_TABLE = "geography_boundary_source_features"
EVENT_TABLE = "geography_boundary_validation_metadata_events"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan-json",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-plan-checksum",
        required=True,
    )
    parser.add_argument(
        "--expected-source-sha256",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def recompute_plan_checksum(
    plan: dict[str, Any],
) -> str:
    scope = plan.get("scope") or {}
    source = plan.get("source") or {}

    payload = {
        "schema_version": plan.get("schema_version"),
        "state_slug": scope.get("state_slug"),
        "state_or_ut": scope.get("state_or_ut"),
        "import_batch_id": scope.get("import_batch_id"),
        "source_sha256": source.get("sha256"),
        "geometry_hash_algorithm": (
            source.get("geometry_hash_algorithm")
        ),
        "cursor_after_index": (
            scope.get("cursor_after_index")
        ),
        "limit": scope.get("limit"),
        "rows": plan.get("rows") or [],
    }

    return canonical_checksum(payload)


def database_counts(
    connection,
) -> dict[str, int]:
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


def load_database_rows(
    connection,
    feature_ids: list[str],
) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            f"""
            select
              id::text as source_feature_id,
              import_batch_id::text as import_batch_id,
              source_feature_index,
              source_vlcode,
              source_geometry_hash,
              geometry_validation_status,
              eligible_for_runtime_after_promotion
            from {SOURCE_TABLE}
            where id = any(
              cast(:source_feature_ids as uuid[])
            )
            order by source_feature_index, id
            """
        ),
        {"source_feature_ids": feature_ids},
    ).mappings()

    return [dict(row) for row in result]


def load_event_conflicts(
    connection,
    feature_ids: list[str],
) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            f"""
            select
              id::text as event_id,
              source_feature_id::text
                as source_feature_id,
              plan_checksum,
              rollback_token,
              apply_status,
              is_active
            from {EVENT_TABLE}
            where source_feature_id = any(
              cast(:source_feature_ids as uuid[])
            )
              and (
                is_active = true
                or apply_status in (
                  'PLANNED',
                  'APPLIED'
                )
              )
            order by source_feature_id, created_at
            """
        ),
        {"source_feature_ids": feature_ids},
    ).mappings()

    return [dict(row) for row in result]


def check_result(
    checks: dict[str, bool],
    name: str,
    condition: bool,
) -> None:
    checks[name] = bool(condition)


def expected_counts(
    before: dict[str, int],
    selected_count: int,
) -> dict[str, int]:
    after = dict(before)
    after["not_validated_rows"] -= selected_count
    after["validated_rows"] += selected_count
    after["validation_event_rows"] += selected_count
    after["active_validation_event_rows"] += (
        selected_count
    )
    return after


def write_outputs(
    output_dir: Path,
    report: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
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

    report["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
    }

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    fields = [
        "sequence",
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "classification",
        "current_geometry_validation_status",
        "planned_geometry_validation_status",
        "database_import_batch_id",
        "database_source_feature_index",
        "database_source_vlcode",
        "database_geometry_validation_status",
        "database_runtime_eligible",
        "identity_aligned",
        "status_aligned",
        "runtime_eligibility_aligned",
        "active_event_conflict",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = arguments()

    plan = json.loads(
        args.plan_json.read_text(encoding="utf-8")
    )
    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}
    planned_rows = list(plan.get("rows") or [])

    source_path = Path(str(source.get("path") or ""))
    feature_ids = [
        str(row.get("source_feature_id") or "")
        for row in planned_rows
    ]
    feature_indexes = [
        row.get("source_feature_index")
        for row in planned_rows
    ]

    recorded_plan_checksum = str(
        batch.get("plan_checksum") or ""
    )
    calculated_plan_checksum = (
        recompute_plan_checksum(plan)
    )
    recorded_source_checksum = str(
        source.get("sha256") or ""
    )

    source_file_present = source_path.is_file()
    calculated_source_checksum = (
        sha256_file(source_path)
        if source_file_present
        else None
    )

    with engine.connect() as connection:
        before_counts = database_counts(connection)
        database_rows = load_database_rows(
            connection,
            feature_ids,
        )
        event_conflicts = load_event_conflicts(
            connection,
            feature_ids,
        )
        after_read_counts = database_counts(connection)

    database_by_id = {
        row["source_feature_id"]: row
        for row in database_rows
    }
    conflict_ids = {
        row["source_feature_id"]
        for row in event_conflicts
    }

    evidence_rows: list[dict[str, Any]] = []

    for sequence, planned in enumerate(
        planned_rows,
        start=1,
    ):
        feature_id = str(
            planned.get("source_feature_id") or ""
        )
        database = database_by_id.get(feature_id)
        database_present = database is not None

        identity_aligned = bool(
            database_present
            and database["import_batch_id"]
            == scope.get("import_batch_id")
            and database["source_feature_index"]
            == planned.get("source_feature_index")
            and str(database["source_vlcode"] or "")
            == str(planned.get("source_vlcode") or "")
        )
        status_aligned = bool(
            database_present
            and database[
                "geometry_validation_status"
            ]
            == "NOT_VALIDATED"
        )
        runtime_aligned = bool(
            database_present
            and database[
                "eligible_for_runtime_after_promotion"
            ]
            is False
        )

        evidence_rows.append(
            {
                "sequence": sequence,
                "source_feature_id": feature_id,
                "source_feature_index": planned.get(
                    "source_feature_index"
                ),
                "source_vlcode": planned.get(
                    "source_vlcode"
                ),
                "classification": planned.get(
                    "classification"
                ),
                "current_geometry_validation_status": (
                    planned.get(
                        "current_geometry_validation_status"
                    )
                ),
                "planned_geometry_validation_status": (
                    planned.get(
                        "planned_geometry_validation_status"
                    )
                ),
                "database_import_batch_id": (
                    database.get("import_batch_id")
                    if database
                    else None
                ),
                "database_source_feature_index": (
                    database.get("source_feature_index")
                    if database
                    else None
                ),
                "database_source_vlcode": (
                    database.get("source_vlcode")
                    if database
                    else None
                ),
                "database_geometry_validation_status": (
                    database.get(
                        "geometry_validation_status"
                    )
                    if database
                    else None
                ),
                "database_runtime_eligible": (
                    database.get(
                        "eligible_for_runtime_after_promotion"
                    )
                    if database
                    else None
                ),
                "identity_aligned": identity_aligned,
                "status_aligned": status_aligned,
                "runtime_eligibility_aligned": (
                    runtime_aligned
                ),
                "active_event_conflict": (
                    feature_id in conflict_ids
                ),
            }
        )

    checks: dict[str, bool] = {}

    check_result(
        checks,
        "plan_file_present",
        args.plan_json.is_file(),
    )
    check_result(
        checks,
        "plan_schema_supported",
        plan.get("schema_version")
        == PLAN_SCHEMA_VERSION,
    )
    check_result(
        checks,
        "plan_reports_healthy",
        plan.get("healthy") is True,
    )
    check_result(
        checks,
        "selected_row_count_within_policy",
        1 <= len(planned_rows) <= 500,
    )
    check_result(
        checks,
        "selected_row_count_matches_batch",
        batch.get("selected_row_count")
        == len(planned_rows),
    )
    check_result(
        checks,
        "expected_plan_checksum_matches_recorded",
        args.expected_plan_checksum
        == recorded_plan_checksum,
    )
    check_result(
        checks,
        "plan_content_checksum_matches",
        args.expected_plan_checksum
        == calculated_plan_checksum,
    )
    check_result(
        checks,
        "expected_source_checksum_matches_recorded",
        args.expected_source_sha256
        == recorded_source_checksum,
    )
    check_result(
        checks,
        "source_file_present",
        source_file_present,
    )
    check_result(
        checks,
        "source_file_checksum_matches",
        calculated_source_checksum
        == args.expected_source_sha256,
    )
    check_result(
        checks,
        "source_feature_ids_present",
        all(feature_ids),
    )
    check_result(
        checks,
        "source_feature_ids_unique",
        len(set(feature_ids))
        == len(feature_ids),
    )
    check_result(
        checks,
        "source_feature_indexes_unique",
        len(set(feature_indexes))
        == len(feature_indexes),
    )
    check_result(
        checks,
        "source_feature_indexes_ordered",
        feature_indexes
        == sorted(feature_indexes),
    )
    check_result(
        checks,
        "all_rows_validated_without_repair",
        all(
            row.get("classification")
            == "VALIDATED_NO_REPAIR"
            for row in planned_rows
        ),
    )
    check_result(
        checks,
        "all_rows_currently_not_validated_in_plan",
        all(
            row.get(
                "current_geometry_validation_status"
            )
            == "NOT_VALIDATED"
            for row in planned_rows
        ),
    )
    check_result(
        checks,
        "all_rows_plan_validated_status",
        all(
            row.get(
                "planned_geometry_validation_status"
            )
            == "VALIDATED"
            for row in planned_rows
        ),
    )
    check_result(
        checks,
        "no_runtime_eligibility_change_planned",
        all(
            row.get(
                "runtime_eligibility_change_planned"
            )
            is False
            for row in planned_rows
        ),
    )
    check_result(
        checks,
        "all_database_rows_present",
        len(database_rows) == len(planned_rows),
    )
    check_result(
        checks,
        "all_database_identities_aligned",
        all(
            row["identity_aligned"]
            for row in evidence_rows
        ),
    )
    check_result(
        checks,
        "all_database_statuses_not_validated",
        all(
            row["status_aligned"]
            for row in evidence_rows
        ),
    )
    check_result(
        checks,
        "all_database_rows_runtime_ineligible",
        all(
            row["runtime_eligibility_aligned"]
            for row in evidence_rows
        ),
    )
    check_result(
        checks,
        "no_active_or_incomplete_event_conflicts",
        len(event_conflicts) == 0,
    )
    check_result(
        checks,
        "database_counts_unchanged",
        before_counts == after_read_counts,
    )

    technical_checks_passed = all(checks.values())
    selected_count = len(planned_rows)

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (
            datetime.now(timezone.utc).isoformat()
        ),
        "healthy": technical_checks_passed,
        "mode": (
            "READ_ONLY_BOUNDARY_VALIDATION_METADATA_"
            "BATCH_APPROVAL_EVIDENCE"
        ),
        "scope": {
            "state_slug": scope.get("state_slug"),
            "state_or_ut": scope.get("state_or_ut"),
            "import_batch_id": scope.get(
                "import_batch_id"
            ),
            "selected_row_count": selected_count,
        },
        "plan": {
            "path": str(args.plan_json),
            "schema_version": plan.get(
                "schema_version"
            ),
            "batch_id": batch.get("batch_id"),
            "recorded_checksum": (
                recorded_plan_checksum
            ),
            "expected_checksum": (
                args.expected_plan_checksum
            ),
            "calculated_checksum": (
                calculated_plan_checksum
            ),
            "first_source_feature_index": (
                batch.get(
                    "first_source_feature_index"
                )
            ),
            "last_source_feature_index": (
                batch.get(
                    "last_source_feature_index"
                )
            ),
            "next_cursor_after_index": (
                batch.get(
                    "next_cursor_after_index"
                )
            ),
            "remaining_valid_not_validated_count": (
                batch.get(
                    "remaining_valid_not_validated_count"
                )
            ),
        },
        "source": {
            "path": str(source_path),
            "recorded_sha256": (
                recorded_source_checksum
            ),
            "expected_sha256": (
                args.expected_source_sha256
            ),
            "calculated_sha256": (
                calculated_source_checksum
            ),
            "feature_count": source.get(
                "feature_count"
            ),
            "geometry_hash_algorithm": (
                source.get(
                    "geometry_hash_algorithm"
                )
            ),
        },
        "checks": checks,
        "summary": {
            "selected_row_count": selected_count,
            "database_row_count": len(
                database_rows
            ),
            "identity_aligned_count": sum(
                1
                for row in evidence_rows
                if row["identity_aligned"]
            ),
            "status_aligned_count": sum(
                1
                for row in evidence_rows
                if row["status_aligned"]
            ),
            "runtime_ineligible_count": sum(
                1
                for row in evidence_rows
                if row[
                    "runtime_eligibility_aligned"
                ]
            ),
            "event_conflict_count": len(
                event_conflicts
            ),
            "technical_check_count": len(
                checks
            ),
            "technical_check_pass_count": sum(
                1
                for value in checks.values()
                if value
            ),
        },
        "database_counts": {
            "before": before_counts,
            "after_read": after_read_counts,
            "unchanged": (
                before_counts
                == after_read_counts
            ),
            "expected_after_apply": (
                expected_counts(
                    before_counts,
                    selected_count,
                )
            ),
        },
        "event_conflicts": event_conflicts,
        "readiness": {
            "ready_for_admin_decision": (
                technical_checks_passed
            ),
            "approved_for_apply": False,
            "ready_for_enabled_apply": False,
            "ready_for_broad_apply": False,
            "ready_for_runtime_eligibility_change": (
                False
            ),
            "ready_for_runtime_lookup_enablement": (
                False
            ),
            "ready_for_android_behavior_change": (
                False
            ),
        },
        "pending_approval_fields": [
            "operator",
            "approver",
            "approval_timestamp",
            "approval_reference",
            "final_rollback_token",
            "enabled_implementation_review",
        ],
        "guardrails": {
            "db_writes_attempted": False,
            "source_files_changed": False,
            "source_features_changed": False,
            "validation_metadata_written": False,
            "validation_events_written": False,
            "geometry_repair_persisted": False,
            "source_runtime_eligibility_changed": (
                False
            ),
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "lgd_geography_overwritten": False,
            "android_behavior_changed": False,
        },
        "rows": evidence_rows,
    }

    write_outputs(
        args.output_dir,
        report,
        evidence_rows,
    )

    print(
        json.dumps(
            {
                "schema_version": report[
                    "schema_version"
                ],
                "healthy": report["healthy"],
                "scope": report["scope"],
                "plan": report["plan"],
                "summary": report["summary"],
                "database_counts": report[
                    "database_counts"
                ],
                "readiness": report["readiness"],
                "guardrails": report["guardrails"],
                "output_files": report[
                    "output_files"
                ],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

    return 0 if technical_checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
