#!/usr/bin/env python3
"""Regression checks for the explicitly gated throughput V2 planner."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = (
    ROOT
    / "backend/scripts"
    / "plan_boundary_geometry_validation_metadata_bounded_state.py"
)
RAW_DIR = (
    ROOT
    / "data/raw/nwdp_boundary_all_state"
    / "20260824T110250Z"
)


def run_limit(
    limit: int,
    *,
    throughput_v2: bool,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(
        prefix="validation-metadata-v2-planner-"
    ) as temporary:
        command = [
            sys.executable,
            str(PLANNER),
            "--state-slug",
            "uttar_pradesh",
            "--state-or-ut",
            "Uttar Pradesh",
            "--expected-source-sha256",
            "intentionally-wrong-checksum",
            "--cursor-after-index",
            "-1",
            "--limit",
            str(limit),
            "--output-dir",
            temporary,
            "--raw-dir",
            str(RAW_DIR),
        ]

        if throughput_v2:
            command.append("--throughput-v2")

        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )


def combined(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def main() -> int:
    v1_500 = run_limit(
        500,
        throughput_v2=False,
    )
    assert "between 1 and 500" not in combined(v1_500)
    assert "SOURCE_CHECKSUM_MISMATCH" in combined(v1_500)

    v1_501 = run_limit(
        501,
        throughput_v2=False,
    )
    assert v1_501.returncode != 0
    assert (
        "--limit must be between 1 and 500"
        in combined(v1_501)
    )

    v2_501 = run_limit(
        501,
        throughput_v2=True,
    )
    assert (
        "between 1 and 500"
        not in combined(v2_501)
    )
    assert "SOURCE_CHECKSUM_MISMATCH" in combined(v2_501)

    v2_25k = run_limit(
        25_000,
        throughput_v2=True,
    )
    assert (
        "between 1 and 50000"
        not in combined(v2_25k)
    )
    assert "SOURCE_CHECKSUM_MISMATCH" in combined(v2_25k)

    v2_50k = run_limit(
        50_000,
        throughput_v2=True,
    )
    assert (
        "between 1 and 50000"
        not in combined(v2_50k)
    )
    assert "SOURCE_CHECKSUM_MISMATCH" in combined(v2_50k)

    v2_50k_plus_one = run_limit(
        50_001,
        throughput_v2=True,
    )
    assert v2_50k_plus_one.returncode != 0
    assert (
        "--limit must be between 1 and 50000 "
        "in throughput V2 mode"
        in combined(v2_50k_plus_one)
    )

    print("PASS V1 planner retains the 500-row ceiling")
    print("PASS V2 planner accepts 501 through 50000 rows")
    print("PASS V2 planner rejects rows above 50000")
    print("PASS throughput mode remains explicit")
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "PLANNER REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
