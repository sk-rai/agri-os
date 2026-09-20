#!/usr/bin/env python3
"""Regression for pinned NWDP runtime geometry reconstruction."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = (
    ROOT
    / "backend/scripts/"
    / "assess_nwdp_runtime_geometry_reuse.py"
)
RAW = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/"
    / "20260824T110250Z/karnataka.geojson"
)


def assert_pass(
    name: str,
    condition: bool,
    payload=None,
) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(
                payload,
                indent=2,
                default=str,
            )[:3000])
        raise SystemExit(1)

    print(f"PASS {name}")


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="nwdp-runtime-geometry-reuse-",
    ) as directory:
        output = Path(directory) / "assessment.json"
        extracted = Path(directory) / "fixture.geojson"

        environment = dict(os.environ)
        environment.update({
            "PYTHONPATH": str(ROOT / "backend"),
            "RAW": str(RAW),
            "OUT_JSON": str(output),
            "EXTRACTED": str(extracted),
        })

        proc = subprocess.run(
            [str(PYTHON), str(SCRIPT)],
            cwd=str(ROOT),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        assert_pass(
            "Assessment exits zero",
            proc.returncode == 0,
            proc.stdout,
        )
        assert_pass(
            "Assessment output is written",
            output.exists(),
        )
        assert_pass(
            "Extracted fixture is written",
            extracted.exists(),
        )

        data = json.loads(
            output.read_text(encoding="utf-8")
        )
        fixture = json.loads(
            extracted.read_text(encoding="utf-8")
        )

        checks = data.get("checks") or {}
        decisions = data.get("reuse_decision") or {}
        lineage = data.get("source_lineage") or {}
        algorithms = (
            lineage.get("geometry_hash_algorithms")
            or {}
        )
        guardrails = data.get("guardrails") or {}
        rows = data.get("rows") or []
        features = fixture.get("features") or []

        assert_pass(
            "Assessment is healthy",
            data.get("healthy") is True,
            data,
        )
        assert_pass(
            "Assessment schema is stable",
            data.get("schema_version")
            == (
                "nwdp_runtime_geometry_"
                "reconstruction_assessment.v1"
            ),
            data,
        )
        assert_pass(
            "Assessment remains read-only",
            data.get("mode")
            == "READ_ONLY_PINNED_SOURCE_RECONSTRUCTION",
            data,
        )
        assert_pass(
            "Every reconstruction check passes",
            bool(checks)
            and all(checks.values()),
            checks,
        )
        assert_pass(
            "Both source checksums match",
            checks.get(
                "runtime_archive_lineage_checksum_matches"
            ) is True
            and checks.get(
                "normalized_geojson_checksum_matches"
            ) is True,
            lineage,
        )
        assert_pass(
            "Cross-format hashes are not compared",
            algorithms.get(
                "cross_format_equality_expected"
            ) is False
            and checks.get(
                "cross_format_hashes_not_compared"
            ) is True,
            algorithms,
        )
        assert_pass(
            "Exactly ten links are reconstructed",
            len(rows) == 10
            and len(features) == 10,
            data.get("summary"),
        )
        assert_pass(
            "All reconstructed geometries are valid",
            all(
                row.get("geometry_valid") is True
                and row.get("geometry_empty") is False
                and row.get(
                    "village_identity_matches"
                ) is True
                for row in rows
            ),
            rows,
        )
        assert_pass(
            "Both geometry hashes are retained",
            all(
                bool(row.get(
                    "runtime_archive_shape_hash"
                ))
                and bool(row.get(
                    "normalized_geojson_geometry_hash"
                ))
                and (
                    row.get("hash_comparison") or {}
                ).get("comparable") is False
                for row in rows
            ),
            rows,
        )
        assert_pass(
            "Tiny read-only preview is ready",
            decisions.get(
                "read_only_tiny_lookup_preview_ready"
            ) is True,
            decisions,
        )
        assert_pass(
            "Production lookup remains unavailable",
            decisions.get(
                "production_lookup_ready"
            ) is False
            and decisions.get(
                "production_runtime_geometry_column_ready"
            ) is False,
            decisions,
        )
        assert_pass(
            "Every no-write guardrail is preserved",
            bool(guardrails)
            and all(
                value is False
                for value in guardrails.values()
            ),
            guardrails,
        )

    print()
    print(
        "# NWDP RUNTIME GEOMETRY "
        "REUSE REGRESSION PASSED"
    )


if __name__ == "__main__":
    main()
