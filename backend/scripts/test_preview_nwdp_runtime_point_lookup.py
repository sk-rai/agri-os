#!/usr/bin/env python3
"""Regression for the read-only 10-row runtime lookup preview."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
ASSESS = (
    ROOT
    / "backend/scripts/"
    / "assess_nwdp_runtime_geometry_reuse.py"
)
PREVIEW = (
    ROOT
    / "backend/scripts/"
    / "preview_nwdp_runtime_point_lookup.py"
)
RAW = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/"
    / "20260824T110250Z/karnataka.geojson"
)


def assert_pass(
    label: str,
    condition: bool,
    payload=None,
) -> None:
    if not condition:
        print(f"FAIL {label}")
        if payload is not None:
            print(json.dumps(
                payload,
                indent=2,
                default=str,
            )[:3000])
        raise SystemExit(1)
    print(f"PASS {label}")


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="nwdp-runtime-point-preview-",
    ) as directory:
        base = Path(directory)
        assessment = base / "assessment.json"
        fixture = base / "fixture.geojson"
        points = base / "points.geojson"
        output = base / "preview.json"

        environment = dict(os.environ)
        environment.update({
            "PYTHONPATH": str(ROOT / "backend"),
            "RAW": str(RAW),
            "OUT_JSON": str(assessment),
            "EXTRACTED": str(fixture),
        })

        assessment_proc = subprocess.run(
            [str(PYTHON), str(ASSESS)],
            cwd=str(ROOT),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert_pass(
            "Geometry assessment exits zero",
            assessment_proc.returncode == 0,
            assessment_proc.stdout,
        )

        fixture_data = json.loads(
            fixture.read_text(encoding="utf-8")
        )

        point_features = []
        expected_villages = {}

        for position, feature in enumerate(
            fixture_data["features"],
            start=1,
        ):
            representative = shape(
                feature["geometry"]
            ).representative_point()
            point_id = f"inside-{position:02d}"
            properties = feature["properties"]

            expected_villages[point_id] = (
                properties["village_lgd_code"]
            )
            point_features.append({
                "type": "Feature",
                "id": point_id,
                "properties": {
                    "point_id": point_id,
                    "expected_village_lgd_code":
                        properties["village_lgd_code"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        representative.x,
                        representative.y,
                    ],
                },
            })

        point_features.append({
            "type": "Feature",
            "id": "outside-01",
            "properties": {
                "point_id": "outside-01",
                "expected_village_lgd_code": None,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [77.5946, 12.9716],
            },
        })

        points.write_text(
            json.dumps({
                "type": "FeatureCollection",
                "features": point_features,
            }, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [
                str(PYTHON),
                str(PREVIEW),
                "--fixture",
                str(fixture),
                "--points",
                str(points),
                "--output",
                str(output),
            ],
            cwd=str(ROOT),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        assert_pass(
            "Point preview exits zero",
            proc.returncode == 0,
            proc.stdout,
        )
        assert_pass(
            "Point preview output is written",
            output.exists(),
        )

        data = json.loads(
            output.read_text(encoding="utf-8")
        )
        results = data.get("results") or []
        by_id = {
            row["point_id"]: row
            for row in results
        }

        assert_pass(
            "Preview is healthy",
            data.get("healthy") is True,
            data,
        )
        assert_pass(
            "Preview schema is stable",
            data.get("schema_version")
            == "nwdp_runtime_point_lookup_preview.v1",
            data,
        )
        assert_pass(
            "Preview remains read-only",
            data.get("mode")
            == "READ_ONLY_10_ROW_POINT_LOOKUP_PREVIEW",
            data,
        )
        assert_pass(
            "All preview checks pass",
            all((data.get("checks") or {}).values()),
            data.get("checks"),
        )
        assert_pass(
            "Ten interior points match exactly once",
            all(
                by_id[point_id]["status"] == "MATCHED"
                and by_id[point_id]["match_count"] == 1
                for point_id in expected_villages
            ),
            results,
        )
        assert_pass(
            "Interior points resolve expected villages",
            all(
                by_id[point_id]["matches"][0][
                    "village_lgd_code"
                ] == village_lgd_code
                for point_id, village_lgd_code
                in expected_villages.items()
            ),
            results,
        )
        assert_pass(
            "Outside point remains unmatched",
            by_id["outside-01"]["status"]
            == "UNMATCHED"
            and by_id["outside-01"]["match_count"] == 0,
            by_id["outside-01"],
        )
        assert_pass(
            "No point is ambiguous",
            data["summary"]["ambiguous_count"] == 0,
            data["summary"],
        )
        assert_pass(
            "Database counts remain unchanged",
            data["database_counts"]["unchanged"] is True,
            data["database_counts"],
        )
        assert_pass(
            "Every no-write guardrail is preserved",
            all(
                value is False
                for value
                in data["guardrails"].values()
            ),
            data["guardrails"],
        )
        assert_pass(
            "Production lookup remains disabled",
            data["readiness"][
                "production_lookup_enabled"
            ] is False
            and data["readiness"][
                "production_lookup_ready"
            ] is False,
            data["readiness"],
        )

    print()
    print(
        "# NWDP RUNTIME POINT LOOKUP "
        "PREVIEW REGRESSION PASSED"
    )


if __name__ == "__main__":
    main()
