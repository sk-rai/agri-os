#!/usr/bin/env python3
"""Run the backend regression sweep required before Android handoff."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REGRESSIONS = [
    ("Broadcast API", ["scripts/test_broadcast_api.py"]),
    ("Weather snapshots", ["scripts/test_weather_snapshots.py"]),
    ("Android profile payloads", ["scripts/test_android_profile_payloads.py"]),
    ("Profile hydration", ["scripts/test_profile_hydration.py"]),
    ("Profile form contracts", ["scripts/test_profile_form_contracts.py"]),
    ("Provider worker ops dry run", ["scripts/run_due_provider_workers.py", "--tenant-id", "default", "--dry-run"]),
    ("Alembic revision chain", ["scripts/check_alembic_revision_chain.py"]),
]


def run_regression(label: str, args: list[str]) -> None:
    print("\n" + "=" * 72)
    print(f"RUNNING: {label}")
    print("=" * 72)
    result = subprocess.run([sys.executable, *args], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {result.returncode}")


def main() -> None:
    print("=" * 72)
    print("ANDROID BACKEND CLOSEOUT REGRESSION SWEEP")
    print("=" * 72)
    for label, args in REGRESSIONS:
        run_regression(label, args)
    print("\n" + "=" * 72)
    print("All Android backend closeout regressions passed")
    print("=" * 72)


if __name__ == "__main__":
    main()
