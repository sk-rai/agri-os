#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path("/tmp/project-boundary-readiness-regression")


def check(condition: bool, label: str, detail=None) -> None:
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:4000])
        return
    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:4000])
    raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("PROJECT BOUNDARY READINESS REPORT REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/report_project_boundary_readiness.py"),
            "--output-dir",
            str(OUT_DIR),
            "--limit",
            "200",
            "--sample-limit",
            "50",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)

    check(proc.returncode == 0, "Readiness report exits zero", {
        "returncode": proc.returncode,
        "stderr": proc.stderr[-2000:],
    })

    json_path = OUT_DIR / "project_boundary_readiness_report.json"
    project_csv = OUT_DIR / "project_boundary_readiness_by_project.csv"
    state_csv = OUT_DIR / "project_boundary_readiness_by_state.csv"
    gap_csv = OUT_DIR / "project_boundary_readiness_gap_samples.csv"

    check(json_path.exists(), "Report writes JSON", str(json_path))
    check(project_csv.exists(), "Report writes project CSV", str(project_csv))
    check(state_csv.exists(), "Report writes state CSV", str(state_csv))
    check(gap_csv.exists(), "Report writes gap sample CSV", str(gap_csv))

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    readiness = data["readiness"]
    guardrails = data["guardrails"]

    check(data["schema_version"] == "project_boundary_readiness_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_PROJECT_BOUNDARY_READINESS_REPORT", "Report is read-only mode", data["mode"])
    check(data["healthy"] is True, "Report is healthy", data["healthy"])

    check(summary["active_project_count"] >= 0, "Active project count is readable", summary)
    check(summary["projects_with_villages_count"] >= 0, "Projects with villages count is readable", summary)
    check(summary["project_village_link_count"] >= 0, "Project village link count is readable", summary)
    check(summary["raw_boundary_candidate_count"] > 0, "NWDP boundary candidate staging is visible", summary)
    check(summary["raw_eligible_boundary_candidate_count"] > 0, "Eligible direct-code boundary candidates are visible", summary)
    check(summary["raw_manual_review_candidate_count"] >= 0, "Manual-review exclusions are visible", summary)
    check(summary["raw_blocked_candidate_count"] >= 0, "Blocked exclusions are visible", summary)
    check(summary["active_project_boundary_match_count"] >= 0, "Existing project boundary matches count is readable", summary)

    check(isinstance(data["project_rows"], list), "Project rows are emitted", data["project_rows"][:3])
    check(isinstance(data["state_rows"], list), "State rows are emitted", data["state_rows"][:3])
    check(isinstance(data["gap_samples"], list), "Gap samples are emitted", data["gap_samples"][:3])

    check(readiness["ready_for_admin_review"] is True, "Ready for admin review", readiness)
    check("ready_for_project_boundary_dry_run" in readiness, "Dry-run readiness is reported", readiness)
    check(readiness["ready_for_project_boundary_apply"] is False, "Not ready for project boundary apply", readiness)
    check(readiness["ready_for_runtime_spatial_matching"] is False, "Not ready for runtime spatial matching", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)

    check(guardrails["db_writes_attempted"] is False, "Report attempts no DB writes", guardrails)
    check(guardrails["project_boundary_matches_written"] is False, "Report writes no project boundary matches", guardrails)
    check(guardrails["boundary_candidates_activated"] is False, "Report activates no candidates", guardrails)
    check(guardrails["boundary_candidates_promoted"] is False, "Report promotes no candidates", guardrails)
    check(guardrails["runtime_boundary_features_written"] is False, "Report writes no runtime boundary features", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Report keeps runtime lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Report keeps Android unchanged", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Report does not overwrite LGD geography", guardrails)

    print("=" * 72)
    print("PROJECT BOUNDARY READINESS REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
