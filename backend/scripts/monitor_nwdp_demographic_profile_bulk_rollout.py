#!/usr/bin/env python3
"""Monitor a bulk NWDP demographic profile rollout output directory."""

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


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_global_summary(output_dir: Path) -> dict:
    probe_dir = output_dir / "_monitor_readiness"
    proc = subprocess.run([
        str(PYTHON),
        "backend/scripts/report_nwdp_demographic_promotion_readiness.py",
        "--output-dir",
        str(probe_dir),
        "--limit",
        "10000",
    ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        return {"error": proc.stdout[-4000:]}
    report = json.loads((probe_dir / "nwdp_demographic_promotion_readiness_report.json").read_text(encoding="utf-8"))
    return report["summary"]


def snapshot(output_dir: Path, include_db: bool) -> dict:
    events_path = output_dir / "rollout_events.jsonl"
    summary_path = output_dir / "bulk_rollout_summary.json"
    events = load_events(events_path)
    successes = [e for e in events if e.get("event") == "batch_succeeded"]
    failures = [e for e in events if e.get("event") == "batch_failed"]

    result = {
        "schema_version": "nwdp_demographic_profile_bulk_rollout_monitor.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "events": str(events_path),
        "event_count": len(events),
        "batch_started_count": len([e for e in events if e.get("event") == "batch_started"]),
        "batch_succeeded_count": len(successes),
        "batch_failed_count": len(failures),
        "promoted_count_from_success_events": sum(int(e.get("promoted_count") or 0) for e in successes),
        "finished": summary_path.exists() or any(e.get("event") == "bulk_rollout_finished" for e in events),
        "latest_events": events[-5:],
        "recent_failures": failures[-10:],
    }
    if summary_path.exists():
        result["bulk_summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
    if include_db:
        result["global_readiness_summary"] = load_global_summary(output_dir)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()

    while True:
        print(json.dumps(snapshot(args.output_dir, include_db=not args.no_db), indent=2, sort_keys=True))
        sys.stdout.flush()
        if not args.watch:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
