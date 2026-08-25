#!/usr/bin/env python3
"""Regression for all-state NWDP inactive staging importer dry-run/apply block."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/import_nwdp_boundary_all_state_inactive_staging.py"
DRY_RUN_OUTPUT = Path("/tmp/nwdp-boundary-all-state-inactive-staging-importer-dry-run-regression.json")
APPLY_BLOCKED_OUTPUT = Path("/tmp/nwdp-boundary-all-state-inactive-staging-importer-apply-blocked-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("    ", json.dumps(detail, indent=2, default=str)[:1200])
    if not condition:
        raise AssertionError(label)


def run_importer(args: list[str], output: Path):
    if output.exists():
        output.unlink()
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output", str(output), *args],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    check(output.exists(), f"Importer wrote {output.name}", proc.stdout)
    return proc, json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    dry_proc, dry = run_importer([], DRY_RUN_OUTPUT)

    check(dry_proc.returncode == 0, "Dry-run exits zero", dry)
    check(dry["schema_version"] == "nwdp_boundary_all_state_inactive_staging_importer.v1", "Importer schema is stable", dry)
    check(dry["mode"] if "mode" in dry else dry["source"]["state_or_ut_scope"] == "ALL_STATES", "Importer scopes all states", dry)
    check(dry["healthy"] is True, "Dry-run is healthy", dry)
    check(dry["apply_mode"] is False, "Dry-run apply mode is false", dry)
    check(dry["db_writes_attempted"] is False, "Dry-run attempts no DB writes", dry)
    check(dry["runtime_tables_written"] is False, "Dry-run writes no runtime tables", dry)
    check(dry["runtime_spatial_matching_changed"] is False, "Dry-run keeps matching disabled", dry)
    check(dry["android_behavior_changed"] is False, "Dry-run keeps Android unchanged", dry)
    check(dry["lookup_api_enabled"] is False, "Dry-run keeps lookup disabled", dry)

    plan = dry["import_plan"]
    check(plan["planned_batch_insert_count"] == 36, "Dry-run plans 36 batches", plan)
    check(plan["planned_source_feature_insert_count"] == 654285, "Dry-run plans 654285 source features", plan)
    check(plan["planned_candidate_insert_count"] == 654285, "Dry-run plans 654285 candidates", plan)
    check(plan["planned_active_source_feature_count"] == 0, "Dry-run activates no source features", plan)
    check(plan["planned_active_candidate_count"] == 0, "Dry-run activates no candidates", plan)
    check(plan["planned_runtime_write_count"] == 0, "Dry-run plans no runtime writes", plan)
    check(plan["unsafe_counts"] == {}, "Dry-run has no unsafe counts", plan["unsafe_counts"])

    blocked_proc, blocked = run_importer(
        ["--apply", "--allow-all-state-inactive-staging-write"],
        APPLY_BLOCKED_OUTPUT,
    )

    check(blocked_proc.returncode != 0, "Apply checkpoint exits non-zero while unimplemented", blocked)
    check(blocked["healthy"] is False, "Apply checkpoint is unhealthy while blocked", blocked)
    check(blocked["apply_mode"] is True, "Apply checkpoint records apply mode", blocked)
    check(blocked["db_writes_attempted"] is False, "Blocked apply attempts no DB writes", blocked)
    check(blocked["runtime_tables_written"] is False, "Blocked apply writes no runtime tables", blocked)
    check(blocked["apply_result"]["error"] == "ALL_STATE_INACTIVE_STAGING_APPLY_NOT_IMPLEMENTED_REQUIRES_SEPARATE_CHECKPOINT", "Blocked apply reports policy error", blocked["apply_result"])
    check(blocked["readiness"]["ready_for_inactive_staging_apply"] is False, "Blocked apply keeps staging apply disabled", blocked["readiness"])
    check(blocked["readiness"]["ready_for_runtime_table_write"] is False, "Blocked apply keeps runtime write disabled", blocked["readiness"])

    print("=" * 72)
    print("NWDP BOUNDARY ALL-STATE INACTIVE STAGING IMPORTER REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
