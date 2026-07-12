"""Run master-data/catalog regression scripts.

Use this suite before changing admin catalog screens, import/export flows,
crop taxonomy, agri input catalogs, product catalogs, or crop/input mapping
contracts. It intentionally groups the reusable reference-data layer apart
from workflow-versioning and report/dashboard suites.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent

REGRESSION_SCRIPTS = [
    "test_crop_catalog.py",
    "test_crop_taxonomy_csv.py",
    "test_crop_propagation_csv.py",
    "test_input_catalog.py",
    "test_input_catalog_csv.py",
    "test_input_catalog_lifecycle.py",
    "test_input_rules.py",
    "test_product_catalog.py",
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
    print("MASTER DATA REGRESSION SUITE")
    print("=" * 80)
    for script_name in REGRESSION_SCRIPTS:
        run_script(script_name)

    print()
    print("=" * 80)
    print("Master data regressions passed")
    print("=" * 80)


if __name__ == "__main__":
    main()
