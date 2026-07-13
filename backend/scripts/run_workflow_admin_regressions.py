"""Run workflow/admin regression scripts.

Use this before deeper admin workflow-builder or import/export changes. The
suite focuses on versioned workflow safety: drafts, publishing, project
enablements, overrides, safe-edit lifecycle, legacy pinning, and crop-cycle
version assignment.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent

REGRESSION_SCRIPTS = [
    "test_workflow_csv_export.py",
    "test_workflow_csv_validation.py",
    "test_project_edit_policy.py",
    "test_project_workflow_enablements.py",
    "test_project_workflow_overrides.py",
    "test_workflow_version_assignment.py",
    "test_workflow_publish_safeguards.py",
    "test_workflow_draft_clone.py",
    "test_workflow_legacy_cycle_pins.py",
    "test_workflow_catalog_single_active.py",
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
    print("WORKFLOW ADMIN REGRESSION SUITE")
    print("=" * 80)
    for script_name in REGRESSION_SCRIPTS:
        run_script(script_name)

    print()
    print("=" * 80)
    print("Workflow admin regressions passed")
    print("=" * 80)


if __name__ == "__main__":
    main()
