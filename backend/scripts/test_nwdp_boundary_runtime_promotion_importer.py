#!/usr/bin/env python3
"""Regression for guarded NWDP runtime promotion importer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "promote_nwdp_boundary_runtime.py"
PYTHON = ROOT / "venv" / "bin" / "python"


def assert_pass(name: str, condition: bool, payload=None) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(payload, indent=2, default=str)[:2000])
        raise SystemExit(1)
    print(f"PASS {name}")
    if payload is not None:
        print("    ", json.dumps(payload, indent=2, default=str)[:1200])


def run_report(*args: str) -> tuple[int, dict]:
    output = Path("/tmp/nwdp-boundary-runtime-promotion-importer-regression.json")
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
    if not output.exists():
        print(proc.stdout)
        raise SystemExit("Importer did not write output report")
    return proc.returncode, json.loads(output.read_text(encoding="utf-8"))


def assert_runtime_counts_zero(report: dict) -> None:
    counts = ((report.get("target_table_check") or {}).get("counts") or {})
    assert_pass(
        "Runtime tables remain empty",
        counts == {
            "geography_boundary_runtime_crosswalks": 0,
            "geography_boundary_runtime_features": 0,
            "geography_boundary_runtime_promotion_events": 0,
            "geography_boundary_runtime_sets": 0,
        },
        counts,
    )


def main() -> None:
    code, dry = run_report()
    assert_pass("Dry-run exits zero", code == 0, dry)
    assert_pass("Dry-run schema version is stable", dry.get("schema_version") == "nwdp_boundary_runtime_promotion_importer.v1", dry)
    assert_pass("Dry-run is healthy", dry.get("healthy") is True, dry)
    assert_pass("Dry-run attempts no DB writes", dry.get("db_writes_attempted") is False, dry)
    assert_pass("Dry-run writes no runtime tables", dry.get("runtime_tables_written") is False, dry)
    assert_pass("Dry-run has zero effective runtime rows", dry.get("runtime_rows_effective") == 0, dry)
    assert_pass("Dry-run keeps Android unchanged", dry["readiness"]["android_behavior_changed"] is False, dry["readiness"])
    assert_pass("Dry-run keeps runtime matching disabled", dry["readiness"]["ready_for_runtime_spatial_matching"] is False, dry["readiness"])
    assert_pass("Dry-run sees runtime tables", dry["readiness"]["runtime_tables_available"] is True, dry["readiness"])
    assert_pass("Dry-run sees all staged candidates", dry["plan"]["candidate_count"] == 29789, dry["plan"])
    assert_pass("Dry-run has zero promotable candidates", dry["plan"]["promotable_candidate_count"] == 0, dry["plan"])
    assert_pass("Dry-run excludes all candidates", dry["plan"]["excluded_candidate_count"] == 29789, dry["plan"])
    assert_runtime_counts_zero(dry)

    code, blocked = run_report("--apply")
    assert_pass("Apply path exits non-zero", code == 1, blocked)
    assert_pass("Apply path is explicitly blocked", blocked.get("apply_blocked") is True, blocked)
    assert_pass("Apply path reports no DB writes", blocked.get("db_writes_attempted") is False, blocked)
    assert_pass("Apply path writes no runtime tables", blocked.get("runtime_tables_written") is False, blocked)
    assert_pass("Apply path has zero effective runtime rows", blocked.get("runtime_rows_effective") == 0, blocked)
    assert_pass("Apply path keeps runtime matching disabled", blocked["readiness"]["ready_for_runtime_spatial_matching"] is False, blocked["readiness"])
    assert_pass("Apply path keeps Android unchanged", blocked["readiness"]["android_behavior_changed"] is False, blocked["readiness"])
    assert_runtime_counts_zero(blocked)

    print("=" * 72)
    print("NWDP BOUNDARY RUNTIME PROMOTION IMPORTER REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
