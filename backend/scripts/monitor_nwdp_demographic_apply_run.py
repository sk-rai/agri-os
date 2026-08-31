#!/usr/bin/env python3
"""Read-only monitor for resumable NWDP demographic all-state apply runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "data/staged/core_stack/nwdp_demographic_profile_apply_runs"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run_dir(run_root: Path) -> Path | None:
    if not run_root.exists():
        return None
    dirs = [path for path in run_root.iterdir() if path.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_dir = args.run_root / args.run_id if args.run_id else latest_run_dir(args.run_root)
    if run_dir is None or not run_dir.exists():
        print(json.dumps({
            "healthy": False,
            "error": "NO_NWDP_DEMOGRAPHIC_APPLY_RUN_FOUND",
            "run_root": str(args.run_root),
        }, indent=2, sort_keys=True))
        return 1

    plan_path = run_dir / "all_state_plan.json"
    summary_path = run_dir / "run_summary.json"
    states_dir = run_dir / "states"

    plan = load_json(plan_path) if plan_path.exists() else {}
    summary = load_json(summary_path) if summary_path.exists() else {}

    completed_files = sorted(states_dir.glob("*.completed.json")) if states_dir.exists() else []
    error_files = sorted(states_dir.glob("*.error.json")) if states_dir.exists() else []
    apply_files = sorted(states_dir.glob("*.apply.json")) if states_dir.exists() else []

    inserted_total = 0
    skipped_total = 0
    planned_total = 0
    completed_states = []

    for path in completed_files:
        data = load_json(path)
        completed_states.append(data.get("state_or_ut"))
        inserted_total += int(data.get("inserted_count") or 0)
        skipped_total += int(data.get("skipped_existing_count") or 0)
        planned_total += int(data.get("planned_insert_count") or 0)

    started_at = None
    started_at_file = run_dir / "started_at.txt"
    if started_at_file.exists():
        started_at = started_at_file.read_text(encoding="utf-8").strip()

    elapsed_seconds = None
    rows_per_second = None
    if started_at:
        elapsed_seconds = max((datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds(), 0.0)
        rows_per_second = round((inserted_total + skipped_total) / elapsed_seconds, 4) if elapsed_seconds else 0

    remaining_rows = plan.get("total_remaining_insert_rows")
    if isinstance(remaining_rows, int):
        remaining_rows = max(remaining_rows - inserted_total - skipped_total, 0)

    report = {
        "schema_version": "nwdp_demographic_apply_run_monitor.v1",
        "healthy": len(error_files) == 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "status": summary.get("status", "UNKNOWN"),
        "state_count_planned": plan.get("state_count"),
        "state_count_completed": len(completed_files),
        "state_count_failed": len(error_files),
        "apply_audit_file_count": len(apply_files),
        "planned_rows_completed": planned_total,
        "inserted_rows_completed": inserted_total,
        "skipped_existing_rows_completed": skipped_total,
        "remaining_rows_estimate": remaining_rows,
        "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        "rows_per_second": rows_per_second,
        "completed_states": completed_states[-10:],
        "error_files": [str(path) for path in error_files],
        "guardrails": {
            "read_only_monitor": True,
            "db_writes_attempted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
