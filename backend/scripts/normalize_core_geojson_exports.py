#!/usr/bin/env python3
"""Normalize CoRE Stack GeoJSON exports for overlay validation.

Google Earth Engine exported a few zone features as GeometryCollection. For the
overlay path we want polygon-only FeatureCollections. This script extracts
Polygon/MultiPolygon members from GeometryCollections, converts them to
MultiPolygon geometry, preserves properties, and writes derived files under:

    data/staged/core_stack/exports_normalized/

It never overwrites the original GEE exports and does not write database rows.
"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_EXPORT_DIR = ROOT / "data/staged/core_stack/exports"
NORMALIZED_EXPORT_DIR = ROOT / "data/staged/core_stack/exports_normalized"

EXPORTS = [
    {
        "layer_name": "Agro-Ecological Zone",
        "source_filename": "Agro_Ecological_Zones.geojson",
        "normalized_filename": "Agro_Ecological_Zones.normalized.geojson",
    },
    {
        "layer_name": "Agro-Climatic Zone",
        "source_filename": "Agro_Climatic_Zones.geojson",
        "normalized_filename": "Agro_Climatic_Zones.normalized.geojson",
    },
    {
        "layer_name": "Biogeographic Zone",
        "source_filename": "Biogeographic_Zone_pan_india.geojson",
        "normalized_filename": "Biogeographic_Zone_pan_india.normalized.geojson",
    },
]


def load_feature_collection(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    if not isinstance(data.get("features"), list):
        raise ValueError(f"{path} has no feature list")
    return data


def polygon_parts(geometry: dict[str, Any]) -> tuple[list[Any], list[str]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Polygon":
        return [coordinates], []
    if geometry_type == "MultiPolygon":
        return list(coordinates or []), []
    if geometry_type == "GeometryCollection":
        parts: list[Any] = []
        unsupported: list[str] = []
        for child in geometry.get("geometries") or []:
            child_parts, child_unsupported = polygon_parts(child)
            parts.extend(child_parts)
            unsupported.extend(child_unsupported)
        return parts, unsupported
    return [], [str(geometry_type)]


def normalize_geometry(geometry: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not geometry:
        return None, {"status": "empty_geometry"}

    geometry_type = geometry.get("type")
    if geometry_type in {"Polygon", "MultiPolygon"}:
        return geometry, {"status": "unchanged", "from_type": geometry_type, "to_type": geometry_type}

    parts, unsupported = polygon_parts(geometry)
    if geometry_type == "GeometryCollection" and parts:
        status = "converted_geometry_collection_to_multipolygon"
        if unsupported:
            status = "converted_geometry_collection_to_multipolygon_dropped_non_polygon_children"
        return (
            {"type": "MultiPolygon", "coordinates": parts},
            {
                "status": status,
                "from_type": geometry_type,
                "to_type": "MultiPolygon",
                "polygon_part_count": len(parts),
                "dropped_child_types": sorted(set(unsupported)),
            },
        )

    return (
        geometry,
        {
            "status": "unsupported_geometry_left_unchanged",
            "from_type": geometry_type,
            "unsupported_child_types": sorted(set(unsupported)),
            "polygon_part_count": len(parts),
        },
    )


def normalize_file(source_path: Path, output_path: Path) -> dict[str, Any]:
    data = load_feature_collection(source_path)
    normalized = deepcopy(data)
    before_types = Counter()
    after_types = Counter()
    conversion_counts = Counter()
    unsupported_features = []

    for index, feature in enumerate(normalized["features"]):
        geometry = feature.get("geometry")
        before_types[(geometry or {}).get("type")] += 1
        new_geometry, status = normalize_geometry(geometry)
        feature["geometry"] = new_geometry
        after_types[(new_geometry or {}).get("type")] += 1
        conversion_counts[status["status"]] += 1
        if status["status"] == "unsupported_geometry_left_unchanged":
            unsupported_features.append({"feature_index": index, **status})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")))

    return {
        "source_path": str(source_path),
        "output_path": str(output_path),
        "source_size_bytes": source_path.stat().st_size,
        "output_size_bytes": output_path.stat().st_size,
        "feature_count": len(normalized["features"]),
        "geometry_types_before": dict(sorted(before_types.items())),
        "geometry_types_after": dict(sorted(after_types.items())),
        "conversion_counts": dict(sorted(conversion_counts.items())),
        "unsupported_features": unsupported_features,
        "ready_for_polygon_only_validation": not unsupported_features
        and set(after_types).issubset({"Polygon", "MultiPolygon"}),
    }


def main() -> int:
    results = []
    missing_sources = []
    for export in EXPORTS:
        source_path = RAW_EXPORT_DIR / export["source_filename"]
        output_path = NORMALIZED_EXPORT_DIR / export["normalized_filename"]
        if not source_path.exists():
            missing_sources.append(str(source_path))
            results.append(
                {
                    "layer_name": export["layer_name"],
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "status": "missing_source",
                }
            )
            continue
        result = normalize_file(source_path, output_path)
        result["layer_name"] = export["layer_name"]
        result["status"] = "normalized"
        results.append(result)

    summary = {
        "schema_version": "core_geojson_normalization_result.v1",
        "mode": "WRITE_NORMALIZED_DERIVED_FILES",
        "external_calls_made": False,
        "db_writes_made": False,
        "raw_export_dir": str(RAW_EXPORT_DIR),
        "normalized_export_dir": str(NORMALIZED_EXPORT_DIR),
        "results": results,
        "missing_sources": missing_sources,
        "readiness": {
            "all_sources_present": not missing_sources,
            "all_outputs_polygon_only": all(
                item.get("ready_for_polygon_only_validation") for item in results if item.get("status") == "normalized"
            )
            and not missing_sources,
        },
        "next_actions": [
            "Run scripts/validate_core_lgd_overlay_inputs.py after normalization.",
            "Stage reviewed LGD-compatible boundary geometry under data/staged/boundaries/.",
            "Do not commit raw or normalized GeoJSON exports unless explicitly approved.",
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["readiness"]["all_outputs_polygon_only"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
