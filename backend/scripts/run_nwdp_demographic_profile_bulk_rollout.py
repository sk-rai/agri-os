#!/usr/bin/env python3
"""Run resumable guarded NWDP demographic rollout batches across districts."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_list(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def load_readiness(output_dir: Path, state_or_ut: str | None = None, district: str | None = None) -> dict:
    command = [
        str(PYTHON),
        "backend/scripts/report_nwdp_demographic_promotion_readiness.py",
        "--output-dir",
        str(output_dir),
        "--limit",
        "10000",
    ]
    if state_or_ut:
        command += ["--state-or-ut", state_or_ut]
    if district:
        command += ["--district", district]
    proc = run_command(command)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout[-8000:])
    return load_json(output_dir / "nwdp_demographic_promotion_readiness_report.json")


def slug_part(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("/", "_")


def district_plan(readiness: dict) -> list[dict]:
    rows = [r for r in readiness["state_district_summary"] if int(r.get("auto_candidate_count") or 0) > 0]
    return sorted(rows, key=lambda r: (-int(r.get("auto_candidate_count") or 0), r.get("state_or_ut") or "", r.get("district") or ""))


def failure_key(row: dict) -> tuple[str, str]:
    return str(row.get("state_or_ut") or ""), str(row.get("district") or "")


def load_failure_skip_list(paths: list[Path]) -> tuple[set[tuple[str, str]], list[dict]]:
    skip_keys: set[tuple[str, str]] = set()
    skipped: list[dict] = []

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("failed_batches") or data.get("recent_failures") or [] if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError(f"{path} must be a JSON array or contain failed_batches/recent_failures")

        for row in rows:
            if not isinstance(row, dict):
                continue
            state_or_ut, district = failure_key(row)
            if not state_or_ut or not district:
                continue
            key = (state_or_ut, district)
            if key not in skip_keys:
                skipped.append({
                    "state_or_ut": state_or_ut,
                    "district": district,
                    "source": str(path),
                })
            skip_keys.add(key)

    return skip_keys, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-policy", action="store_true")
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-total-rows", type=int)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewer-notes-prefix", default="Admin-reviewed bulk rollout batch")
    parser.add_argument("--skip-failures-from", type=Path, action="append", default=[], help="JSON array or bulk summary containing failed districts to skip")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        raise SystemExit("--apply is required")
    if not args.enable_policy:
        raise SystemExit("--enable-policy is required")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    if args.max_total_rows is not None and args.max_total_rows <= 0:
        raise SystemExit("--max-total-rows must be positive")
    if args.district and not args.state_or_ut:
        raise SystemExit("--district requires --state-or-ut")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    events_path = args.output_dir / "rollout_events.jsonl"
    summary_path = args.output_dir / "bulk_rollout_summary.json"

    started_at = utc_now()
    readiness_before = load_readiness(args.output_dir / "_readiness_before", args.state_or_ut, args.district)
    plan = district_plan(readiness_before)
    skip_keys, skipped_districts = load_failure_skip_list(args.skip_failures_from)
    plan = [row for row in plan if failure_key(row) not in skip_keys]

    append_event(events_path, {
        "event": "bulk_rollout_started",
        "generated_at": started_at,
        "batch_size": args.batch_size,
        "max_total_rows": args.max_total_rows,
        "planned_district_count": len(plan),
        "planned_auto_candidate_count": sum(int(r["auto_candidate_count"]) for r in plan),
        "skipped_district_count": len(skipped_districts),
        "skipped_districts": skipped_districts,
    })

    total_attempted = 0
    total_promoted = 0
    failures = []
    successes = []

    for row in plan:
        state_or_ut = row["state_or_ut"]
        district = row["district"]
        remaining = int(row["auto_candidate_count"])

        while remaining > 0:
            if args.max_total_rows is not None and total_attempted >= args.max_total_rows:
                remaining = 0
                break

            batch_rows = min(args.batch_size, remaining)
            if args.max_total_rows is not None:
                batch_rows = min(batch_rows, args.max_total_rows - total_attempted)
            if batch_rows <= 0:
                break

            batch_slug = f"{slug_part(state_or_ut)}__{slug_part(district)}__{total_attempted + 1}_{total_attempted + batch_rows}"
            batch_dir = args.output_dir / batch_slug
            reviewer_notes = f"{args.reviewer_notes_prefix}: {state_or_ut.strip()} {district.strip()} rows {total_attempted + 1}-{total_attempted + batch_rows}."

            base = {
                "state_or_ut": state_or_ut,
                "district": district,
                "batch_rows": batch_rows,
                "batch_dir": str(batch_dir),
                "total_attempted_before_batch": total_attempted,
            }
            append_event(events_path, {"event": "batch_started", "generated_at": utc_now(), **base})

            proc = run_command([
                str(PYTHON),
                "backend/scripts/run_nwdp_demographic_profile_rollout_batch.py",
                "--apply",
                "--enable-policy",
                "--state-or-ut",
                state_or_ut,
                "--district",
                district,
                "--max-rows",
                str(batch_rows),
                "--reviewer-notes",
                reviewer_notes,
                "--output-dir",
                str(batch_dir),
            ])
            total_attempted += batch_rows

            if proc.returncode != 0:
                failure = {"event": "batch_failed", "generated_at": utc_now(), "returncode": proc.returncode, "stdout_tail": proc.stdout[-8000:], **base}
                failures.append(failure)
                append_event(events_path, failure)
                if args.stop_on_error:
                    break
                break

            summaries = sorted(batch_dir.glob("*__rollout_summary.json"))
            batch_summary = load_json(summaries[0]) if summaries else {}
            promoted = int(batch_summary.get("rollout_result", {}).get("promoted_count") or batch_rows)
            activated = int(batch_summary.get("rollout_result", {}).get("activated_count") or promoted)
            total_promoted += promoted
            remaining -= promoted

            success = {"event": "batch_succeeded", "generated_at": utc_now(), "returncode": 0, "promoted_count": promoted, "activated_count": activated, **base}
            successes.append(success)
            append_event(events_path, success)

        if args.stop_on_error and failures:
            break

    readiness_after = load_readiness(args.output_dir / "_readiness_after", args.state_or_ut, args.district)
    failed_districts_path = args.output_dir / "failed_districts.json"
    failure_districts = [
        {
            "state_or_ut": failure["state_or_ut"],
            "district": failure["district"],
            "batch_rows": failure["batch_rows"],
            "batch_dir": failure["batch_dir"],
            "returncode": failure["returncode"],
        }
        for failure in failures
    ]
    write_json_list(failed_districts_path, failure_districts)
    summary = {
        "schema_version": "nwdp_demographic_profile_bulk_rollout.v1",
        "generated_at": utc_now(),
        "started_at": started_at,
        "healthy": total_promoted > 0 and not failures,
        "events": str(events_path),
        "batch_size": args.batch_size,
        "max_total_rows": args.max_total_rows,
        "planned_district_count": len(plan),
        "planned_auto_candidate_count": sum(int(r["auto_candidate_count"]) for r in plan),
        "total_attempted_rows": total_attempted,
        "total_promoted_rows": total_promoted,
        "successful_batch_count": len(successes),
        "failed_batch_count": len(failures),
        "failed_batches": failures,
        "failed_districts": str(failed_districts_path),
        "skipped_district_count": len(skipped_districts),
        "skipped_districts": skipped_districts,
        "successful_batches": successes[-20:],
        "before": readiness_before["summary"],
        "after": readiness_after["summary"],
        "guardrails": {
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
        },
    }
    write_json(summary_path, summary)
    append_event(events_path, {"event": "bulk_rollout_finished", "generated_at": utc_now(), **summary})
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
