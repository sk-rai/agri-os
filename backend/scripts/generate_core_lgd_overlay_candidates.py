#!/usr/bin/env python3
"""Generate dry-run CoRE polygon to LGD district overlay candidates.

This script writes local staged candidate files only. It does not write database
rows and does not call external services.

The actual polygon intersection requires shapely. If shapely is not installed,
the script exits cleanly with a dependency report instead of attempting a weak
geometry approximation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_CORE_EXPORT_DIR = ROOT / "data/staged/core_stack/exports_normalized"
BOUNDARY_FILE = ROOT / "data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson"
OUTPUT_DIR = ROOT / "data/staged/core_stack/overlay_candidates"

CORE_LAYERS = [
    {
        "layer_name": "Agro-Ecological Zone",
        "region_system": "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
        "class_property": "physio_reg",
        "path": NORMALIZED_CORE_EXPORT_DIR / "Agro_Ecological_Zones.normalized.geojson",
    },
    {
        "layer_name": "Agro-Climatic Zone",
        "region_system": "CORE_STACK_AGRO_CLIMATIC_ZONE",
        "class_property": "regionname",
        "path": NORMALIZED_CORE_EXPORT_DIR / "Agro_Climatic_Zones.normalized.geojson",
    },
    {
        "layer_name": "Biogeographic Zone",
        "region_system": "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        "class_property": "biogeozone",
        "path": NORMALIZED_CORE_EXPORT_DIR / "Biogeographic_Zone_pan_india.normalized.geojson",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-districts", type=int, default=None, help="Optional smoke-test limit.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def dependency_error() -> dict[str, Any] | None:
    try:
        import shapely  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - report exact import failure
        return {
            "schema_version": "core_lgd_overlay_candidate_generation.v1",
            "mode": "DRY_RUN_CANDIDATE_GENERATION",
            "external_calls_made": False,
            "db_writes_made": False,
            "candidate_files_written": False,
            "dependency_ready": False,
            "missing_dependency": "shapely",
            "error": str(exc),
            "next_actions": [
                "Add/install shapely intentionally before running polygon intersections.",
                "Do not substitute bbox-only overlap for district climate mapping.",
                "Re-run this script after shapely is available in the backend venv.",
            ],
        }
    return None


def load_geojson(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return data


def ensure_valid_geometry(geometry):
    if geometry.is_valid:
        return geometry
    repaired = geometry.buffer(0)
    return repaired if not repaired.is_empty else geometry


def load_core_features():
    from shapely.geometry import shape

    records = []
    for layer in CORE_LAYERS:
        data = load_geojson(layer["path"])
        for index, feature in enumerate(data["features"]):
            properties = feature.get("properties") or {}
            class_name = properties.get(layer["class_property"])
            geometry = ensure_valid_geometry(shape(feature.get("geometry")))
            if geometry.is_empty:
                continue
            records.append(
                {
                    "layer_name": layer["layer_name"],
                    "region_system": layer["region_system"],
                    "class_property": layer["class_property"],
                    "class_name": class_name,
                    "class_code": properties.get("regioncode")
                    or properties.get("ae_regcode")
                    or properties.get("zone_code")
                    or properties.get("prov_code")
                    or class_name,
                    "feature_index": index,
                    "geometry": geometry,
                    "properties": properties,
                }
            )
    return records


def load_districts(limit: int | None = None):
    from shapely.geometry import shape

    data = load_geojson(BOUNDARY_FILE)
    features = data["features"][:limit] if limit else data["features"]
    districts = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        geometry = ensure_valid_geometry(shape(feature.get("geometry")))
        if geometry.is_empty:
            continue
        districts.append(
            {
                "feature_index": index,
                "state_lgd_code": str(properties.get("state_lgd") or properties.get("stcode11") or ""),
                "state_name": properties.get("stname"),
                "district_lgd_code": str(properties.get("dist_lgd") or properties.get("dtcode11") or ""),
                "district_name": properties.get("dtname") or properties.get("Dist"),
                "geometry": geometry,
                "properties": properties,
            }
        )
    return districts


def dominant_overlap(district: dict[str, Any], core_features: list[dict[str, Any]], region_system: str):
    district_geometry = district["geometry"]
    district_area = district_geometry.area
    overlaps = []
    for core in core_features:
        if core["region_system"] != region_system:
            continue
        if not district_geometry.intersects(core["geometry"]):
            continue
        intersection = district_geometry.intersection(core["geometry"])
        if intersection.is_empty:
            continue
        area = intersection.area
        if area <= 0:
            continue
        overlaps.append(
            {
                "region_system": region_system,
                "region_class_name": core["class_name"],
                "region_class_code": str(core["class_code"]),
                "core_feature_index": core["feature_index"],
                "overlap_area_degrees2": area,
                "overlap_percent_of_district": (area / district_area * 100) if district_area else 0,
            }
        )
    overlaps.sort(key=lambda row: row["overlap_area_degrees2"], reverse=True)
    return overlaps[0] if overlaps else None


def candidate_rows(districts, core_features):
    rows = []
    for district in districts:
        for layer in CORE_LAYERS:
            best = dominant_overlap(district, core_features, layer["region_system"])
            if not best:
                rows.append(
                    {
                        "state_lgd_code": district["state_lgd_code"],
                        "state_name": district["state_name"],
                        "district_lgd_code": district["district_lgd_code"],
                        "district_name": district["district_name"],
                        "scope_level": "DISTRICT",
                        "region_system": layer["region_system"],
                        "candidate_status": "NO_OVERLAP_FOUND",
                        "review_status": "MANUAL_REVIEW",
                    }
                )
                continue
            rows.append(
                {
                    "state_lgd_code": district["state_lgd_code"],
                    "state_name": district["state_name"],
                    "district_lgd_code": district["district_lgd_code"],
                    "district_name": district["district_name"],
                    "scope_level": "DISTRICT",
                    "region_system": layer["region_system"],
                    "region_class_name": best["region_class_name"],
                    "region_class_code": best["region_class_code"],
                    "overlap_area_degrees2": round(best["overlap_area_degrees2"], 12),
                    "overlap_percent_of_district": round(best["overlap_percent_of_district"], 4),
                    "candidate_status": "DOMINANT_OVERLAP_CANDIDATE",
                    "confidence": "POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW",
                    "review_status": "MANUAL_REVIEW",
                }
            )
    return rows


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "district_core_overlay_candidates.json"
    csv_path = output_dir / "district_core_overlay_candidates.csv"

    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True))
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    args = parse_args()
    dep = dependency_error()
    if dep:
        print(json.dumps(dep, indent=2, sort_keys=True))
        return 1

    core_missing = [str(layer["path"]) for layer in CORE_LAYERS if not layer["path"].exists()]
    boundary_missing = not BOUNDARY_FILE.exists()
    if core_missing or boundary_missing:
        print(
            json.dumps(
                {
                    "schema_version": "core_lgd_overlay_candidate_generation.v1",
                    "mode": "DRY_RUN_CANDIDATE_GENERATION",
                    "external_calls_made": False,
                    "db_writes_made": False,
                    "candidate_files_written": False,
                    "dependency_ready": True,
                    "missing_core_files": core_missing,
                    "boundary_file_exists": not boundary_missing,
                    "boundary_file": str(BOUNDARY_FILE),
                    "readiness": {"ready_for_candidate_generation": False},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    core_features = load_core_features()
    districts = load_districts(limit=args.limit_districts)
    rows = candidate_rows(districts, core_features)
    outputs = write_outputs(rows, args.output_dir)
    no_overlap_count = sum(row["candidate_status"] == "NO_OVERLAP_FOUND" for row in rows)
    result = {
        "schema_version": "core_lgd_overlay_candidate_generation.v1",
        "mode": "DRY_RUN_CANDIDATE_GENERATION",
        "external_calls_made": False,
        "db_writes_made": False,
        "candidate_files_written": True,
        "dependency_ready": True,
        "output_files": outputs,
        "districts_seen": len(districts),
        "core_features_seen": len(core_features),
        "candidate_rows": len(rows),
        "no_overlap_count": no_overlap_count,
        "readiness": {
            "ready_for_candidate_generation": True,
            "candidates_generated": bool(rows),
            "manual_review_required": True,
            "ready_for_db_import": False,
        },
        "warnings": [
            "Area is calculated in source lon/lat coordinate units for dry-run ranking only.",
            "Rows remain MANUAL_REVIEW and must not be imported as authoritative without source/method review.",
            "This script intentionally does not write geography_climate_region_mappings.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if rows and no_overlap_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
