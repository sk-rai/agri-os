#!/usr/bin/env python3
"""Sample read-only NWDP village polygon × CoRE/agro-zone overlay."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from shapely.geometry import shape
from shapely.ops import transform
from shapely.validation import explain_validity

try:
    from shapely.validation import make_valid
except Exception:  # pragma: no cover
    make_valid = None

try:
    from pyproj import Transformer
except Exception:  # pragma: no cover
    Transformer = None

sys.path.insert(0, str(Path("backend").resolve()))
from app.core.config import settings


STATE = "Andaman and Nicobar Islands"
RAW_NWDP = Path("data/raw/nwdp_boundary_all_state/20260824T110250Z/andaman_and_nicobar_islands.geojson")
DEFAULT_NWDP_SOURCE_CRS = "EPSG:7755"
WGS84_CRS = "EPSG:4326"
EQUAL_AREA_CRS = "EPSG:6933"

ZONE_LAYERS = [
    {
        "layer_key": "agro_climatic",
        "path": Path("data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson"),
        "code_property": "regioncode",
        "name_property": "regionname",
    },
    {
        "layer_key": "agro_ecological",
        "path": Path("data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson"),
        "code_property": "ae_regcode",
        "name_property": "physio_reg",
    },
    {
        "layer_key": "biogeographic",
        "path": Path("data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson"),
        "code_property": "zone_code",
        "name_property": "biogeozone",
        "extra_properties": ["prov_code", "biogeoprov"],
    },
]


def db_url() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def load_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def equal_area_geom(geom):
    if Transformer is None:
        return geom
    transformer = Transformer.from_crs(WGS84_CRS, EQUAL_AREA_CRS, always_xy=True)
    return transform(transformer.transform, geom)


def transform_geom(geom, source_crs: str, target_crs: str):
    if source_crs == target_crs or Transformer is None:
        return geom
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geom)


def repair_geom(geom):
    if geom.is_valid:
        return geom, False, "Valid Geometry"
    reason = explain_validity(geom)
    repaired = make_valid(geom) if make_valid is not None else geom.buffer(0)
    return repaired, True, reason


def bounds_dict(geom) -> dict:
    minx, miny, maxx, maxy = geom.bounds
    return {"min_x": minx, "min_y": miny, "max_x": maxx, "max_y": maxy}


def load_zones() -> list[dict]:
    zones = []
    for layer in ZONE_LAYERS:
        data = load_geojson(layer["path"])
        for idx, feature in enumerate(data.get("features") or []):
            geom = feature.get("geometry")
            if not geom:
                continue
            props = feature.get("properties") or {}
            zones.append({
                "layer_key": layer["layer_key"],
                "feature_index": idx,
                "zone_code": str(props.get(layer["code_property"], "")),
                "zone_name": str(props.get(layer["name_property"], "")),
                "extra": {key: props.get(key) for key in layer.get("extra_properties", [])},
                "geometry": repair_geom(shape(geom))[0],
                "geometry_equal_area": equal_area_geom(repair_geom(shape(geom))[0]),
            })
    return zones


def classify_overlay(village_geom, zones: list[dict], dominant_threshold: float, review_threshold: float, nwdp_source_crs: str) -> dict:
    raw_validity = explain_validity(village_geom) if not village_geom.is_valid else "Valid Geometry"
    village_geom, repaired, repair_reason = repair_geom(village_geom)
    village_wgs84 = transform_geom(village_geom, nwdp_source_crs, WGS84_CRS)
    village_wgs84, repaired_after_transform, transform_repair_reason = repair_geom(village_wgs84)
    village_equal_area = equal_area_geom(village_wgs84)
    village_area = village_equal_area.area
    if not math.isfinite(village_area) or village_area <= 0:
        return {
            "status": "INVALID_VILLAGE_GEOMETRY",
            "village_area_m2": village_area,
            "raw_bounds": bounds_dict(village_geom),
            "wgs84_bounds": bounds_dict(village_wgs84),
            "raw_validity": raw_validity,
            "geometry_repaired": repaired or repaired_after_transform,
            "repair_reason": repair_reason if repaired else transform_repair_reason,
            "layers": {},
        }

    result_by_layer = {}
    for layer_key in sorted({zone["layer_key"] for zone in zones}):
        hits = []
        for zone in [z for z in zones if z["layer_key"] == layer_key]:
            if not village_wgs84.intersects(zone["geometry"]):
                continue
            intersection = village_equal_area.intersection(zone["geometry_equal_area"])
            area = intersection.area
            if not math.isfinite(area) or area <= 0:
                continue
            hits.append({
                "zone_code": zone["zone_code"],
                "zone_name": zone["zone_name"],
                "feature_index": zone["feature_index"],
                "overlap_area_m2": area,
                "overlap_ratio": area / village_area,
                "extra": zone["extra"],
            })

        hits.sort(key=lambda item: item["overlap_area_m2"], reverse=True)
        top = hits[0] if hits else None
        if top is None:
            status = "NO_ZONE_OVERLAP"
        elif top["overlap_ratio"] >= dominant_threshold:
            status = "DOMINANT_ZONE"
        elif top["overlap_ratio"] >= review_threshold:
            status = "MANUAL_REVIEW_ZONE"
        else:
            status = "UNRESOLVED_MULTI_ZONE"

        result_by_layer[layer_key] = {
            "status": status,
            "top_zone": top,
            "overlap_count": len(hits),
            "overlaps": hits[:5],
        }

    return {
        "status": "OVERLAYED",
        "village_area_m2": village_area,
        "raw_bounds": bounds_dict(village_geom),
        "wgs84_bounds": bounds_dict(village_wgs84),
        "raw_validity": raw_validity,
        "geometry_repaired": repaired or repaired_after_transform,
        "repair_reason": repair_reason if repaired else transform_repair_reason,
        "layers": result_by_layer,
    }


def candidate_map(state: str, limit: int) -> dict[int, dict]:
    engine = create_engine(db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            select
              c.source_feature_index,
              c.id::text as candidate_id,
              c.proposed_village_id::text as proposed_village_id,
              c.proposed_village_lgd_code,
              c.candidate_bucket,
              c.review_status,
              c.promotion_status,
              f.source_village_name,
              f.source_vlcode,
              f.source_district_name,
              f.source_subdistrict_name
            from geography_boundary_crosswalk_candidates c
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and b.state_or_ut = :state
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by c.source_feature_index
            limit :limit
        """), {"state": state, "limit": limit}).mappings().all()
    return {int(row["source_feature_index"]): dict(row) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut", default=STATE)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--nwdp-source-crs", default=DEFAULT_NWDP_SOURCE_CRS)
    parser.add_argument("--dominant-threshold", type=float, default=0.80)
    parser.add_argument("--review-threshold", type=float, default=0.50)
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-core-agro-zone-sample-overlay.json"))
    args = parser.parse_args()

    if args.state_or_ut != STATE:
        raise SystemExit(f"This sample currently supports {STATE!r}; got {args.state_or_ut!r}")
    if not RAW_NWDP.exists():
        raise SystemExit(f"Missing raw NWDP GeoJSON: {RAW_NWDP}")

    candidates = candidate_map(args.state_or_ut, args.limit)
    raw = load_geojson(RAW_NWDP)
    features = raw.get("features") or []
    zones = load_zones()

    items = []
    for feature_index, candidate in candidates.items():
        if feature_index >= len(features):
            items.append({
                "source_feature_index": feature_index,
                "candidate": candidate,
                "status": "SOURCE_FEATURE_INDEX_OUT_OF_RANGE",
            })
            continue

        geom_data = features[feature_index].get("geometry")
        if not geom_data:
            items.append({
                "source_feature_index": feature_index,
                "candidate": candidate,
                "status": "MISSING_SOURCE_GEOMETRY",
            })
            continue

        overlay = classify_overlay(shape(geom_data), zones, args.dominant_threshold, args.review_threshold, args.nwdp_source_crs)
        items.append({
            "source_feature_index": feature_index,
            "candidate": candidate,
            "overlay": overlay,
        })

    layer_summaries = {}
    for item in items:
        for layer_key, layer_result in (item.get("overlay") or {}).get("layers", {}).items():
            bucket = layer_summaries.setdefault(layer_key, {})
            status = layer_result["status"]
            bucket[status] = bucket.get(status, 0) + 1

    result = {
        "schema_version": "nwdp_core_agro_zone_sample_overlay.v1",
        "mode": "READ_ONLY_SAMPLE_POLYGON_OVERLAY",
        "healthy": len(items) > 0 and all("overlay" in item for item in items),
        "state_or_ut": args.state_or_ut,
        "sample_limit": args.limit,
        "sample_count": len(items),
        "dominant_threshold": args.dominant_threshold,
        "review_threshold": args.review_threshold,
        "raw_nwdp_geojson": str(RAW_NWDP),
        "nwdp_source_crs": args.nwdp_source_crs,
        "nwdp_target_crs": WGS84_CRS,
        "area_crs": EQUAL_AREA_CRS,
        "zone_layers": [
            {
                "layer_key": layer["layer_key"],
                "path": str(layer["path"]),
                "code_property": layer["code_property"],
                "name_property": layer["name_property"],
            }
            for layer in ZONE_LAYERS
        ],
        "layer_summaries": layer_summaries,
        "items": items,
        "guardrails": {
            "db_writes_attempted": False,
            "core_zone_mappings_written": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_tables_written": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "healthy": result["healthy"],
        "state_or_ut": result["state_or_ut"],
        "sample_count": result["sample_count"],
        "layer_summaries": result["layer_summaries"],
    }, indent=2, default=str))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
