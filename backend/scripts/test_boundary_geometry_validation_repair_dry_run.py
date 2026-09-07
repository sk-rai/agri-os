#!/usr/bin/env python3
"""Regression for the boundary geometry validation/repair dry-run."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "report_boundary_geometry_validation_repair_dry_run.py"
)
SOURCE = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/"
    "20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)
OUT_DIR = Path(
    "/tmp/boundary-geometry-validation-repair-dry-run-regression"
)
JSON_PATH = (
    OUT_DIR
    / "andaman_and_nicobar_islands_"
    "geometry_validation_repair_dry_run.json"
)
CSV_PATH = (
    OUT_DIR
    / "andaman_and_nicobar_islands_"
    "geometry_validation_repair_samples.csv"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def check(condition: bool, label: str, detail: Any = None) -> None:
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str))
        return

    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, default=str))
    raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("BOUNDARY GEOMETRY VALIDATION REPAIR DRY-RUN REGRESSION")
    print("=" * 72)

    check(SCRIPT.is_file(), "Dry-run report script exists", str(SCRIPT))
    check(SOURCE.is_file(), "Andaman source GeoJSON exists", str(SOURCE))

    source_hash_before = digest(SOURCE)
    source_mtime_before = SOURCE.stat().st_mtime_ns

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-slug",
            "andaman_and_nicobar_islands",
            "--output-dir",
            str(OUT_DIR),
            "--sample-limit",
            "50",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )

    print(proc.stdout)

    check(
        proc.returncode == 0,
        "Dry-run report exits zero",
        {
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
        },
    )
    check(JSON_PATH.is_file(), "Dry-run writes JSON", str(JSON_PATH))
    check(CSV_PATH.is_file(), "Dry-run writes CSV", str(CSV_PATH))

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    summary = data["summary"]
    classifications = data["classification_counts"]
    readiness = data["readiness"]
    guardrails = data["guardrails"]

    check(
        data["schema_version"]
        == "boundary_geometry_validation_repair_dry_run.v1",
        "Schema version is stable",
        data["schema_version"],
    )
    check(
        data["mode"]
        == "READ_ONLY_GEOMETRY_VALIDATION_REPAIR_DRY_RUN",
        "Mode is read-only dry-run",
        data["mode"],
    )
    check(data["healthy"] is True, "Andaman dry-run is healthy")

    check(
        summary["feature_count"] == 669,
        "Andaman feature count is stable",
        summary,
    )
    check(
        summary["source_valid_count"] == 660,
        "Already-valid geometry count is stable",
        summary,
    )
    check(
        summary["source_invalid_count"] == 9,
        "Confirmed invalid geometry count is stable",
        summary,
    )
    check(
        summary["repair_attempted_in_memory_count"] == 9,
        "Nine repairs are attempted only in memory",
        summary,
    )
    check(
        summary["repairable_make_valid_count"] == 9,
        "All confirmed invalid geometries are safely repairable",
        summary,
    )
    check(
        summary["manual_review_count"] == 0,
        "No Andaman geometry requires manual repair review",
        summary,
    )
    check(
        summary["reimport_or_crs_review_count"] == 0,
        "No Andaman geometry requires reimport or CRS review",
        summary,
    )
    check(
        summary["transformed_valid_count"] == 669,
        "All transformed geometries are valid",
        summary,
    )
    check(
        summary["transformed_inside_india_count"] == 669,
        "All transformed geometries are inside India bounds",
        summary,
    )

    check(
        classifications["VALIDATED_NO_REPAIR"] == 660,
        "No-repair classification count is stable",
        classifications,
    )
    check(
        classifications["REPAIRABLE_MAKE_VALID"] == 9,
        "Repairable classification count is stable",
        classifications,
    )

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))

    check(
        len(csv_rows) == 9,
        "CSV contains the nine repairable features",
        {"row_count": len(csv_rows)},
    )
    check(
        all(
            row["classification"] == "REPAIRABLE_MAKE_VALID"
            for row in csv_rows
        ),
        "CSV contains only repairable problem rows",
    )

    check(
        readiness["ready_for_admin_validation_review"] is True,
        "Admin validation review is ready",
        readiness,
    )
    check(
        readiness["ready_for_tiny_fixture_repair_design"] is True,
        "Tiny-fixture repair design is ready",
        readiness,
    )
    check(
        readiness["ready_for_broad_geometry_repair_apply"] is False,
        "Broad geometry repair remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_selected_runtime_promotion_apply"] is False,
        "Selected runtime promotion remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_runtime_lookup_enablement"] is False,
        "Runtime lookup remains disabled",
        readiness,
    )
    check(
        readiness["ready_for_android_behavior_change"] is False,
        "Android behavior remains unchanged",
        readiness,
    )

    required_false_guardrails = [
        "db_writes_attempted",
        "source_files_changed",
        "source_features_changed",
        "geometry_repair_persisted",
        "geometry_validation_status_changed",
        "source_runtime_eligibility_changed",
        "boundary_candidates_promoted",
        "boundary_candidates_activated",
        "runtime_tables_written",
        "runtime_lookup_enabled",
        "android_behavior_changed",
        "lgd_geography_overwritten",
    ]

    for key in required_false_guardrails:
        check(
            guardrails[key] is False,
            f"Guardrail remains false: {key}",
            guardrails,
        )

    check(
        digest(SOURCE) == source_hash_before,
        "Source GeoJSON checksum is unchanged",
        source_hash_before,
    )
    check(
        SOURCE.stat().st_mtime_ns == source_mtime_before,
        "Source GeoJSON modification time is unchanged",
    )

    script_text = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden_sql = [
        "insert into geography_",
        "update geography_",
        "delete from geography_",
        "truncate geography_",
    ]

    check(
        not any(token in script_text for token in forbidden_sql),
        "Dry-run contains no geography mutation SQL",
        forbidden_sql,
    )

    print("=" * 72)
    print(
        "BOUNDARY GEOMETRY VALIDATION REPAIR "
        "DRY-RUN REGRESSION PASSED"
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
