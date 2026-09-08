#!/usr/bin/env python3
"""Regression for the bounded state validation metadata planner."""

from __future__ import annotations

import csv
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

from app.core.database import SessionLocal  # noqa: E402

PLANNER = (
    ROOT
    / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)
OUTPUT_ROOT = Path(
    "/tmp/bounded-validation-metadata-planner-regression"
)

STATE_SLUG = "andaman_and_nicobar_islands"
STATE_NAME = "Andaman and Nicobar Islands"
SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
SOURCE_PATH = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)

FALSE_GUARDRAILS = [
    "db_writes_attempted",
    "source_files_changed",
    "source_features_changed",
    "validation_metadata_written",
    "geometry_repair_persisted",
    "source_runtime_eligibility_changed",
    "boundary_candidates_promoted",
    "boundary_candidates_activated",
    "runtime_tables_written",
    "runtime_lookup_enabled",
    "lgd_geography_overwritten",
    "android_behavior_changed",
]


def check(condition: bool, label: str, value: Any = None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(json.dumps(value, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_counts() -> dict[str, int]:
    with SessionLocal() as db:
        row = db.execute(text("""
            select
              (select count(*) from geography_boundary_source_features)
                as source_feature_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'NOT_VALIDATED')
                as not_validated_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'VALIDATED')
                as validated_rows,
              (select count(*) from geography_boundary_source_features
               where eligible_for_runtime_after_promotion = true)
                as runtime_eligible_source_rows,
              (select count(*) from geography_boundary_crosswalk_candidates)
                as candidate_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where is_active = true)
                as active_candidate_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where promotion_status = 'PROMOTED')
                as promoted_candidate_rows,
              (select count(*) from geography_boundary_runtime_sets)
                as runtime_set_rows,
              (select count(*) from geography_boundary_runtime_features)
                as runtime_feature_rows,
              (select count(*) from geography_boundary_runtime_crosswalks)
                as runtime_crosswalk_rows
        """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def command(
    output_dir: Path,
    cursor: int,
    limit: int,
    source_sha256: str = SOURCE_SHA256,
) -> list[str]:
    return [
        sys.executable,
        str(PLANNER),
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--expected-source-sha256",
        source_sha256,
        "--cursor-after-index",
        str(cursor),
        "--limit",
        str(limit),
        "--output-dir",
        str(output_dir),
    ]


def run_success(
    name: str,
    cursor: int,
    limit: int,
) -> dict[str, Any]:
    output_dir = OUTPUT_ROOT / name
    completed = subprocess.run(
        command(output_dir, cursor, limit),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    json_path = (
        output_dir
        / f"{STATE_SLUG}_bounded_validation_metadata_plan.json"
    )
    csv_path = (
        output_dir
        / f"{STATE_SLUG}_bounded_validation_metadata_plan.csv"
    )

    check(
        completed.returncode == 0,
        f"{name}: planner exits zero",
        {
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        },
    )
    check(json_path.is_file(), f"{name}: JSON plan is written")
    check(csv_path.is_file(), f"{name}: CSV plan is written")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    check(data["healthy"] is True, f"{name}: plan is healthy")
    check(
        data["schema_version"]
        == "boundary_geometry_validation_metadata_bounded_state_plan.v1",
        f"{name}: schema version is stable",
    )
    check(
        data["mode"]
        == "READ_ONLY_BOUNDED_STATE_VALIDATION_METADATA_PLAN",
        f"{name}: mode is read-only",
    )
    check(
        len(csv_rows) == len(data["rows"]),
        f"{name}: CSV and JSON row counts match",
    )
    check(
        data["database_counts"]["unchanged"] is True,
        f"{name}: database counts are unchanged",
        data["database_counts"],
    )
    check(
        data["database_counts"]["before"]
        == data["database_counts"]["after"],
        f"{name}: before and after snapshots match",
    )

    for key in FALSE_GUARDRAILS:
        check(
            data["guardrails"].get(key) is False,
            f"{name}: guardrail remains false: {key}",
            data["guardrails"],
        )

    return data


def run_failure(
    name: str,
    cursor: int,
    limit: int,
    source_sha256: str,
    expected_error: str,
) -> None:
    output_dir = OUTPUT_ROOT / name
    completed = subprocess.run(
        command(output_dir, cursor, limit, source_sha256),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    combined = completed.stdout + completed.stderr
    check(
        completed.returncode != 0,
        f"{name}: invalid invocation exits non-zero",
        {"returncode": completed.returncode, "output": combined[-2000:]},
    )
    check(
        expected_error in combined,
        f"{name}: expected error is reported",
        combined[-2000:],
    )


def main() -> int:
    print("=" * 76)
    print("BOUNDED STATE VALIDATION METADATA PLANNER REGRESSION")
    print("=" * 76)

    before = database_counts()
    source_checksum_before = checksum(SOURCE_PATH)
    source_mtime_before = SOURCE_PATH.stat().st_mtime_ns

    check(
        source_checksum_before == SOURCE_SHA256,
        "Pinned source checksum matches",
        source_checksum_before,
    )

    run_failure(
        "checksum_mismatch",
        -1,
        500,
        "0" * 64,
        "SOURCE_CHECKSUM_MISMATCH",
    )

    run_failure(
        "limit_above_maximum",
        -1,
        501,
        SOURCE_SHA256,
        "--limit must be between 1 and 500",
    )

    run_failure(
        "limit_below_minimum",
        -1,
        0,
        SOURCE_SHA256,
        "--limit must be between 1 and 500",
    )

    first = run_success("batch_1", -1, 500)
    repeated = run_success("batch_1_repeated", -1, 500)

    check(
        first["batch"]["selected_row_count"] == 500,
        "First batch selects exactly 500 rows",
        first["batch"],
    )
    check(
        first["batch"]["first_source_feature_index"] == 0,
        "First batch starts at source index zero",
        first["batch"],
    )
    check(
        first["batch"]["has_more"] is True,
        "First batch reports more valid rows",
        first["batch"],
    )
    check(
        first["batch"]["remaining_valid_not_validated_count"] == 160,
        "First batch reports 160 remaining rows",
        first["batch"],
    )
    check(
        first["state_classification"]
        == {
            "valid_without_repair_count": 660,
            "repair_required_count": 9,
            "validation_review_count": 0,
        },
        "State classification is stable",
        first["state_classification"],
    )
    check(
        first["batch"]["batch_id"] == repeated["batch"]["batch_id"],
        "Repeated plan has deterministic batch ID",
    )
    check(
        first["batch"]["plan_checksum"]
        == repeated["batch"]["plan_checksum"],
        "Repeated plan has deterministic checksum",
    )
    check(
        first["rows"] == repeated["rows"],
        "Repeated plan has identical selected rows",
    )

    cursor = first["batch"]["next_cursor_after_index"]
    second = run_success("batch_2", cursor, 500)

    check(
        second["batch"]["selected_row_count"] == 160,
        "Second batch selects remaining 160 rows",
        second["batch"],
    )
    check(
        second["batch"]["first_source_feature_index"] > cursor,
        "Second batch begins after first cursor",
        second["batch"],
    )
    check(
        second["batch"]["has_more"] is False,
        "Second batch is terminal",
        second["batch"],
    )
    check(
        second["batch"]["remaining_valid_not_validated_count"] == 0,
        "Second batch reports no remaining rows",
        second["batch"],
    )

    rows = first["rows"] + second["rows"]
    ids = [row["source_feature_id"] for row in rows]
    indexes = [row["source_feature_index"] for row in rows]

    check(len(rows) == 660, "Combined batches contain 660 rows")
    check(len(set(ids)) == 660, "Combined source feature IDs are unique")
    check(
        len(set(indexes)) == 660,
        "Combined source feature indexes are unique",
    )
    check(
        indexes == sorted(indexes),
        "Combined rows are deterministically ordered",
    )
    check(
        all(
            row["classification"] == "VALIDATED_NO_REPAIR"
            for row in rows
        ),
        "Every selected row is valid without repair",
    )
    check(
        all(
            row["planned_geometry_validation_status"] == "VALIDATED"
            for row in rows
        ),
        "Every selected row plans VALIDATED status",
    )
    check(
        all(
            row["runtime_eligibility_change_planned"] is False
            for row in rows
        ),
        "No selected row plans runtime eligibility change",
    )
    check(
        all(row["source_geometry_hash"] for row in rows),
        "Every selected row has canonical geometry hash",
    )
    check(
        all(row["transformed_bbox"] for row in rows),
        "Every selected row has transformed bounding box",
    )
    check(
        all(row["transformed_centroid"] for row in rows),
        "Every selected row has transformed centroid",
    )

    after = database_counts()

    check(after == before, "Regression leaves database counts unchanged")
    check(
        checksum(SOURCE_PATH) == source_checksum_before,
        "Source checksum is unchanged",
    )
    check(
        SOURCE_PATH.stat().st_mtime_ns == source_mtime_before,
        "Source modification time is unchanged",
    )

    source = PLANNER.read_text(encoding="utf-8").lower()
    for forbidden in [
        "insert into geography_",
        "update geography_",
        "delete from geography_",
        "truncate geography_",
    ]:
        check(
            forbidden not in source,
            f"Planner contains no mutation SQL: {forbidden}",
        )

    print("=" * 76)
    print("BOUNDED STATE VALIDATION METADATA PLANNER REGRESSION PASSED")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
