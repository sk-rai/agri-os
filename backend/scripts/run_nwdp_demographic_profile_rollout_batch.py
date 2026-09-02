#!/usr/bin/env python3
"""Run one guarded NWDP demographic approval -> promotion rollout batch."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"


def run_step(label: str, command: list[str], expected_returncode: int = 0) -> dict:
    proc = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    step = {"label": label, "returncode": proc.returncode, "stdout_tail": proc.stdout[-8000:]}
    if proc.returncode != expected_returncode:
        raise RuntimeError(json.dumps(step, indent=2, sort_keys=True))
    return step


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut", required=True)
    parser.add_argument("--district", required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--reviewer-notes", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-policy", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.max_rows <= 0:
        raise SystemExit("--max-rows must be positive")
    if not args.apply:
        raise SystemExit("--apply is required")
    if not args.enable_policy:
        raise SystemExit("--enable-policy is required")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = f"{args.state_or_ut.strip().lower()}__{args.district.strip().lower()}__{args.max_rows}".replace(" ", "_").replace("/", "_")

    approval_json = args.output_dir / f"{slug}__approval_apply.json"
    readiness_before_dir = args.output_dir / f"{slug}__promotion_readiness_after_approval"
    disabled_json = args.output_dir / f"{slug}__promotion_disabled_audit.json"
    promotion_json = args.output_dir / f"{slug}__promotion_apply.json"
    readiness_after_dir = args.output_dir / f"{slug}__promotion_readiness_after_promotion"
    summary_json = args.output_dir / f"{slug}__rollout_summary.json"

    steps = []

    steps.append(run_step("approval apply", [
        str(PYTHON), "backend/scripts/apply_nwdp_demographic_profile_review_approval.py",
        "--apply", "--enable-policy",
        "--state-or-ut", args.state_or_ut,
        "--district", args.district,
        "--reviewer-notes", args.reviewer_notes,
        "--max-rows", str(args.max_rows),
        "--output", str(approval_json),
    ]))
    approval = load_json(approval_json)

    steps.append(run_step("promotion readiness after approval", [
        str(PYTHON), "backend/scripts/report_nwdp_demographic_promotion_readiness.py",
        "--state-or-ut", args.state_or_ut,
        "--district", args.district,
        "--output-dir", str(readiness_before_dir),
    ]))
    readiness_before = load_json(readiness_before_dir / "nwdp_demographic_promotion_readiness_report.json")

    steps.append(run_step("promotion disabled audit", [
        str(PYTHON), "backend/scripts/apply_nwdp_demographic_profile_promotion.py",
        "--apply",
        "--state-or-ut", args.state_or_ut,
        "--district", args.district,
        "--limit", str(args.max_rows),
        "--output", str(disabled_json),
    ], expected_returncode=1))
    disabled = load_json(disabled_json)

    steps.append(run_step("promotion apply", [
        str(PYTHON), "backend/scripts/apply_nwdp_demographic_profile_promotion.py",
        "--apply", "--enable-policy",
        "--state-or-ut", args.state_or_ut,
        "--district", args.district,
        "--limit", str(args.max_rows),
        "--output", str(promotion_json),
    ]))
    promotion = load_json(promotion_json)

    steps.append(run_step("promotion readiness after promotion", [
        str(PYTHON), "backend/scripts/report_nwdp_demographic_promotion_readiness.py",
        "--state-or-ut", args.state_or_ut,
        "--district", args.district,
        "--output-dir", str(readiness_after_dir),
    ]))
    readiness_after = load_json(readiness_after_dir / "nwdp_demographic_promotion_readiness_report.json")

    approval_result = approval["apply_result"]
    promotion_result = promotion["apply_result"]

    healthy = (
        approval["healthy"] is True
        and readiness_before["healthy"] is True
        and disabled["healthy"] is False
        and promotion["healthy"] is True
        and readiness_after["healthy"] is True
        and int(approval_result["planned_approval_count"]) == args.max_rows
        and int(approval_result["approved_count"]) == args.max_rows
        and int(disabled["apply_result"]["planned_promotion_count"]) == args.max_rows
        and int(promotion_result["promoted_count"]) == args.max_rows
        and int(promotion_result["activated_count"]) == args.max_rows
        and int(readiness_after["summary"]["eligible_for_promotion_count"]) == 0
        and promotion["guardrails"]["runtime_lookup_enabled"] is False
        and promotion["guardrails"]["android_behavior_changed"] is False
    )

    summary = {
        "schema_version": "nwdp_demographic_profile_rollout_batch.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "state_or_ut": args.state_or_ut,
        "district": args.district,
        "max_rows": args.max_rows,
        "rollout_result": {
            "planned_approval_count": int(approval_result["planned_approval_count"]),
            "approved_count": int(approval_result["approved_count"]),
            "planned_promotion_count": int(promotion_result["planned_promotion_count"]),
            "promoted_count": int(promotion_result["promoted_count"]),
            "activated_count": int(promotion_result["activated_count"]),
            "remaining_eligible_after_promotion": int(readiness_after["summary"]["eligible_for_promotion_count"]),
        },
        "guardrails": {
            "disabled_audit_attempted_no_db_writes": disabled["guardrails"]["db_writes_attempted"] is False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
        },
        "outputs": {
            "approval": str(approval_json),
            "promotion_disabled_audit": str(disabled_json),
            "promotion": str(promotion_json),
            "summary": str(summary_json),
        },
        "steps": steps,
    }

    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
