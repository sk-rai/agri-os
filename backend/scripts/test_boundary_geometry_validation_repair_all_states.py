#!/usr/bin/env python3
"""Regression for the resumable boundary geometry validation orchestrator."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "run_boundary_geometry_validation_repair_all_states.py"
)
STATES = (
    "andaman_and_nicobar_islands,"
    "chandigarh,"
    "lakshadweep"
)


def check(condition: bool, label: str, detail: Any = None) -> None:
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        return

    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, default=str))
    raise AssertionError(label)


def run(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--states",
            STATES,
            "--workers",
            "2",
            "--sample-limit",
            "50",
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )


def verify_common(data: dict[str, Any]) -> None:
    summary = data["summary"]
    readiness = data["readiness"]
    guardrails = data["guardrails"]

    check(
        data["schema_version"]
        == "boundary_geometry_validation_repair_all_states.v1",
        "Schema version is stable",
        data["schema_version"],
    )
    check(
        data["mode"]
        == (
            "READ_ONLY_RESUMABLE_BOUNDARY_GEOMETRY_"
            "VALIDATION_REPAIR_ORCHESTRATOR"
        ),
        "Mode is read-only resumable orchestrator",
        data["mode"],
    )
    check(data["healthy"] is True, "Orchestrator is healthy")

    check(
        summary["selected_state_count"] == 3,
        "Three states are selected",
        summary,
    )
    check(
        summary["completed_state_count"] == 3,
        "Three states are completed",
        summary,
    )
    check(
        summary["failed_state_count"] == 0,
        "No state execution failed",
        summary,
    )
    check(
        summary["states_with_review_blockers_count"] == 0,
        "No pilot state has review blockers",
        summary,
    )
    check(
        summary["feature_count"] == 716,
        "Pilot feature count is stable",
        summary,
    )
    check(
        summary["source_valid_count"] == 707,
        "Pilot valid count is stable",
        summary,
    )
    check(
        summary["source_invalid_count"] == 9,
        "Pilot invalid count is stable",
        summary,
    )
    check(
        summary["validated_no_repair_count"] == 707,
        "No-repair count is stable",
        summary,
    )
    check(
        summary["repairable_make_valid_count"] == 9,
        "Repairable count is stable",
        summary,
    )
    check(
        summary["manual_review_count"] == 0,
        "No pilot feature requires manual review",
        summary,
    )
    check(
        summary["reimport_or_crs_review_count"] == 0,
        "No pilot feature requires reimport or CRS review",
        summary,
    )
    check(
        summary["transformed_valid_count"] == 716,
        "All transformed pilot geometries are valid",
        summary,
    )
    check(
        summary["transformed_inside_india_count"] == 716,
        "All transformed pilot geometries are inside India",
        summary,
    )

    check(
        readiness["ready_for_admin_national_validation_review"]
        is True,
        "Admin national validation review is ready",
        readiness,
    )
    check(
        readiness["ready_for_broad_geometry_repair_apply"]
        is False,
        "Broad geometry repair remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_selected_runtime_promotion_apply"]
        is False,
        "Selected runtime promotion remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_runtime_lookup_enablement"]
        is False,
        "Runtime lookup remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_android_behavior_change"]
        is False,
        "Android remains unchanged",
        readiness,
    )

    for key, value in guardrails.items():
        check(
            value is False,
            f"Guardrail remains false: {key}",
            guardrails,
        )


def main() -> int:
    print("=" * 72)
    print("BOUNDARY GEOMETRY ALL-STATE ORCHESTRATOR REGRESSION")
    print("=" * 72)

    check(SCRIPT.is_file(), "Orchestrator script exists", str(SCRIPT))

    with tempfile.TemporaryDirectory(
        prefix="boundary-geometry-orchestrator-regression-"
    ) as temporary:
        output_dir = Path(temporary)

        first = run(output_dir)
        print(first.stdout)

        check(
            first.returncode == 0,
            "Initial three-state run exits zero",
            {
                "returncode": first.returncode,
                "stderr": first.stderr[-2000:],
            },
        )

        json_path = (
            output_dir
            / "boundary_geometry_validation_repair_"
            "national_summary.json"
        )
        csv_path = (
            output_dir
            / "boundary_geometry_validation_repair_by_state.csv"
        )

        check(json_path.is_file(), "Orchestrator writes JSON")
        check(csv_path.is_file(), "Orchestrator writes CSV")

        first_data = json.loads(json_path.read_text(encoding="utf-8"))
        verify_common(first_data)

        check(
            first_data["summary"]["resumed_state_count"] == 0,
            "Initial run executes all selected states",
            first_data["summary"],
        )

        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        check(len(rows) == 3, "State CSV contains three rows", rows)
        check(
            {row["state_slug"] for row in rows}
            == {
                "andaman_and_nicobar_islands",
                "chandigarh",
                "lakshadweep",
            },
            "State CSV contains the expected states",
            rows,
        )

        second = run(output_dir)
        print(second.stdout)

        check(
            second.returncode == 0,
            "Resume run exits zero",
            {
                "returncode": second.returncode,
                "stderr": second.stderr[-2000:],
            },
        )

        second_data = json.loads(
            json_path.read_text(encoding="utf-8")
        )
        verify_common(second_data)

        check(
            second_data["summary"]["resumed_state_count"] == 3,
            "Resume run reuses all three reports",
            second_data["summary"],
        )
        check(
            all(
                row["execution_status"] == "RESUMED"
                for row in second_data["state_rows"]
            ),
            "Every state is marked resumed",
            second_data["state_rows"],
        )

    script_text = SCRIPT.read_text(encoding="utf-8").lower()

    check(
        "insert into geography_" not in script_text,
        "Orchestrator contains no geography inserts",
    )
    check(
        "update geography_" not in script_text,
        "Orchestrator contains no geography updates",
    )
    check(
        "delete from geography_" not in script_text,
        "Orchestrator contains no geography deletes",
    )

    print("=" * 72)
    print(
        "BOUNDARY GEOMETRY ALL-STATE "
        "ORCHESTRATOR REGRESSION PASSED"
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
