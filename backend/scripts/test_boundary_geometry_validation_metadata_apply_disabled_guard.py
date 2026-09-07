#!/usr/bin/env python3
"""Regression for the disabled boundary validation metadata apply guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GUARD = (
    ROOT
    / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_disabled.py"
)
OUTPUT_ROOT = Path(
    "/tmp/boundary-validation-metadata-apply-disabled-regression"
)

SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
STATE_SLUG = "andaman_and_nicobar_islands"
STATE_NAME = "Andaman and Nicobar Islands"
ROLLBACK_TOKEN = "boundary-validation-metadata-disabled-regression"

EXPECTED_GUARDRAILS = [
    "db_writes_attempted",
    "source_files_changed",
    "source_features_changed",
    "geometry_repair_persisted",
    "geometry_validation_status_changed",
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
    if value is not None:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))


def run_case(
    name: str,
    expected_error: str,
    arguments: list[str],
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    output_dir = OUTPUT_ROOT / name
    command = [
        sys.executable,
        str(GUARD),
        "--output-dir",
        str(output_dir),
        *arguments,
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    json_path = (
        output_dir
        / "boundary_validation_metadata_apply_disabled_audit.json"
    )
    csv_path = (
        output_dir
        / "boundary_validation_metadata_apply_disabled_rows.csv"
    )

    check(
        completed.returncode != 0,
        f"{name}: invocation exits non-zero",
        {
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        },
    )
    check(json_path.is_file(), f"{name}: JSON audit is written", str(json_path))
    check(csv_path.is_file(), f"{name}: CSV audit is written", str(csv_path))

    data = json.loads(json_path.read_text(encoding="utf-8"))

    check(
        data["error"] == expected_error,
        f"{name}: expected rejection reason",
        {
            "expected": expected_error,
            "actual": data.get("error"),
        },
    )
    check(
        data["healthy"] is False,
        f"{name}: apply is not reported healthy",
        data.get("healthy"),
    )
    check(
        data["schema_version"]
        == "boundary_geometry_validation_metadata_apply_disabled_guard.v1",
        f"{name}: schema version is stable",
        data.get("schema_version"),
    )
    check(
        data["mode"]
        == "DISABLED_BOUNDARY_GEOMETRY_VALIDATION_METADATA_APPLY",
        f"{name}: mode is stable",
        data.get("mode"),
    )
    check(
        data["policy"]["real_apply_supported"] is False,
        f"{name}: real apply remains unsupported",
        data["policy"],
    )

    counts = data["database_counts"]
    check(
        counts["unchanged"] is True,
        f"{name}: database counts remain unchanged",
        counts,
    )
    check(
        counts["before"] == counts["after"],
        f"{name}: before and after counts match",
        counts,
    )

    for key in EXPECTED_GUARDRAILS:
        check(
            data["guardrails"].get(key) is False,
            f"{name}: guardrail remains false: {key}",
            data["guardrails"],
        )

    return completed, data


def scoped_arguments() -> list[str]:
    return [
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--source-sha256",
        SOURCE_SHA256,
        "--limit",
        "100",
    ]


def main() -> int:
    print("=" * 76)
    print("BOUNDARY VALIDATION METADATA APPLY DISABLED GUARD REGRESSION")
    print("=" * 76)

    run_case(
        "no_apply",
        "EXPLICIT_APPLY_FLAG_REQUIRED",
        scoped_arguments(),
    )

    run_case(
        "missing_scope",
        "STATE_SCOPE_REQUIRED",
        [
            "--apply",
            "--source-sha256",
            SOURCE_SHA256,
            "--limit",
            "100",
        ],
    )

    run_case(
        "invalid_limit",
        "BOUNDED_ROW_LIMIT_REQUIRED",
        [
            "--state-slug",
            STATE_SLUG,
            "--state-or-ut",
            STATE_NAME,
            "--source-sha256",
            SOURCE_SHA256,
            "--limit",
            "501",
            "--apply",
        ],
    )

    run_case(
        "missing_policy_flag",
        "ENABLE_VALIDATION_METADATA_WRITE_POLICY_FLAG_REQUIRED",
        [
            *scoped_arguments(),
            "--apply",
        ],
    )

    run_case(
        "missing_checksum",
        "SOURCE_CHECKSUM_CONFIRMATION_REQUIRED",
        [
            "--state-slug",
            STATE_SLUG,
            "--state-or-ut",
            STATE_NAME,
            "--limit",
            "100",
            "--apply",
            "--enable-validation-metadata-write",
        ],
    )

    run_case(
        "checksum_mismatch",
        "SOURCE_CHECKSUM_MISMATCH",
        [
            "--state-slug",
            STATE_SLUG,
            "--state-or-ut",
            STATE_NAME,
            "--source-sha256",
            "0" * 64,
            "--limit",
            "100",
            "--apply",
            "--enable-validation-metadata-write",
        ],
    )

    run_case(
        "missing_rollback",
        "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED",
        [
            *scoped_arguments(),
            "--apply",
            "--enable-validation-metadata-write",
        ],
    )

    run_case(
        "missing_dry_run_review",
        "DRY_RUN_REVIEW_REQUIRED",
        [
            *scoped_arguments(),
            "--apply",
            "--enable-validation-metadata-write",
            "--rollback-token",
            ROLLBACK_TOKEN,
        ],
    )

    run_case(
        "missing_admin_confirmation",
        "ADMIN_CONFIRMATION_REQUIRED",
        [
            *scoped_arguments(),
            "--apply",
            "--enable-validation-metadata-write",
            "--rollback-token",
            ROLLBACK_TOKEN,
            "--dry-run-reviewed",
        ],
    )

    _, final_data = run_case(
        "fully_confirmed",
        "BOUNDARY_VALIDATION_METADATA_APPLY_DISABLED_BY_POLICY",
        [
            *scoped_arguments(),
            "--apply",
            "--enable-validation-metadata-write",
            "--rollback-token",
            ROLLBACK_TOKEN,
            "--dry-run-reviewed",
            "--admin-confirmation",
        ],
    )

    summary = final_data["dry_run"]["summary"]

    check(
        final_data["rollback_token"] == ROLLBACK_TOKEN,
        "Fully confirmed: rollback token is recorded",
        final_data["rollback_token"],
    )
    check(
        final_data["source_sha256"] == SOURCE_SHA256,
        "Fully confirmed: source checksum is recorded",
        final_data["source_sha256"],
    )
    check(
        final_data["confirmations"]["explicit_apply_requested"] is True,
        "Fully confirmed: explicit apply intent is recorded",
        final_data["confirmations"],
    )
    check(
        final_data["confirmations"][
            "validation_metadata_write_policy_enabled"
        ]
        is True,
        "Fully confirmed: metadata policy flag is recorded",
        final_data["confirmations"],
    )
    check(
        final_data["confirmations"]["dry_run_reviewed"] is True,
        "Fully confirmed: dry-run review is recorded",
        final_data["confirmations"],
    )
    check(
        final_data["confirmations"]["admin_confirmation"] is True,
        "Fully confirmed: admin confirmation is recorded",
        final_data["confirmations"],
    )
    check(
        summary["selected_row_count"] == 100,
        "Fully confirmed: selects 100 bounded rows",
        summary,
    )
    check(
        summary["validated_count"] == 99,
        "Fully confirmed: plans 99 validated rows",
        summary,
    )
    check(
        summary["repair_required_count"] == 1,
        "Fully confirmed: plans one repair-required row",
        summary,
    )
    check(
        summary["validation_review_count"] == 0,
        "Fully confirmed: plans no manual validation review",
        summary,
    )
    check(
        summary["runtime_eligibility_change_planned_count"] == 0,
        "Fully confirmed: plans no runtime eligibility changes",
        summary,
    )
    check(
        final_data["policy"]["geometry_repair_allowed"] is False,
        "Fully confirmed: geometry repair remains disabled",
        final_data["policy"],
    )
    check(
        final_data["policy"]["runtime_eligibility_changes_allowed"] is False,
        "Fully confirmed: runtime eligibility changes remain disabled",
        final_data["policy"],
    )
    check(
        final_data["policy"]["runtime_promotion_allowed"] is False,
        "Fully confirmed: runtime promotion remains disabled",
        final_data["policy"],
    )

    print("=" * 76)
    print(
        "BOUNDARY VALIDATION METADATA APPLY DISABLED GUARD "
        "REGRESSION PASSED"
    )
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
