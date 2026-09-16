#!/usr/bin/env python3
"""Regression for the read-only national validation-metadata planner."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANNER = (
    ROOT / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_national_rollout.py"
)
BASE = Path("/tmp/national-validation-metadata-planner-regression")


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def run(output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--output-dir",
            str(output),
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def load(output: Path) -> dict:
    return json.loads(
        (
            output /
            "national_validation_metadata_wave_plan.json"
        ).read_text(encoding="utf-8")
    )


def main() -> int:
    shutil.rmtree(BASE, ignore_errors=True)
    BASE.mkdir(parents=True)

    first = run(
        BASE / "first",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
        "--workers", "2",
    )
    check(
        first.returncode == 0,
        "Two-state planner succeeds",
        {"stdout": first.stdout, "stderr": first.stderr},
    )

    report = load(BASE / "first")
    check(
        report["schema_version"] ==
            "boundary_geometry_validation_metadata_"
            "national_rollout_plan.v1"
        and report["mode"] ==
            "READ_ONLY_NATIONAL_VALIDATION_METADATA_WAVE_PLAN"
        and report["healthy"] is True,
        "National schema and mode are stable",
        report,
    )
    check(
        report["summary"]["selected_state_count"] == 2
        and report["summary"]["planned_state_count"] == 2
        and report["summary"]["selected_row_count"] == 1000
        and report["summary"][
            "failed_or_blocked_state_count"
        ] == 0,
        "Two-state wave totals are exact",
        report["summary"],
    )

    states = {
        row["state_slug"]: row
        for row in report["states"]
    }
    check(
        list(sorted(states)) == ["bihar", "uttar_pradesh"],
        "Requested state selection is exact",
        states,
    )
    check(
        states["bihar"]["selected_row_count"] == 500
        and states["uttar_pradesh"]["selected_row_count"] == 500,
        "Per-state selected counts are exact",
        states,
    )
    check(
        all(
            row["selected_row_count"] <= 500
            and len(row["plan_checksum"]) == 64
            and len(row["source_sha256"]) == 64
            and row["batch_id"]
            and row["rollback_token_proposal"].startswith(
                "national-validation-metadata-wave-1-"
            )
            for row in states.values()
        ),
        "State plans expose bounded deterministic identity",
        states,
    )

    for row in states.values():
        state_plan = json.loads(
            Path(row["plan_json"]).read_text(encoding="utf-8")
        )
        check(
            state_plan["schema_version"] ==
                "boundary_geometry_validation_metadata_"
                "bounded_state_plan.v1"
            and state_plan["healthy"] is True
            and state_plan["database_counts"]["unchanged"] is True
            and all(
                item["classification"] ==
                    "VALIDATED_NO_REPAIR"
                and item[
                    "current_geometry_validation_status"
                ] == "NOT_VALIDATED"
                and item[
                    "planned_geometry_validation_status"
                ] == "VALIDATED"
                and item[
                    "runtime_eligibility_change_planned"
                ] is False
                for item in state_plan["rows"]
            ),
            f"State plan is safe: {row['state_slug']}",
            state_plan,
        )

    check(
        report["database_counts"]["unchanged"] is True
        and report["database_counts"]["before"] ==
            report["database_counts"]["after"],
        "Planning performs no database writes",
        report["database_counts"],
    )
    check(
        all(value is False for value in report["guardrails"].values())
        and report["readiness"]["ready_for_national_apply"] is False
        and report["readiness"]["ready_for_runtime_promotion"] is False
        and report["readiness"][
            "ready_for_android_behavior_change"
        ] is False,
        "Runtime and Android guardrails remain closed",
        {
            "guardrails": report["guardrails"],
            "readiness": report["readiness"],
        },
    )

    second = run(
        BASE / "second",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
        "--workers", "1",
    )
    check(second.returncode == 0, "Deterministic rerun succeeds")
    second_report = load(BASE / "second")
    check(
        second_report["national_plan_checksum"] ==
            report["national_plan_checksum"],
        "National checksum ignores time, workers and output path",
        {
            "first": report["national_plan_checksum"],
            "second": second_report["national_plan_checksum"],
        },
    )

    protected = run(
        BASE / "first",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
    )
    check(
        protected.returncode != 0
        and "RUN_DIRECTORY_NOT_EMPTY_USE_RESUME_OR_FORCE" in (
            protected.stdout + protected.stderr
        ),
        "Existing run directory requires resume or force",
        {
            "stdout": protected.stdout,
            "stderr": protected.stderr,
        },
    )

    resumed = run(
        BASE / "first",
        "--resume",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
        "--workers", "2",
    )
    check(
        resumed.returncode == 0,
        "Existing run resumes successfully",
        {"stdout": resumed.stdout, "stderr": resumed.stderr},
    )
    resumed_report = load(BASE / "first")
    check(
        resumed_report["healthy"] is True
        and resumed_report["summary"]["resumed_state_count"] == 2
        and resumed_report["summary"]["generated_state_count"] == 0
        and all(
            row["execution_status"] == "RESUMED"
            for row in resumed_report["states"]
        ),
        "Resume reuses every validated state checkpoint",
        resumed_report,
    )
    check(
        resumed_report["national_plan_checksum"] ==
            report["national_plan_checksum"],
        "Resume preserves the national plan checksum",
        {
            "initial": report["national_plan_checksum"],
            "resumed": resumed_report["national_plan_checksum"],
        },
    )

    forced = run(
        BASE / "first",
        "--force",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
        "--workers", "1",
    )
    check(
        forced.returncode == 0,
        "Force regenerates an existing run",
        {"stdout": forced.stdout, "stderr": forced.stderr},
    )
    forced_report = load(BASE / "first")
    check(
        forced_report["healthy"] is True
        and forced_report["summary"]["generated_state_count"] == 2
        and forced_report["summary"]["resumed_state_count"] == 0
        and all(
            row["execution_status"] == "GENERATED"
            for row in forced_report["states"]
        ),
        "Force bypasses cached checkpoints",
        forced_report,
    )
    check(
        forced_report["national_plan_checksum"] ==
            report["national_plan_checksum"],
        "Forced regeneration preserves deterministic identity",
        {
            "initial": report["national_plan_checksum"],
            "forced": forced_report["national_plan_checksum"],
        },
    )

    stale_dir = BASE / "stale"
    shutil.copytree(BASE / "first", stale_dir)
    stale_checkpoint_path = (
        stale_dir / "states/bihar/checkpoint.json"
    )
    stale_checkpoint = json.loads(
        stale_checkpoint_path.read_text(encoding="utf-8")
    )
    stale_checkpoint["plan_checksum"] = "0" * 64
    stale_checkpoint_path.write_text(
        json.dumps(stale_checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    stale = run(
        stale_dir,
        "--resume",
        "--states", "bihar,uttar_pradesh",
        "--batch-limit", "500",
        "--workers", "2",
    )
    check(
        stale.returncode != 0,
        "Tampered checkpoint prevents successful resume",
        {"stdout": stale.stdout, "stderr": stale.stderr},
    )
    stale_report = load(stale_dir)
    stale_states = {
        row["state_slug"]: row
        for row in stale_report["states"]
    }
    check(
        stale_report["healthy"] is False
        and stale_report["summary"][
            "checkpoint_rejected_state_count"
        ] == 1
        and stale_states["bihar"]["status"] == "BLOCKED"
        and stale_states["bihar"]["execution_status"] ==
            "CHECKPOINT_REJECTED"
        and "STALE_CACHED_STATE_PLAN" in
            stale_states["bihar"]["error"]
        and stale_states["uttar_pradesh"]["execution_status"] ==
            "RESUMED",
        "Resume rejects stale state while preserving valid checkpoints",
        stale_report,
    )

    bad_limit = run(
        BASE / "bad-limit",
        "--states", "bihar",
        "--batch-limit", "501",
    )
    check(
        bad_limit.returncode != 0
        and "between 1 and 500" in (
            bad_limit.stdout + bad_limit.stderr
        ),
        "Oversized batch limit is rejected",
    )

    unknown = run(
        BASE / "unknown",
        "--states", "not_a_state",
    )
    check(
        unknown.returncode != 0
        and "UNKNOWN_STATE_SLUGS" in (
            unknown.stdout + unknown.stderr
        ),
        "Unknown state is rejected",
    )

    print("=" * 72)
    print("NATIONAL VALIDATION METADATA PLANNER REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
