#!/usr/bin/env python3
"""Compare CoRE/LGD overlay ranking with an India equal-area projection.

This is a dry-run review aid only. It reads staged CoRE GeoJSON exports,
LGD-compatible district boundaries, and the existing lon/lat candidate CSV.
It writes comparison files under data/staged and never writes database rows.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_CORE_EXPORT_DIR = ROOT / "data/staged/core_stack/exports_normalized"
BOUNDARY_FILE = ROOT / "data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson"
BASELINE_CSV = ROOT / "data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv"
OUTPUT_DIR = ROOT / "data/staged/core_stack/overlay_candidates/equal_area"

LOW_OVERLAP_THRESHOLD = 60.0
INDIA_ALBERS = "+proj=aea +lat_1=12 +lat_2=32 +lat_0=0 +lon_0=78 +datum=WGS84 +units=m +no_defs"

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
    parser.add_argument("--baseline-csv", type=Path, default=BASELINE_CSV)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--low-overlap-threshold", type=float, default=LOW_OVERLAP_THRESHOLD)
    return parser.parse_args()


def dependency_error() -> dict[str, Any] | None:
    missing = []
    for dependency in ("shapely", "pyproj"):
        try:
            __import__(dependency)
        except Exception as exc:  # noqa: BLE001 - report exact import failure
            missing.append({"dependency": dependency, "error": str(exc)})
    if not missing:
        return None
    return {
        "schema_version": "core_lgd_overlay_equal_area_comparison.v1",
        "mode": "DRY_RUN_EQUAL_AREA_COMPARISON",
        "external_calls_made": False,
        "db_writes_made": False,
        "comparison_files_written": False,
        "dependency_ready": False,
        "missing_dependencies": missing,
        "next_actions": [
            "Install pinned shapely/pyproj dependencies in the backend venv.",
            "Re-run this script after dependencies are available.",
            "Do not import polygon-derived mappings until equal-area comparison is reviewed.",
        ],
    }


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


def comparison_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("state_lgd_code") or ""),
        str(row.get("district_lgd_code") or ""),
        str(row.get("district_name") or ""),
        str(row.get("region_system") or ""),
    )


def read_baseline_rows(path: Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.setdefault(comparison_key(row), row)
    return rows


def load_projector():
    from pyproj import CRS, Transformer
    from shapely.ops import transform

    source = CRS.from_epsg(4326)
    target = CRS.from_proj4(INDIA_ALBERS)
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return lambda geometry: transform(transformer.transform, geometry)


def class_code(properties: dict[str, Any], class_name: Any) -> str:
    value = (
        properties.get("regioncode")
        or properties.get("ae_regcode")
        or properties.get("zone_code")
        or properties.get("prov_code")
        or class_name
    )
    return str(value)


def load_core_features(project):
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
            geometry = ensure_valid_geometry(project(geometry))
            if geometry.is_empty:
                continue
            records.append(
                {
                    "layer_name": layer["layer_name"],
                    "region_system": layer["region_system"],
                    "class_property": layer["class_property"],
                    "region_class_name": class_name,
                    "region_class_code": class_code(properties, class_name),
                    "feature_index": index,
                    "geometry": geometry,
                }
            )
    return records


def load_districts(project, limit: int | None = None):
    from shapely.geometry import shape

    data = load_geojson(BOUNDARY_FILE)
    features = data["features"][:limit] if limit else data["features"]
    districts = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        geometry = ensure_valid_geometry(shape(feature.get("geometry")))
        if geometry.is_empty:
            continue
        geometry = ensure_valid_geometry(project(geometry))
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
            }
        )
    return districts


def dominant_equal_area_overlap(
    district: dict[str, Any],
    core_features: list[dict[str, Any]],
    region_system: str,
) -> dict[str, Any] | None:
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
                "region_class_name": core["region_class_name"],
                "region_class_code": core["region_class_code"],
                "core_feature_index": core["feature_index"],
                "equal_area_overlap_sqkm": area / 1_000_000,
                "equal_area_overlap_percent_of_district": (area / district_area * 100) if district_area else 0,
            }
        )
    overlaps.sort(key=lambda row: row["equal_area_overlap_sqkm"], reverse=True)
    return overlaps[0] if overlaps else None


def build_comparison_rows(
    districts,
    core_features,
    baseline_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for district in districts:
        for layer in CORE_LAYERS:
            region_system = layer["region_system"]
            best = dominant_equal_area_overlap(district, core_features, region_system)
            key = (
                district["state_lgd_code"],
                district["district_lgd_code"],
                str(district["district_name"] or ""),
                region_system,
            )
            baseline = baseline_by_key.get(key, {})
            baseline_name = baseline.get("region_class_name")
            equal_name = best.get("region_class_name") if best else None
            changed = bool(baseline_name and equal_name and baseline_name != equal_name)
            rows.append(
                {
                    "state_lgd_code": district["state_lgd_code"],
                    "state_name": district["state_name"],
                    "district_lgd_code": district["district_lgd_code"],
                    "district_name": district["district_name"],
                    "scope_level": "DISTRICT",
                    "region_system": region_system,
                    "baseline_region_class_name": baseline_name,
                    "baseline_region_class_code": baseline.get("region_class_code"),
                    "baseline_overlap_area_degrees2": baseline.get("overlap_area_degrees2"),
                    "baseline_overlap_percent_of_district": baseline.get("overlap_percent_of_district"),
                    "equal_area_region_class_name": equal_name,
                    "equal_area_region_class_code": best.get("region_class_code") if best else None,
                    "equal_area_overlap_sqkm": round(best["equal_area_overlap_sqkm"], 6) if best else None,
                    "equal_area_overlap_percent_of_district": round(best["equal_area_overlap_percent_of_district"], 4)
                    if best
                    else None,
                    "dominant_class_changed": changed,
                    "candidate_status": "DOMINANT_OVERLAP_CANDIDATE" if best else "NO_OVERLAP_FOUND",
                    "review_status": "MANUAL_REVIEW",
                }
            )
    return rows


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def summarize(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_region[row["region_system"]].append(row)

    summaries = {}
    for region_system, region_rows in sorted(by_region.items()):
        equal_overlaps = [as_float(row.get("equal_area_overlap_percent_of_district")) for row in region_rows]
        baseline_overlaps = [as_float(row.get("baseline_overlap_percent_of_district")) for row in region_rows]
        changed = [row for row in region_rows if row.get("dominant_class_changed")]
        low_equal = [row for row in region_rows if as_float(row.get("equal_area_overlap_percent_of_district")) < threshold]
        low_baseline = [row for row in region_rows if as_float(row.get("baseline_overlap_percent_of_district")) < threshold]
        summaries[region_system] = {
            "row_count": len(region_rows),
            "dominant_class_changed_count": len(changed),
            "baseline_low_overlap_count": len(low_baseline),
            "equal_area_low_overlap_count": len(low_equal),
            "baseline_min_overlap_percent": min(baseline_overlaps) if baseline_overlaps else None,
            "equal_area_min_overlap_percent": min(equal_overlaps) if equal_overlaps else None,
            "baseline_median_overlap_percent": median(baseline_overlaps) if baseline_overlaps else None,
            "equal_area_median_overlap_percent": median(equal_overlaps) if equal_overlaps else None,
            "changed_examples": [
                {
                    "state_name": row.get("state_name"),
                    "district_lgd_code": row.get("district_lgd_code"),
                    "district_name": row.get("district_name"),
                    "baseline_region_class_name": row.get("baseline_region_class_name"),
                    "equal_area_region_class_name": row.get("equal_area_region_class_name"),
                    "baseline_overlap_percent_of_district": row.get("baseline_overlap_percent_of_district"),
                    "equal_area_overlap_percent_of_district": row.get("equal_area_overlap_percent_of_district"),
                }
                for row in sorted(
                    changed,
                    key=lambda item: as_float(item.get("equal_area_overlap_percent_of_district")),
                )[:10]
            ],
            "lowest_equal_area_examples": [
                {
                    "state_name": row.get("state_name"),
                    "district_lgd_code": row.get("district_lgd_code"),
                    "district_name": row.get("district_name"),
                    "equal_area_region_class_name": row.get("equal_area_region_class_name"),
                    "equal_area_overlap_percent_of_district": row.get("equal_area_overlap_percent_of_district"),
                }
                for row in sorted(
                    low_equal,
                    key=lambda item: as_float(item.get("equal_area_overlap_percent_of_district")),
                )[:10]
            ],
        }
    return summaries


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "district_core_overlay_equal_area_comparison.json"
    csv_path = output_dir / "district_core_overlay_equal_area_comparison.csv"
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
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

    missing_inputs = [str(layer["path"]) for layer in CORE_LAYERS if not layer["path"].exists()]
    if not BOUNDARY_FILE.exists():
        missing_inputs.append(str(BOUNDARY_FILE))
    if not args.baseline_csv.exists():
        missing_inputs.append(str(args.baseline_csv))

    if missing_inputs:
        print(
            json.dumps(
                {
                    "schema_version": "core_lgd_overlay_equal_area_comparison.v1",
                    "mode": "DRY_RUN_EQUAL_AREA_COMPARISON",
                    "external_calls_made": False,
                    "db_writes_made": False,
                    "comparison_files_written": False,
                    "missing_inputs": missing_inputs,
                    "readiness": {"ready_for_equal_area_comparison": False},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    project = load_projector()
    core_features = load_core_features(project)
    districts = load_districts(project, args.limit_districts)
    baseline_by_key = read_baseline_rows(args.baseline_csv)
    rows = build_comparison_rows(districts, core_features, baseline_by_key)
    files = write_outputs(rows, args.output_dir)

    changed_count = sum(1 for row in rows if row.get("dominant_class_changed"))
    equal_low_count = sum(
        1 for row in rows if as_float(row.get("equal_area_overlap_percent_of_district")) < args.low_overlap_threshold
    )
    baseline_low_count = sum(
        1 for row in rows if as_float(row.get("baseline_overlap_percent_of_district")) < args.low_overlap_threshold
    )
    status_counts = Counter(row.get("candidate_status") for row in rows)
    review_counts = Counter(row.get("review_status") for row in rows)

    result = {
        "schema_version": "core_lgd_overlay_equal_area_comparison.v1",
        "mode": "DRY_RUN_EQUAL_AREA_COMPARISON",
        "projection": {
            "name": "India Albers equal-area",
            "proj4": INDIA_ALBERS,
            "units": "metres",
        },
        "external_calls_made": False,
        "db_writes_made": False,
        "comparison_files_written": True,
        "output_files": files,
        "baseline_candidate_csv": str(args.baseline_csv),
        "district_count": len(districts),
        "row_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "dominant_class_changed_count": changed_count,
        "baseline_low_overlap_count": baseline_low_count,
        "equal_area_low_overlap_count": equal_low_count,
        "region_system_summaries": summarize(rows, args.low_overlap_threshold),
        "readiness": {
            "ready_for_equal_area_manual_review": bool(rows),
            "dominant_classes_stable_under_equal_area": changed_count == 0,
            "ready_for_db_import": False,
        },
        "warnings": [
            "This is a dry-run comparison only; no database rows were written.",
            "All comparison rows remain MANUAL_REVIEW.",
            "BharatAtlas is acceptable for operational dry-run review, not marked as authoritative government source.",
            "Existing fallback rows should remain until polygon-derived rows are reviewed and intentionally imported.",
        ],
        "next_actions": [
            "Review any dominant-class changes and low-overlap rows.",
            "If equal-area changes are material, regenerate/import candidates from equal-area outputs only.",
            "Design importer to write MANUAL_REVIEW polygon-derived rows without replacing fallback mappings.",
            "Promote rows only after source/provenance, low-overlap, duplicate-code, and precedence review.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
