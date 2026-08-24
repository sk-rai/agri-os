#!/usr/bin/env python3
"""Regression for read-only NWDP pilot geometry materialization planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend" / "scripts" / "plan_nwdp_boundary_pilot_geometry_materialization.py"
OUTPUT = Path("/tmp/nwdp-boundary-pilot-geometry-materialization-plan-regression.json")


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
    assert_pass("Geometry materialization planner exits zero", proc.returncode == 0, proc.stdout)
    assert_pass("Geometry materialization planner wrote report", OUTPUT.exists(), proc.stdout)

    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert_pass("Geometry materialization schema is stable", data.get("schema_version") == "nwdp_boundary_pilot_geometry_materialization_plan.v1", data)
    assert_pass("Geometry materialization planner is read-only", data.get("mode") == "READ_ONLY_GEOMETRY_MATERIALIZATION_PLAN", data)
    assert_pass("Geometry materialization attempts no DB writes", data.get("db_writes_attempted") is False, data)
    assert_pass("Geometry materialization writes no runtime tables", data.get("runtime_tables_written") is False, data)
    assert_pass("Geometry materialization keeps runtime matching disabled", data.get("runtime_spatial_matching_changed") is False, data)
    assert_pass("Geometry materialization keeps Android unchanged", data.get("android_behavior_changed") is False, data)

    summary = data.get("summary") or {}
    assert_pass("Geometry materialization sees 10 payloads", summary.get("geometry_payload_available_count") == 10, summary)
    assert_pass("Geometry materialization does not update staging now", summary.get("staging_rows_to_update_now") == 0, summary)
    assert_pass("Geometry materialization does not write runtime rows now", summary.get("runtime_rows_to_write_now") == 0, summary)
    assert_pass("Geometry materialization requires separate apply checkpoint", summary.get("requires_separate_apply_checkpoint") is True, summary)

    items = data.get("items") or []
    assert_pass("Geometry materialization returns 10 items", len(items) == 10, items)
    assert_pass("All pilot geometry payloads are available", all(item["geometry_payload_available"] is True for item in items), items)
    assert_pass("All materialized hashes are present", all(item.get("materialized_source_geometry_hash") for item in items), items)
    assert_pass("All transformed bboxes are healthy", all(item["materialized_transformed_bbox"].get("healthy") is True for item in items), items)
    assert_pass("All staging updates are blocked", all(item["staging_update_allowed_now"] is False for item in items), items)
    assert_pass("All runtime writes are blocked", all(item["runtime_write_allowed_now"] is False for item in items), items)

    print("=" * 72)
    print("NWDP BOUNDARY PILOT GEOMETRY MATERIALIZATION PLAN REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
