#!/usr/bin/env python3
"""Regression for resumable NWDP demographic all-state apply orchestrator."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
RUN_SCRIPT = ROOT / "backend/scripts/run_nwdp_demographic_all_state_inactive_apply.py"
MONITOR_SCRIPT = ROOT / "backend/scripts/monitor_nwdp_demographic_apply_run.py"
RUN_ROOT = Path("/tmp/nwdp-demographic-apply-runs-regression")
RUN_ID = "resume-regression"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2000])
    if not condition:
        raise AssertionError(label)


def run_command(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ALL-STATE APPLY ORCHESTRATOR RESUME REGRESSION")
    print("=" * 72)

    if RUN_ROOT.exists():
        shutil.rmtree(RUN_ROOT)

    code, output = run_command([
        str(PYTHON),
        str(RUN_SCRIPT),
        "--run-root",
        str(RUN_ROOT),
        "--run-id",
        RUN_ID,
        "--max-rows-per-state",
        "200000",
    ])
    check(code == 0, "Plan-only orchestrator exits zero", output)

    run_dir = RUN_ROOT / RUN_ID
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    check(summary["status"] == "PLAN_ONLY_NO_APPLY_EXECUTED", "Plan-only status is explicit", summary)
    check(summary["execute"] is False, "Execute flag is false by default", summary)
    check(summary["guardrails"]["demographic_profile_rows_written"] is False, "Plan-only writes no profiles", summary["guardrails"])
    check(summary["state_count_completed_this_invocation"] == 0, "Plan-only completes no state applies", summary)
    check((run_dir / "all_state_plan.json").exists(), "Durable all-state plan exists", str(run_dir))

    completed_files = sorted((run_dir / "states").glob("*.completed.json"))
    check(len(completed_files) == 0, "Plan-only creates no completed-state markers", [str(path) for path in completed_files])

    code, monitor_output = run_command([
        str(PYTHON),
        str(MONITOR_SCRIPT),
        "--run-root",
        str(RUN_ROOT),
        "--run-id",
        RUN_ID,
    ])
    monitor = json.loads(monitor_output)
    check(code == 0, "Monitor exits zero", monitor)
    check(monitor["state_count_completed"] == 0, "Monitor sees no completed state applies", monitor)
    check(monitor["inserted_rows_completed"] == 0, "Monitor reports zero inserted rows", monitor)
    check(monitor["guardrails"]["read_only_monitor"] is True, "Monitor is read-only", monitor["guardrails"])

    code, output = run_command([
        str(PYTHON),
        str(RUN_SCRIPT),
        "--run-root",
        str(RUN_ROOT),
        "--run-id",
        RUN_ID,
        "--max-rows-per-state",
        "200000",
        "--resume",
    ])
    check(code == 0, "Resume plan-only orchestrator pass exits zero", output)

    completed_files_after = sorted((run_dir / "states").glob("*.completed.json"))
    check(len(completed_files_after) == 0, "Resume keeps zero completed markers in plan-only mode", [str(path) for path in completed_files_after])

    final_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    check(final_summary["status"] == "PLAN_ONLY_NO_APPLY_EXECUTED", "Resume summary remains plan-only", final_summary)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ALL-STATE APPLY ORCHESTRATOR RESUME REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
