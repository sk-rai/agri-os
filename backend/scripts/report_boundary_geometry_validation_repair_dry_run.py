#!/usr/bin/env python3
"""Read-only NWDP boundary geometry validation and repair dry-run.

Reads one state GeoJSON at a time, validates source and transformed geometry,
and tests Shapely make_valid() in memory. It never writes to the database,
runtime tables, source features, boundary candidates, or Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry
from shapely.validation import explain_validity


SCHEMA_VERSION = "boundary_geometry_validation_repair_dry_run.v1"
DEFAULT_RAW_DIR = Path(
    "data/raw/nwdp_boundary_all_state/20260824T110250Z"
)
DEFAULT_OUTPUT_DIR = Path(
    "/tmp/boundary-geometry-validation-repair-dry-run"
)
DEFAULT_SOURCE_CRS = "EPSG:7755"
TARGET_CRS = "EPSG:4326"

POLYGONAL_TYPES = {"Polygon", "MultiPolygon"}

# Deliberately generous national bounds, including island territories.
INDIA_LON_MIN = 66.0
INDIA_LON_MAX = 99.0
INDIA_LAT_MIN = 5.0
INDIA_LAT_MAX = 38.5

MAX_SAFE_RELATIVE_AREA_CHANGE = 0.000001


def json_default(value: Any) -> str:
    return str(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crs_name(payload: dict[str, Any]) -> str:
    crs = payload.get("crs") or {}
    properties = crs.get("properties") or {}
    name = str(properties.get("name") or "").strip()

    if "EPSG::" in name:
        return "EPSG:" + name.rsplit("EPSG::", 1)[1]

    if name:
        return name

    return DEFAULT_SOURCE_CRS


def source_vlcode(properties: dict[str, Any]) -> str | None:
    for key in (
        "VLCODE",
        "vlcode",
        "village_lgd_code",
        "VILLAGE_LGD_CODE",
        "village_code",
    ):
        value = properties.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def source_name(properties: dict[str, Any]) -> str | None:
    for key in (
        "VILLAGE",
        "village",
        "village_name",
        "VILLAGE_NAME",
        "NAME",
        "name",
    ):
        value = properties.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def bounds_inside_india(bounds: tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return (
        INDIA_LON_MIN <= min_x <= INDIA_LON_MAX
        and INDIA_LON_MIN <= max_x <= INDIA_LON_MAX
        and INDIA_LAT_MIN <= min_y <= INDIA_LAT_MAX
        and INDIA_LAT_MIN <= max_y <= INDIA_LAT_MAX
    )


def classify_feature(
    index: int,
    feature: dict[str, Any],
    transformer: Transformer,
) -> dict[str, Any]:
    properties = feature.get("properties") or {}

    row: dict[str, Any] = {
        "source_feature_index": index,
        "source_vlcode": source_vlcode(properties),
        "source_village_name": source_name(properties),
        "source_geometry_type": None,
        "source_valid": False,
        "source_validity_reason": None,
        "repair_attempted_in_memory": False,
        "repair_output_type": None,
        "repair_output_valid": False,
        "relative_area_change": None,
        "transformed_geometry_type": None,
        "transformed_valid": False,
        "transformed_bounds": None,
        "transformed_bounds_inside_india": False,
        "classification": None,
        "recommended_action": None,
        "error": None,
    }

    try:
        geometry_value = feature.get("geometry")
        if not geometry_value:
            row["classification"] = "REIMPORT_REQUIRED_MISSING_GEOMETRY"
            row["recommended_action"] = (
                "Reimport the source feature because geometry is missing."
            )
            return row

        geometry = shape(geometry_value)
        row["source_geometry_type"] = geometry.geom_type

        if geometry.is_empty:
            row["classification"] = "REIMPORT_REQUIRED_EMPTY_GEOMETRY"
            row["recommended_action"] = (
                "Reimport or manually reconstruct the empty geometry."
            )
            return row

        row["source_valid"] = bool(geometry.is_valid)
        row["source_validity_reason"] = explain_validity(geometry)

        candidate = geometry

        if not geometry.is_valid:
            row["repair_attempted_in_memory"] = True
            repaired = make_valid(geometry)
            row["repair_output_type"] = repaired.geom_type
            row["repair_output_valid"] = bool(repaired.is_valid)

            before_area = float(geometry.area)
            after_area = float(repaired.area)

            if before_area > 0:
                row["relative_area_change"] = abs(
                    after_area - before_area
                ) / before_area

            if (
                not repaired.is_valid
                or repaired.is_empty
                or repaired.geom_type not in POLYGONAL_TYPES
            ):
                row["classification"] = (
                    "MANUAL_REVIEW_UNSAFE_REPAIR_OUTPUT"
                )
                row["recommended_action"] = (
                    "Review manually; make_valid did not produce a safe "
                    "polygonal output."
                )
                return row

            if (
                row["relative_area_change"] is not None
                and row["relative_area_change"]
                > MAX_SAFE_RELATIVE_AREA_CHANGE
            ):
                row["classification"] = (
                    "MANUAL_REVIEW_MATERIAL_AREA_CHANGE"
                )
                row["recommended_action"] = (
                    "Review manually because repair materially changed area."
                )
                return row

            candidate = repaired

        transformed = transform_geometry(
            transformer.transform,
            candidate,
        )

        row["transformed_geometry_type"] = transformed.geom_type
        row["transformed_valid"] = bool(transformed.is_valid)
        row["transformed_bounds"] = [
            round(float(value), 8)
            for value in transformed.bounds
        ]
        row["transformed_bounds_inside_india"] = bounds_inside_india(
            transformed.bounds
        )

        if not transformed.is_valid:
            row["classification"] = (
                "MANUAL_REVIEW_INVALID_AFTER_TRANSFORM"
            )
            row["recommended_action"] = (
                "Review CRS transformation and transformed topology."
            )
        elif transformed.geom_type not in POLYGONAL_TYPES:
            row["classification"] = (
                "MANUAL_REVIEW_NON_POLYGONAL_TRANSFORM"
            )
            row["recommended_action"] = (
                "Review because transformed output is not polygonal."
            )
        elif not row["transformed_bounds_inside_india"]:
            row["classification"] = (
                "REIMPORT_OR_CRS_REVIEW_OUTSIDE_INDIA"
            )
            row["recommended_action"] = (
                "Verify source CRS and reimport policy."
            )
        elif geometry.is_valid:
            row["classification"] = "VALIDATED_NO_REPAIR"
            row["recommended_action"] = (
                "Record validation metadata through a separately guarded "
                "apply workflow."
            )
        else:
            row["classification"] = "REPAIRABLE_MAKE_VALID"
            row["recommended_action"] = (
                "Eligible for a separately reviewed tiny-fixture repair "
                "apply; do not enable runtime automatically."
            )

    except Exception as exc:
        row["classification"] = "REIMPORT_OR_MANUAL_REVIEW_PARSE_ERROR"
        row["recommended_action"] = (
            "Inspect the source feature and reimport or review manually."
        )
        row["error"] = f"{type(exc).__name__}: {exc}"

    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "source_feature_index",
        "source_vlcode",
        "source_village_name",
        "source_geometry_type",
        "source_valid",
        "source_validity_reason",
        "repair_attempted_in_memory",
        "repair_output_type",
        "repair_output_valid",
        "relative_area_change",
        "transformed_geometry_type",
        "transformed_valid",
        "transformed_bounds",
        "transformed_bounds_inside_india",
        "classification",
        "recommended_action",
        "error",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        for row in rows:
            output = dict(row)
            output["transformed_bounds"] = json.dumps(
                output.get("transformed_bounds")
            )
            writer.writerow(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-slug", required=True)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--sample-limit", type=int, default=100)
    args = parser.parse_args()

    input_path = args.raw_dir / f"{args.state_slug}.geojson"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_path = (
        args.output_dir
        / f"{args.state_slug}_geometry_validation_repair_dry_run.json"
    )
    csv_path = (
        args.output_dir
        / f"{args.state_slug}_geometry_validation_repair_samples.csv"
    )

    if not input_path.is_file():
        result = {
            "schema_version": SCHEMA_VERSION,
            "healthy": False,
            "error": "SOURCE_GEOJSON_NOT_FOUND",
            "input": str(input_path),
        }
        json_path.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 1

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    features = payload.get("features") or []

    source_crs_value = crs_name(payload)
    source_crs = CRS.from_user_input(source_crs_value)
    target_crs = CRS.from_user_input(TARGET_CRS)
    transformer = Transformer.from_crs(
        source_crs,
        target_crs,
        always_xy=True,
    )

    rows = [
        classify_feature(index, feature, transformer)
        for index, feature in enumerate(features)
    ]

    classification_counts = Counter(
        row["classification"] for row in rows
    )
    validity_reasons = Counter(
        row["source_validity_reason"]
        for row in rows
        if not row["source_valid"]
        and row["source_validity_reason"]
    )
    source_types = Counter(
        row["source_geometry_type"]
        for row in rows
        if row["source_geometry_type"]
    )
    repair_output_types = Counter(
        row["repair_output_type"]
        for row in rows
        if row["repair_output_type"]
    )

    problem_rows = [
        row
        for row in rows
        if row["classification"] != "VALIDATED_NO_REPAIR"
    ]

    summary = {
        "feature_count": len(rows),
        "source_valid_count": sum(
            row["source_valid"] for row in rows
        ),
        "source_invalid_count": sum(
            not row["source_valid"] for row in rows
        ),
        "repair_attempted_in_memory_count": sum(
            row["repair_attempted_in_memory"] for row in rows
        ),
        "repairable_make_valid_count": classification_counts[
            "REPAIRABLE_MAKE_VALID"
        ],
        "manual_review_count": sum(
            count
            for key, count in classification_counts.items()
            if key.startswith("MANUAL_REVIEW")
        ),
        "reimport_or_crs_review_count": sum(
            count
            for key, count in classification_counts.items()
            if key.startswith("REIMPORT")
        ),
        "transformed_valid_count": sum(
            row["transformed_valid"] for row in rows
        ),
        "transformed_inside_india_count": sum(
            row["transformed_bounds_inside_india"] for row in rows
        ),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": (
            len(rows) > 0
            and summary["manual_review_count"] == 0
            and summary["reimport_or_crs_review_count"] == 0
        ),
        "mode": "READ_ONLY_GEOMETRY_VALIDATION_REPAIR_DRY_RUN",
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "size_bytes": input_path.stat().st_size,
            "source_crs": source_crs.to_string(),
            "target_crs": target_crs.to_string(),
        },
        "summary": summary,
        "classification_counts": dict(classification_counts),
        "source_geometry_types": dict(source_types),
        "repair_output_types": dict(repair_output_types),
        "invalidity_reasons": dict(validity_reasons),
        "samples": problem_rows[: max(0, args.sample_limit)],
        "readiness": {
            "ready_for_admin_validation_review": True,
            "ready_for_tiny_fixture_repair_design": (
                summary["repairable_make_valid_count"] > 0
            ),
            "ready_for_broad_geometry_repair_apply": False,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "source_files_changed": False,
            "source_features_changed": False,
            "geometry_repair_persisted": False,
            "geometry_validation_status_changed": False,
            "source_runtime_eligibility_changed": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
        "output_files": {
            "json": str(json_path),
            "csv": str(csv_path),
        },
    }

    json_path.write_text(
        json.dumps(report, indent=2, default=json_default),
        encoding="utf-8",
    )
    write_csv(csv_path, problem_rows[: max(0, args.sample_limit)])

    print(json.dumps({
        "schema_version": report["schema_version"],
        "healthy": report["healthy"],
        "mode": report["mode"],
        "input": report["input"],
        "summary": report["summary"],
        "classification_counts": report["classification_counts"],
        "invalidity_reasons": report["invalidity_reasons"],
        "readiness": report["readiness"],
        "guardrails": report["guardrails"],
        "output_files": report["output_files"],
    }, indent=2, default=json_default))

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
