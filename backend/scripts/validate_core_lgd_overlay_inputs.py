#!/usr/bin/env python3
"""Dry-run validator for CoRE polygon and LGD boundary overlay inputs.

Read-only. This script inspects local staged files only:

- CoRE GeoJSON exports under data/staged/core_stack/exports/
- boundary candidates under data/staged/boundaries/

It does not call Google Earth Engine, does not download boundary data, and does
not write database rows.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CORE_EXPORT_DIR = ROOT / "data/staged/core_stack/exports"
NORMALIZED_CORE_EXPORT_DIR = ROOT / "data/staged/core_stack/exports_normalized"
BOUNDARY_DIR = ROOT / "data/staged/boundaries"

EXPECTED_CORE_EXPORTS = [
    {
        "layer_name": "Agro-Ecological Zone",
        "region_system": "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
        "class_property": "physio_reg",
        "expected_filename": "Agro_Ecological_Zones.geojson",
        "normalized_filename": "Agro_Ecological_Zones.normalized.geojson",
    },
    {
        "layer_name": "Agro-Climatic Zone",
        "region_system": "CORE_STACK_AGRO_CLIMATIC_ZONE",
        "class_property": "regionname",
        "expected_filename": "Agro_Climatic_Zones.geojson",
        "normalized_filename": "Agro_Climatic_Zones.normalized.geojson",
    },
    {
        "layer_name": "Biogeographic Zone",
        "region_system": "CORE_STACK_BIOGEOGRAPHIC_ZONE",
        "class_property": "biogeozone",
        "expected_filename": "Biogeographic_Zone_pan_india.geojson",
        "normalized_filename": "Biogeographic_Zone_pan_india.normalized.geojson",
    },
]

BOUNDARY_EXTENSIONS = {".geojson", ".json", ".shp"}
LGD_HINT_FIELDS = {
    "state": ["state_lgd_code", "state_code", "st_lgd", "stcode11", "state_lgd", "lgd_state_code"],
    "district": ["district_lgd_code", "district_code", "dt_lgd", "dtcode11", "dist_lgd", "lgd_district_code"],
    "block": ["block_lgd_code", "block_code", "subdistrict_code", "subdt_lgd", "lgd_block_code"],
    "village": ["village_lgd_code", "village_code", "vill_lgd", "lgd_village_code"],
}


def load_geojson(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - CLI validator reports failures
            return None, [f"unable_to_read_json: {exc}"]
    except Exception as exc:  # noqa: BLE001 - CLI validator reports failures
        return None, [f"unable_to_read_json: {exc}"]

    if not isinstance(data, dict):
        errors.append("root_is_not_object")
    elif data.get("type") != "FeatureCollection":
        errors.append(f"root_type_is_not_feature_collection: {data.get('type')}")

    return data if isinstance(data, dict) else None, errors


def iter_positions(geometry: Any):
    if isinstance(geometry, dict):
        coordinates = geometry.get("coordinates")
        yield from iter_positions(coordinates)
    elif isinstance(geometry, list):
        if (
            len(geometry) >= 2
            and isinstance(geometry[0], (int, float))
            and isinstance(geometry[1], (int, float))
        ):
            yield geometry
        else:
            for item in geometry:
                yield from iter_positions(item)


def bbox_from_features(features: list[dict[str, Any]]) -> dict[str, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for feature in features:
        for position in iter_positions(feature.get("geometry")):
            xs.append(float(position[0]))
            ys.append(float(position[1]))
    if not xs or not ys:
        return None
    return {
        "min_lng_or_x": min(xs),
        "min_lat_or_y": min(ys),
        "max_lng_or_x": max(xs),
        "max_lat_or_y": max(ys),
    }


def geojson_summary(path: Path, required_property: str | None = None) -> dict[str, Any]:
    data, load_errors = load_geojson(path)
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "readable": data is not None,
        "errors": load_errors,
    }
    if data is None:
        return result

    features = data.get("features") if isinstance(data.get("features"), list) else []
    geometry_types = Counter(
        (feature.get("geometry") or {}).get("type")
        for feature in features
        if isinstance(feature, dict)
    )
    property_keys = Counter()
    required_property_non_empty = 0
    empty_geometry_count = 0

    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not geometry:
            empty_geometry_count += 1
        properties = feature.get("properties") or {}
        if isinstance(properties, dict):
            property_keys.update(properties.keys())
            if required_property and properties.get(required_property) not in (None, ""):
                required_property_non_empty += 1

    invalid_geometry_types = sorted(
        geometry_type
        for geometry_type in geometry_types
        if geometry_type not in {"Polygon", "MultiPolygon"}
    )
    result.update(
        {
            "feature_count": len(features),
            "geometry_types": dict(sorted(geometry_types.items())),
            "invalid_geometry_types": invalid_geometry_types,
            "empty_geometry_count": empty_geometry_count,
            "bbox": bbox_from_features(features),
            "crs": data.get("crs") or "not_declared_geojson_default_wgs84_lon_lat",
            "sample_property_keys": sorted(property_keys)[:40],
            "required_property": required_property,
            "required_property_present": required_property in property_keys if required_property else None,
            "required_property_non_empty_count": required_property_non_empty if required_property else None,
            "ready_for_overlay": (
                len(features) > 0
                and not invalid_geometry_types
                and empty_geometry_count == 0
                and (required_property is None or required_property_non_empty > 0)
            ),
        }
    )
    return result


def core_export_path(expected: dict[str, str]) -> tuple[Path, str]:
    normalized_path = NORMALIZED_CORE_EXPORT_DIR / expected["normalized_filename"]
    raw_path = CORE_EXPORT_DIR / expected["expected_filename"]
    if normalized_path.exists():
        return normalized_path, "normalized"
    return raw_path, "raw"


def validate_core_exports() -> list[dict[str, Any]]:
    summaries = []
    for expected in EXPECTED_CORE_EXPORTS:
        path, source_variant = core_export_path(expected)
        raw_path = CORE_EXPORT_DIR / expected["expected_filename"]
        normalized_path = NORMALIZED_CORE_EXPORT_DIR / expected["normalized_filename"]
        if path.exists():
            validation = geojson_summary(path, required_property=expected["class_property"])
        else:
            validation = {
                "path": str(path),
                "exists": False,
                "readable": False,
                "errors": ["missing_expected_geojson_export"],
                "ready_for_overlay": False,
            }
        summaries.append({
            **expected,
            **validation,
            "source_variant": source_variant,
            "raw_path": str(raw_path),
            "raw_exists": raw_path.exists(),
            "normalized_path": str(normalized_path),
            "normalized_exists": normalized_path.exists(),
        })
    return summaries


def sidecars_for_shapefile(path: Path) -> dict[str, bool]:
    return {
        suffix: path.with_suffix(suffix).exists()
        for suffix in [".shp", ".shx", ".dbf", ".prj"]
    }


def lgd_hint_matches(property_keys: list[str]) -> dict[str, list[str]]:
    lower_to_original = {key.lower(): key for key in property_keys}
    result: dict[str, list[str]] = {}
    for scope, candidates in LGD_HINT_FIELDS.items():
        matches = [lower_to_original[candidate] for candidate in candidates if candidate in lower_to_original]
        result[scope] = matches
    return result


def validate_boundary_candidates() -> list[dict[str, Any]]:
    if not BOUNDARY_DIR.exists():
        return []

    candidates = [
        path
        for path in sorted(BOUNDARY_DIR.rglob("*"))
        if path.is_file() and path.suffix.lower() in BOUNDARY_EXTENSIONS
    ]
    summaries: list[dict[str, Any]] = []
    for path in candidates:
        suffix = path.suffix.lower()
        rel_path = str(path.relative_to(ROOT))
        if suffix == ".shp":
            summaries.append(
                {
                    "path": rel_path,
                    "format": "shapefile",
                    "sidecars": sidecars_for_shapefile(path),
                    "readable": None,
                    "ready_for_overlay": False,
                    "note": "Shapefile presence detected. Convert to GeoJSON or inspect with GIS/geopandas before overlay.",
                }
            )
            continue

        summary = geojson_summary(path)
        summary["path"] = rel_path
        summary["format"] = "geojson"
        summary["lgd_hint_matches"] = lgd_hint_matches(summary.get("sample_property_keys", []))
        summary["has_any_lgd_hint_field"] = any(summary["lgd_hint_matches"].values())
        summaries.append(summary)
    return summaries


def main() -> int:
    core_exports = validate_core_exports()
    boundary_candidates = validate_boundary_candidates()
    malformed_inputs = [
        item["path"]
        for item in core_exports + boundary_candidates
        if item.get("exists", True) and item.get("errors")
    ]
    all_core_exports_ready = all(item.get("ready_for_overlay") for item in core_exports)
    any_boundary_candidate_ready = any(
        item.get("format") == "geojson" and item.get("ready_for_overlay")
        for item in boundary_candidates
    )
    any_boundary_with_lgd_hint = any(
        item.get("has_any_lgd_hint_field")
        for item in boundary_candidates
    )

    result = {
        "schema_version": "core_lgd_overlay_input_validation.v1",
        "mode": "DRY_RUN_READ_ONLY",
        "external_calls_made": False,
        "db_writes_made": False,
        "core_export_dir": str(CORE_EXPORT_DIR),
        "normalized_core_export_dir": str(NORMALIZED_CORE_EXPORT_DIR),
        "boundary_dir": str(BOUNDARY_DIR),
        "core_exports": core_exports,
        "boundary_candidates": boundary_candidates,
        "readiness": {
            "core_export_dir_exists": CORE_EXPORT_DIR.exists(),
            "normalized_core_export_dir_exists": NORMALIZED_CORE_EXPORT_DIR.exists(),
            "all_core_exports_ready": all_core_exports_ready,
            "boundary_dir_exists": BOUNDARY_DIR.exists(),
            "boundary_candidates_found": bool(boundary_candidates),
            "any_boundary_candidate_ready": any_boundary_candidate_ready,
            "any_boundary_with_lgd_hint_field": any_boundary_with_lgd_hint,
            "malformed_inputs_found": bool(malformed_inputs),
            "ready_for_dry_run_overlay": (
                all_core_exports_ready
                and any_boundary_candidate_ready
                and any_boundary_with_lgd_hint
                and not malformed_inputs
            ),
        },
        "malformed_inputs": malformed_inputs,
        "next_actions": [
            "Export CoRE GeoJSON files into data/staged/core_stack/exports/.",
            "Stage reviewed boundary GeoJSON or shapefile candidates under data/staged/boundaries/.",
            "Prefer boundary files with LGD code attributes; otherwise create a reviewed LGD crosswalk before overlay.",
            "Do not write geography_climate_region_mappings until dry-run candidates are generated and reviewed.",
            "No Android Maestro flow is required until backend land-intelligence output changes.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if malformed_inputs else 0


if __name__ == "__main__":
    raise SystemExit(main())
