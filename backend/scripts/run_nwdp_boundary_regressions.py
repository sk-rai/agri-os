#!/usr/bin/env python3
"""Run NWDP boundary staging/admin regressions in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"

CHECKS = [
    ("verify inactive staging import", [str(PYTHON), "scripts/verify_nwdp_boundary_review_staging_import.py"]),
    ("admin read endpoints", [str(PYTHON), "scripts/test_nwdp_boundary_admin_read_endpoints.py"]),
    ("admin review endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_admin_review_endpoint.py"]),
    ("runtime tiny pilot apply", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_tiny_pilot_apply.py"]),
    ("runtime pilot inspection", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_pilot_inspection.py"]),
    ("runtime activation plan", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_activation_plan.py"]),
    ("all-state inactive staging import plan", [str(PYTHON), "scripts/test_nwdp_boundary_all_state_inactive_staging_import_plan.py"]),
    ("all-state inactive staging importer", [str(PYTHON), "scripts/test_nwdp_boundary_all_state_inactive_staging_importer.py"]),
]


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY REGRESSION RUNNER")
    print("=" * 72)

    for label, command in CHECKS:
        print(f"\n--- {label} ---")
        result = subprocess.run(command, cwd=BACKEND, text=True, capture_output=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"FAILED: {label}")
            return result.returncode

    print("=" * 72)
    print("NWDP BOUNDARY REGRESSION RUNNER PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
