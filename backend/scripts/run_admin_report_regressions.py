"""Run lightweight admin report regression scripts.

This keeps read-only admin/reporting endpoint checks grouped separately from
permission enforcement checks. Use it after changing report contracts,
dashboard data, traceability payloads, or admin analytics screens.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent

REGRESSION_SCRIPTS = [
    "test_activity_usage_report.py",
    "test_system_readiness_report.py",
    "test_project_enrollment_report.py",
]


def run_script(script_name: str) -> None:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Regression script not found: {script_path}")

    print()
    print("=" * 80)
    print(f"Running {script_name}")
    print("=" * 80)

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BACKEND_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    print("=" * 80)
    print("ADMIN REPORT REGRESSION SUITE")
    print("=" * 80)
    for script_name in REGRESSION_SCRIPTS:
        run_script(script_name)

    print()
    print("=" * 80)
    print("Admin report regressions passed")
    print("=" * 80)


if __name__ == "__main__":
    main()
