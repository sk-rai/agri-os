#!/usr/bin/env python3
"""Regression for read-only NWDP boundary pilot promotion review planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend" / "scripts" / "plan_nwdp_boundary_pilot_promotion_review.py"
OUTPUT = Path("/tmp/nwdp-boundary-pilot-promotion-review-plan-regression.json")


def assert_pass(name: str, condition: bool, payload=None) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(payload, indent=2, default=str)[:2000])
        raise SystemExit(1)
    print(f"PASS {name}")
    if payload is not None:
        print("    ", json.dumps(payload, indent=2, default=str)[:1200])


def main() -> None:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--limit", "10", "--output", str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert_pass("Pilot planner exits zero", proc.returncode == 0, proc.stdout)
    assert_pass("Pilot planner wrote report", OUTPUT.exists(), proc.stdout)

    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert_pass("Pilot planner schema is stable", data.get("schema_version") == "nwdp_boundary_pilot_promotion_review_plan.v1", data)
    assert_pass("Pilot planner is read-only mode", data.get("mode") == "READ_ONLY_PILOT_SELECTION", data)
    assert_pass("Pilot planner attempts no DB writes", data.get("db_writes_attempted") is False, data)
    assert_pass("Pilot planner writes no runtime tables", data.get("runtime_tables_written") is False, data)
    assert_pass("Pilot planner keeps runtime matching disabled", data.get("runtime_spatial_matching_changed") is False, data)
    assert_pass("Pilot planner keeps Android unchanged", data.get("android_behavior_changed") is False, data)

    summary = data.get("summary") or {}
    assert_pass("Pilot planner selects 10 candidates", summary.get("selected_candidate_count") == 10, summary)
    assert_pass("Pilot planner does not allow runtime writes", summary.get("runtime_write_allowed_now") is False, summary)
    assert_pass("Pilot planner requires reviewer metadata", summary.get("requires_reviewer_metadata") is True, summary)
    assert_pass("Pilot planner requires geometry validation", summary.get("requires_geometry_validation") is True, summary)

    items = data.get("items") or []
    assert_pass("Pilot planner returns items", len(items) == 10, items)
    assert_pass("All pilot items are direct-code candidates", all(item["candidate_bucket"] == "DIRECT_VLCODE_MATCH" for item in items), items)
    assert_pass("All pilot items remain unpromoted", all(item["promotion_status"] == "NOT_PROMOTED" for item in items), items)
    assert_pass("All pilot items are runtime-write blocked", all(item["runtime_write_allowed_now"] is False for item in items), items)
    assert_pass("All pilot items preserve vlcode/LGD match", all(item["source_vlcode_matches_proposed_lgd"] is True for item in items), items)
    assert_pass(
        "All pilot items require review and geometry next actions",
        all(
            "reviewer must set APPROVED_FOR_PROMOTION with promotion-compatible decision" in item["required_next_actions"]
            and "geometry validation checkpoint required" in item["required_next_actions"]
            for item in items
        ),
        items,
    )

    print("=" * 72)
    print("NWDP BOUNDARY PILOT PROMOTION REVIEW PLAN REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
