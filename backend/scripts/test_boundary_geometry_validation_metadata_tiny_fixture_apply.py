#!/usr/bin/env python3
"""Regression for tiny-fixture boundary validation metadata apply."""

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

from app.core.database import SessionLocal  # noqa: E402

APPLY_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_tiny_fixture.py"
)
OUTPUT_ROOT = Path(
    "/tmp/boundary-validation-metadata-tiny-fixture-regression"
)

FIXTURE_ID = "9a18114f-5350-5173-97df-f24e1e64c30b"
SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
ROLLBACK_TOKEN = "boundary-validation-metadata-tiny-fixture-regression"
SOURCE_PATH = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)

SAFE_FALSE_GUARDRAILS = [
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


def check(condition: bool, label: str, value: Any = None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(json.dumps(value, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_snapshot() -> dict[str, Any]:
    with SessionLocal() as db:
        row = db.execute(text("""
            select
              sf.id::text as source_feature_id,
              sf.source_geometry_hash,
              sf.source_bbox,
              sf.transformed_bbox,
              sf.transformed_centroid,
              sf.geometry_validation_status,
              sf.eligible_for_runtime_after_promotion,
              sf.metadata,
              (select count(*)
               from geography_boundary_source_features)
                as source_feature_rows,
              (select count(*)
               from geography_boundary_source_features
               where geometry_validation_status = 'NOT_VALIDATED')
                as not_validated_rows,
              (select count(*)
               from geography_boundary_source_features
               where geometry_validation_status = 'VALIDATED')
                as validated_rows,
              (select count(*)
               from geography_boundary_source_features
               where eligible_for_runtime_after_promotion = true)
                as runtime_eligible_source_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates)
                as candidate_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates
               where is_active = true)
                as active_candidate_rows,
              (select count(*)
               from geography_boundary_crosswalk_candidates
               where promotion_status = 'PROMOTED')
                as promoted_candidate_rows,
              (select count(*)
               from geography_boundary_runtime_sets)
                as runtime_set_rows,
              (select count(*)
               from geography_boundary_runtime_features)
                as runtime_feature_rows,
              (select count(*)
               from geography_boundary_runtime_crosswalks)
                as runtime_crosswalk_rows
            from geography_boundary_source_features sf
            where sf.id = cast(:fixture_id as uuid)
        """), {"fixture_id": FIXTURE_ID}).mappings().one()

    data = dict(row)
    for key, value in list(data.items()):
        if key.endswith("_rows"):
            data[key] = int(value or 0)
    return data


def common_arguments(output_name: str) -> list[str]:
    return [
        "--source-feature-id",
        FIXTURE_ID,
        "--source-sha256",
        SOURCE_SHA256,
        "--rollback-token",
        ROLLBACK_TOKEN,
        "--output-dir",
        str(OUTPUT_ROOT / output_name),
        "--enable-validation-metadata-write",
        "--dry-run-reviewed",
        "--admin-confirmation",
    ]


def run(
    output_name: str,
    extra_arguments: list[str],
    expected_returncode: int,
    expected_action: str,
    expected_error: str | None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(APPLY_SCRIPT),
        *common_arguments(output_name),
        *extra_arguments,
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output_dir = OUTPUT_ROOT / output_name
    json_path = (
        output_dir
        / "boundary_validation_metadata_tiny_fixture_apply_audit.json"
    )
    csv_path = (
        output_dir
        / "boundary_validation_metadata_tiny_fixture_apply_rows.csv"
    )

    check(
        completed.returncode == expected_returncode,
        f"{output_name}: expected exit code",
        {
            "expected": expected_returncode,
            "actual": completed.returncode,
            "stderr": completed.stderr[-2000:],
        },
    )
    check(json_path.is_file(), f"{output_name}: JSON audit is written")
    check(csv_path.is_file(), f"{output_name}: CSV audit is written")

    data = json.loads(json_path.read_text(encoding="utf-8"))

    check(
        data["action"] == expected_action,
        f"{output_name}: expected action",
        data,
    )
    check(
        data.get("error") == expected_error,
        f"{output_name}: expected error",
        data,
    )
    check(
        data["schema_version"]
        == "boundary_geometry_validation_metadata_tiny_fixture_apply.v1",
        f"{output_name}: schema version is stable",
    )

    return data


def assert_safe_guardrails(
    name: str,
    data: dict[str, Any],
) -> None:
    for key in SAFE_FALSE_GUARDRAILS:
        check(
            data["guardrails"].get(key) is False,
            f"{name}: guardrail remains false: {key}",
            data["guardrails"],
        )


def cleanup_if_needed() -> None:
    snapshot = database_snapshot()
    metadata = snapshot.get("metadata") or {}
    marker = (
        metadata.get("tiny_fixture_validation_metadata_apply")
        if isinstance(metadata, dict)
        else None
    )
    if not isinstance(marker, dict):
        return

    token = marker.get("rollback_token")
    if not token:
        return

    command = [
        sys.executable,
        str(APPLY_SCRIPT),
        "--source-feature-id",
        FIXTURE_ID,
        "--source-sha256",
        SOURCE_SHA256,
        "--rollback-token",
        token,
        "--output-dir",
        str(OUTPUT_ROOT / "emergency-cleanup"),
        "--rollback",
        "--enable-validation-metadata-write",
        "--dry-run-reviewed",
        "--admin-confirmation",
    ]
    subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    print("=" * 76)
    print("BOUNDARY VALIDATION METADATA TINY FIXTURE APPLY REGRESSION")
    print("=" * 76)

    cleanup_if_needed()

    before = database_snapshot()
    source_hash_before = sha256_file(SOURCE_PATH)

    check(
        before["geometry_validation_status"] == "NOT_VALIDATED",
        "Fixture begins NOT_VALIDATED",
        before,
    )
    check(
        before["source_geometry_hash"] is None,
        "Fixture begins without canonical geometry hash",
        before,
    )
    check(
        before["eligible_for_runtime_after_promotion"] is False,
        "Fixture begins runtime-ineligible",
        before,
    )

    try:
        rejected = run(
            "missing_apply_or_rollback",
            [],
            1,
            "REJECTED",
            "EXACTLY_ONE_OF_APPLY_OR_ROLLBACK_REQUIRED",
        )
        assert_safe_guardrails("missing_apply_or_rollback", rejected)
        check(
            rejected["guardrails"]["db_writes_attempted"] is False,
            "Rejected invocation attempts no DB writes",
        )

        wrong_id_command = [
            sys.executable,
            str(APPLY_SCRIPT),
            "--source-feature-id",
            "00000000-0000-0000-0000-000000000000",
            "--source-sha256",
            SOURCE_SHA256,
            "--rollback-token",
            ROLLBACK_TOKEN,
            "--output-dir",
            str(OUTPUT_ROOT / "wrong_fixture"),
            "--apply",
            "--enable-validation-metadata-write",
            "--dry-run-reviewed",
            "--admin-confirmation",
        ]
        wrong_id = subprocess.run(
            wrong_id_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        wrong_id_path = (
            OUTPUT_ROOT
            / "wrong_fixture/"
            "boundary_validation_metadata_tiny_fixture_apply_audit.json"
        )
        check(wrong_id.returncode == 1, "Wrong fixture ID exits non-zero")
        check(wrong_id_path.is_file(), "Wrong fixture ID writes audit")
        wrong_id_data = json.loads(wrong_id_path.read_text())
        check(
            wrong_id_data["error"] == "TINY_FIXTURE_ID_REQUIRED",
            "Wrong fixture ID is rejected",
            wrong_id_data,
        )

        applied = run(
            "apply",
            ["--apply"],
            0,
            "APPLIED",
            None,
        )
        assert_safe_guardrails("apply", applied)
        check(
            applied["changed_row_count"] == 1,
            "Apply changes exactly one row",
            applied,
        )
        check(
            applied["guardrails"]["db_writes_attempted"] is True,
            "Apply records DB write",
        )
        check(
            applied["guardrails"]["validation_metadata_written"] is True,
            "Apply records validation metadata write",
        )
        check(
            applied["final_row"]["geometry_validation_status"]
            == "VALIDATED",
            "Apply sets fixture to VALIDATED",
        )
        check(
            applied["final_row"]["eligible_for_runtime_after_promotion"]
            is False,
            "Apply leaves runtime eligibility false",
        )
        check(
            applied["plan"]["classification"] == "VALIDATED_NO_REPAIR",
            "Apply uses safely validated classification",
        )
        check(
            applied["plan"]["runtime_eligibility_change_planned"] is False,
            "Plan contains no runtime eligibility change",
        )

        after_apply = database_snapshot()
        check(
            after_apply["not_validated_rows"]
            == before["not_validated_rows"] - 1,
            "Apply decreases NOT_VALIDATED by one",
        )
        check(
            after_apply["validated_rows"] == before["validated_rows"] + 1,
            "Apply increases VALIDATED by one",
        )

        for key in [
            "source_feature_rows",
            "runtime_eligible_source_rows",
            "candidate_rows",
            "active_candidate_rows",
            "promoted_candidate_rows",
            "runtime_set_rows",
            "runtime_feature_rows",
            "runtime_crosswalk_rows",
        ]:
            check(
                after_apply[key] == before[key],
                f"Apply leaves count unchanged: {key}",
                {"before": before[key], "after": after_apply[key]},
            )

        repeated = run(
            "idempotent_apply",
            ["--apply"],
            0,
            "IDEMPOTENT_NO_OP",
            None,
        )
        assert_safe_guardrails("idempotent_apply", repeated)
        check(
            repeated["changed_row_count"] == 0,
            "Repeated apply changes zero rows",
        )
        check(
            repeated["before_counts"] == repeated["after_counts"],
            "Repeated apply leaves all counts unchanged",
        )
        check(
            repeated["guardrails"]["db_writes_attempted"] is False,
            "Repeated apply attempts no DB writes",
        )

        wrong_token_command = [
            sys.executable,
            str(APPLY_SCRIPT),
            "--source-feature-id",
            FIXTURE_ID,
            "--source-sha256",
            SOURCE_SHA256,
            "--rollback-token",
            "wrong-rollback-token",
            "--output-dir",
            str(OUTPUT_ROOT / "wrong_rollback_token"),
            "--rollback",
            "--enable-validation-metadata-write",
            "--dry-run-reviewed",
            "--admin-confirmation",
        ]
        wrong_token = subprocess.run(
            wrong_token_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        wrong_token_path = (
            OUTPUT_ROOT
            / "wrong_rollback_token/"
            "boundary_validation_metadata_tiny_fixture_apply_audit.json"
        )
        check(
            wrong_token.returncode == 1,
            "Wrong rollback token exits non-zero",
        )
        check(wrong_token_path.is_file(), "Wrong rollback token writes audit")
        wrong_token_data = json.loads(wrong_token_path.read_text())
        check(
            wrong_token_data["error"] == "ROLLBACK_TOKEN_MISMATCH",
            "Wrong rollback token is rejected",
            wrong_token_data,
        )
        check(
            database_snapshot() == after_apply,
            "Rejected rollback leaves fixture unchanged",
        )

        rolled_back = run(
            "rollback",
            ["--rollback"],
            0,
            "ROLLED_BACK",
            None,
        )
        assert_safe_guardrails("rollback", rolled_back)
        check(
            rolled_back["changed_row_count"] == 1,
            "Rollback changes exactly one row",
        )
        check(
            rolled_back["guardrails"]["db_writes_attempted"] is True,
            "Rollback records DB write",
        )
        check(
            rolled_back["guardrails"]["validation_metadata_rolled_back"]
            is True,
            "Rollback records metadata restoration",
        )

        after = database_snapshot()
        check(after == before, "Rollback restores exact database baseline")
        check(
            sha256_file(SOURCE_PATH) == source_hash_before,
            "Source GeoJSON checksum is unchanged",
        )

    finally:
        cleanup_if_needed()

    final = database_snapshot()
    check(final == before, "Regression cleanup returns fixture to baseline")

    print("=" * 76)
    print(
        "BOUNDARY VALIDATION METADATA TINY FIXTURE APPLY "
        "REGRESSION PASSED"
    )
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
