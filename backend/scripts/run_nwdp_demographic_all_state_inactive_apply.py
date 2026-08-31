#!/usr/bin/env python3
"""Resumable all-state NWDP demographic inactive profile apply orchestrator.

By default this writes only a durable plan and monitorable run summary. Passing
--execute calls the guarded one-state apply command one state/UT at a time and
writes durable audit files so the run can resume after terminal close, shutdown,
or hibernation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
PLAN_SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_all_state_inactive_apply.py"
APPLY_SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_import.py"
DEFAULT_RUN_ROOT = ROOT / "data/staged/core_stack/nwdp_demographic_profile_apply_runs"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def completed_state_file(run_dir: Path, state: str) -> Path:
    return run_dir / "states" / f"{safe_slug(state)}.completed.json"


def state_audit_file(run_dir: Path, state: str) -> Path:
    return run_dir / "states" / f"{safe_slug(state)}.apply.json"


def state_error_file(run_dir: Path, state: str) -> Path:
    return run_dir / "states" / f"{safe_slug(state)}.error.json"


def run_plan(run_dir: Path, max_rows_per_state: int) -> dict:
    output = run_dir / "all_state_plan.json"
    proc = subprocess.run(
        [
            str(PYTHON),
            str(PLAN_SCRIPT),
            "--output",
            str(output),
            "--max-rows-per-state",
            str(max_rows_per_state),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    if proc.returncode != 0 or not output.exists():
        raise RuntimeError(f"all-state plan failed:\n{proc.stdout}")

    return load_json(output)


def run_state_apply(run_dir: Path, state: str, max_rows: int) -> dict:
    output = state_audit_file(run_dir, state)
    proc = subprocess.run(
        [
            str(PYTHON),
            str(APPLY_SCRIPT),
            "--state-or-ut",
            state,
            "--apply",
            "--max-rows",
            str(max_rows),
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    if not output.exists():
        error = {
            "state_or_ut": state,
            "healthy": False,
            "error": "STATE_APPLY_OUTPUT_NOT_WRITTEN",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "generated_at": utc_now(),
        }
        write_json(state_error_file(run_dir, state), error)
        return error

    data = load_json(output)
    data["returncode"] = proc.returncode
    if proc.returncode != 0 or data.get("healthy") is not True:
        error = {
            "state_or_ut": state,
            "healthy": False,
            "error": "STATE_APPLY_FAILED",
            "returncode": proc.returncode,
            "apply_output": data,
            "stdout_tail": proc.stdout[-4000:],
            "generated_at": utc_now(),
        }
        write_json(state_error_file(run_dir, state), error)
        return error

    return data


def summarize_run(run_dir: Path, started_at: str, status: str, state_results: list[dict], plan: dict, execute: bool) -> dict:
    completed = [row for row in state_results if row.get("healthy") is True]
    failed = [row for row in state_results if row.get("healthy") is not True]

    inserted = sum(int(row.get("apply_result", {}).get("inserted_count", 0)) for row in completed)
    skipped = sum(int(row.get("apply_result", {}).get("skipped_existing_count", 0)) for row in completed)
    planned = sum(int(row.get("apply_result", {}).get("planned_insert_count", 0)) for row in completed)

    started_ts = datetime.fromisoformat(started_at)
    elapsed_seconds = max((datetime.now(timezone.utc) - started_ts).total_seconds(), 0.0)

    return {
        "schema_version": "nwdp_demographic_all_state_inactive_apply_run.v1",
        "run_dir": str(run_dir),
        "started_at": started_at,
        "updated_at": utc_now(),
        "status": status,
        "execute": execute,
        "state_count_planned": len(plan.get("state_plans", [])),
        "state_count_completed_this_invocation": len(completed),
        "state_count_failed_this_invocation": len(failed),
        "planned_rows_processed_this_invocation": planned,
        "inserted_rows_this_invocation": inserted,
        "skipped_existing_rows_this_invocation": skipped,
        "elapsed_seconds_this_invocation": round(elapsed_seconds, 3),
        "rows_per_second_this_invocation": round((inserted + skipped) / elapsed_seconds, 4) if elapsed_seconds else 0,
        "failed_states_this_invocation": [row.get("state_or_ut") for row in failed],
        "guardrails": {
            "db_writes_attempted": bool(execute and (inserted > 0 or skipped > 0)),
            "demographic_profile_rows_written": bool(inserted > 0),
            "profiles_promoted": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--max-rows-per-state", type=int, default=200000)
    parser.add_argument("--stop-after-states", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Actually run one-state inactive profile applies. Omit for plan-only mode.")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at_path = run_dir / "started_at.txt"
    if started_at_path.exists():
        started_at = started_at_path.read_text(encoding="utf-8").strip()
    else:
        started_at = utc_now()
        started_at_path.write_text(started_at + "\n", encoding="utf-8")

    plan = run_plan(run_dir, args.max_rows_per_state)

    if not args.execute:
        summary = summarize_run(run_dir, started_at, "PLAN_ONLY_NO_APPLY_EXECUTED", [], plan, execute=False)
        summary["claim_boundary"] = (
            "Plan-only mode writes durable run metadata only. It does not insert "
            "demographic profiles, promote profiles, enable runtime lookup, or "
            "change Android behavior. Pass --execute for the guarded state-by-state apply."
        )
        write_json(run_dir / "run_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    state_results: list[dict] = []
    processed_now = 0

    for state_plan in plan.get("state_plans", []):
        state = state_plan["state_or_ut"]
        remaining = int(state_plan.get("remaining_insert_rows", 0))
        max_rows = int(state_plan.get("planned_profile_rows", 0))

        if remaining <= 0:
            continue

        done_file = completed_state_file(run_dir, state)
        if done_file.exists():
            continue

        if max_rows > args.max_rows_per_state:
            error = {
                "state_or_ut": state,
                "healthy": False,
                "error": "STATE_EXCEEDS_MAX_ROWS_PER_STATE",
                "planned_profile_rows": max_rows,
                "max_rows_per_state": args.max_rows_per_state,
                "generated_at": utc_now(),
            }
            write_json(state_error_file(run_dir, state), error)
            state_results.append(error)
            break

        result = run_state_apply(run_dir, state, args.max_rows_per_state)
        state_results.append(result)

        if result.get("healthy") is True:
            write_json(done_file, {
                "state_or_ut": state,
                "completed_at": utc_now(),
                "apply_output": str(state_audit_file(run_dir, state)),
                "planned_insert_count": result.get("apply_result", {}).get("planned_insert_count", 0),
                "inserted_count": result.get("apply_result", {}).get("inserted_count", 0),
                "skipped_existing_count": result.get("apply_result", {}).get("skipped_existing_count", 0),
            })
        else:
            break

        processed_now += 1
        summary = summarize_run(run_dir, started_at, "RUNNING", state_results, plan, execute=True)
        write_json(run_dir / "run_summary.json", summary)

        if args.stop_after_states > 0 and processed_now >= args.stop_after_states:
            summary = summarize_run(run_dir, started_at, "PAUSED_AFTER_STOP_LIMIT", state_results, plan, execute=True)
            write_json(run_dir / "run_summary.json", summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

    status = "FAILED" if any(row.get("healthy") is not True for row in state_results) else "COMPLETE_OR_NO_REMAINING_STATES"
    summary = summarize_run(run_dir, started_at, status, state_results, plan, execute=True)
    write_json(run_dir / "run_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
