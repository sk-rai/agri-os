#!/usr/bin/env python3
"""Regression for the disabled bounded-state validation metadata apply guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

PLANNER = (
    ROOT
    / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)
GUARD = (
    ROOT
    / "backend/scripts/"
    "apply_boundary_geometry_validation_metadata_bounded_state_disabled.py"
)
OUTPUT_ROOT = Path(
    "/tmp/bounded-validation-metadata-disabled-guard-regression"
)

STATE_SLUG = "andaman_and_nicobar_islands"
STATE_NAME = "Andaman and Nicobar Islands"
SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
ROLLBACK_TOKEN = "bounded-validation-metadata-disabled-regression"

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


def check(condition: bool, label: str, value: Any = None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(json.dumps(value, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def build_plan() -> tuple[Path, dict[str, Any]]:
    output_dir = OUTPUT_ROOT / "plan"
    command = [
        sys.executable,
        str(PLANNER),
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--expected-source-sha256",
        SOURCE_SHA256,
        "--cursor-after-index",
        "-1",
        "--limit",
        "500",
        "--output-dir",
        str(output_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    check(
        completed.returncode == 0,
        "Bounded source plan exits zero",
        {
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        },
    )

    path = (
        output_dir
        / f"{STATE_SLUG}_bounded_validation_metadata_plan.json"
    )
    check(path.is_file(), "Bounded source plan is written")

    data = json.loads(path.read_text(encoding="utf-8"))
    check(
        data["batch"]["selected_row_count"] == 500,
        "Bounded source plan selects 500 rows",
        data["batch"],
    )
    return path, data


def full_arguments(
    plan_path: Path,
    plan_checksum: str,
) -> list[str]:
    return [
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--source-sha256",
        SOURCE_SHA256,
        "--plan-json",
        str(plan_path),
        "--plan-checksum",
        plan_checksum,
        "--rollback-token",
        ROLLBACK_TOKEN,
        "--apply",
        "--enable-bounded-validation-metadata-write",
        "--dry-run-reviewed",
        "--event-schema-reviewed",
        "--admin-confirmation",
    ]


def run_case(
    name: str,
    arguments: list[str],
    expected_error: str,
) -> dict[str, Any]:
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
        / "bounded_validation_metadata_apply_disabled_audit.json"
    )
    csv_path = (
        output_dir
        / "bounded_validation_metadata_apply_disabled_rows.csv"
    )

    check(
        completed.returncode != 0,
        f"{name}: invocation exits non-zero",
        {
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        },
    )
    check(json_path.is_file(), f"{name}: JSON audit is written")
    check(csv_path.is_file(), f"{name}: CSV audit is written")

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
        f"{name}: apply remains unhealthy",
    )
    check(
        data["schema_version"]
        == "boundary_geometry_validation_metadata_bounded_state_apply_disabled.v1",
        f"{name}: schema version is stable",
    )
    check(
        data["policy"]["real_apply_supported"] is False,
        f"{name}: real apply remains unsupported",
    )
    check(
        data["database_counts"]["unchanged"] is True,
        f"{name}: database counts remain unchanged",
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


def without(values: list[str], option: str) -> list[str]:
    result = list(values)
    index = result.index(option)
    del result[index]
    if index < len(result) and not result[index].startswith("--"):
        del result[index]
    return result


def main() -> int:
    print("=" * 76)
    print("BOUNDED VALIDATION METADATA APPLY DISABLED GUARD REGRESSION")
    print("=" * 76)

    plan_path, plan = build_plan()
    plan_checksum = plan["batch"]["plan_checksum"]
    complete = full_arguments(plan_path, plan_checksum)

    run_case(
        "no_apply",
        without(complete, "--apply"),
        "EXPLICIT_APPLY_FLAG_REQUIRED",
    )

    missing_scope = without(complete, "--state-slug")
    missing_scope = without(missing_scope, "--state-or-ut")
    run_case(
        "missing_scope",
        missing_scope,
        "STATE_SCOPE_REQUIRED",
    )

    run_case(
        "missing_plan",
        without(complete, "--plan-json"),
        "PLAN_JSON_REQUIRED",
    )

    run_case(
        "missing_source_checksum",
        without(complete, "--source-sha256"),
        "SOURCE_CHECKSUM_REQUIRED",
    )

    run_case(
        "missing_plan_checksum",
        without(complete, "--plan-checksum"),
        "PLAN_CHECKSUM_REQUIRED",
    )

    run_case(
        "missing_policy_flag",
        without(
            complete,
            "--enable-bounded-validation-metadata-write",
        ),
        "BOUNDED_METADATA_WRITE_POLICY_FLAG_REQUIRED",
    )

    run_case(
        "missing_rollback_token",
        without(complete, "--rollback-token"),
        "ROLLBACK_OR_SUPERSESSION_TOKEN_REQUIRED",
    )

    run_case(
        "missing_dry_run_review",
        without(complete, "--dry-run-reviewed"),
        "DRY_RUN_REVIEW_REQUIRED",
    )

    run_case(
        "missing_event_schema_review",
        without(complete, "--event-schema-reviewed"),
        "EVENT_SCHEMA_REVIEW_REQUIRED",
    )

    run_case(
        "missing_admin_confirmation",
        without(complete, "--admin-confirmation"),
        "ADMIN_CONFIRMATION_REQUIRED",
    )

    wrong_checksum = list(complete)
    checksum_index = wrong_checksum.index("--plan-checksum") + 1
    wrong_checksum[checksum_index] = "0" * 64
    run_case(
        "wrong_plan_checksum",
        wrong_checksum,
        "PLAN_CHECKSUM_MISMATCH",
    )

    tampered_path = OUTPUT_ROOT / "tampered-plan.json"
    tampered = json.loads(json.dumps(plan))
    tampered["rows"][0]["source_geometry_hash"] = "0" * 64
    tampered_path.write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    tampered_arguments = full_arguments(
        tampered_path,
        plan_checksum,
    )
    run_case(
        "tampered_plan_content",
        tampered_arguments,
        "PLAN_CONTENT_CHECKSUM_MISMATCH",
    )

    final = run_case(
        "fully_confirmed",
        complete,
        "BOUNDED_STATE_VALIDATION_METADATA_APPLY_DISABLED_BY_POLICY",
    )

    check(
        final["plan_summary"]["batch"]["selected_row_count"] == 500,
        "Fully confirmed guard records 500 selected rows",
        final["plan_summary"]["batch"],
    )
    check(
        final["plan_summary"]["batch"]["plan_checksum"]
        == plan_checksum,
        "Fully confirmed guard records exact plan checksum",
    )
    check(
        final["source_sha256"] == SOURCE_SHA256,
        "Fully confirmed guard records source checksum",
    )
    check(
        final["rollback_token"] == ROLLBACK_TOKEN,
        "Fully confirmed guard records rollback token",
    )
    check(
        final["database_counts"]["after"]["validation_event_rows"]
        == final["database_counts"]["before"]["validation_event_rows"],
        "Fully confirmed guard writes no validation events",
    )
    check(
        final["database_counts"]["after"]["active_validation_event_rows"]
        == final["database_counts"]["before"][
            "active_validation_event_rows"
        ],
        "Fully confirmed guard activates no validation events",
    )
    check(
        all(
            row["classification"] == "VALIDATED_NO_REPAIR"
            and row["runtime_eligibility_change_planned"] is False
            for row in plan["rows"]
        ),
        "Source plan contains only safe validation rows",
    )

    print("=" * 76)
    print(
        "BOUNDED VALIDATION METADATA APPLY DISABLED GUARD "
        "REGRESSION PASSED"
    )
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
