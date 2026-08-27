#!/usr/bin/env python3
"""Read-only feasibility audit for NWDP village boundary × CoRE/agro-zone overlay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path("backend").resolve()))
from app.core.config import settings


ZONE_FILES = [
    Path("data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson"),
    Path("data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson"),
    Path("data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_geojson(path: Path) -> dict:
    exists = path.exists()
    if not exists:
        return {"path": str(path), "exists": False, "healthy": False}

    data = load_json(path)
    features = data.get("features") or []
    property_keys: set[str] = set()
    geometry_types: dict[str, int] = {}
    sample_properties = []

    for feature in features[:25]:
        props = feature.get("properties") or {}
        property_keys.update(str(k) for k in props.keys())
        if len(sample_properties) < 3:
            sample_properties.append(props)
        geom_type = ((feature.get("geometry") or {}).get("type") or "MISSING")
        geometry_types[geom_type] = geometry_types.get(geom_type, 0) + 1

    for feature in features[25:]:
        geom_type = ((feature.get("geometry") or {}).get("type") or "MISSING")
        geometry_types[geom_type] = geometry_types.get(geom_type, 0) + 1

    return {
        "path": str(path),
        "exists": True,
        "healthy": data.get("type") == "FeatureCollection" and len(features) > 0,
        "geojson_type": data.get("type"),
        "feature_count": len(features),
        "geometry_types": geometry_types,
        "property_keys_sample": sorted(property_keys)[:80],
        "sample_properties": sample_properties,
    }


def db_url() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-core-agro-zone-overlay-feasibility.json"))
    args = parser.parse_args()

    zone_layers = [summarize_geojson(path) for path in ZONE_FILES]

    engine = create_engine(db_url())
    with engine.connect() as conn:
        nwdp = conn.execute(text("""
            select
              count(*) as candidates,
              count(*) filter (
                where c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
              ) as safe_direct_auto_candidates,
              count(distinct c.proposed_village_id) filter (
                where c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.is_active = false
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
              ) as safe_direct_auto_villages,
              count(*) filter (where c.review_status = 'MANUAL_REVIEW') as manual_review_candidates,
              count(*) filter (where c.review_status = 'BLOCKED') as blocked_candidates,
              count(*) filter (where c.is_active = true) as active_candidates,
              count(*) filter (where c.promotion_status <> 'NOT_PROMOTED') as promoted_candidates
            from geography_boundary_crosswalk_candidates c
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
        """)).mappings().first()

        source_features = conn.execute(text("""
            select
              count(*) as source_features,
              count(*) filter (where source_bbox <> '[]'::jsonb) as source_bbox_count,
              count(*) filter (where transformed_bbox <> '[]'::jsonb) as transformed_bbox_count,
              count(*) filter (where transformed_centroid <> '{}'::jsonb) as transformed_centroid_count,
              count(*) filter (where source_geometry_hash is not null and source_geometry_hash <> '') as geometry_hash_count,
              count(*) filter (where f.is_active = true) as active_source_features
            from geography_boundary_source_features f
            join geography_boundary_import_batches b on b.id = f.import_batch_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
        """)).mappings().first()

        runtime = conn.execute(text("""
            select
              (select count(*) from geography_boundary_runtime_sets) as runtime_sets,
              (select count(*) from geography_boundary_runtime_features) as runtime_features,
              (select count(*) from geography_boundary_project_matches) as project_matches
        """)).mappings().first()

    result = {
        "schema_version": "nwdp_core_agro_zone_overlay_feasibility_audit.v1",
        "mode": "READ_ONLY_OVERLAY_FEASIBILITY_AUDIT",
        "healthy": all(layer["healthy"] for layer in zone_layers) and nwdp["safe_direct_auto_candidates"] > 0,
        "zone_layers": zone_layers,
        "nwdp_candidate_summary": dict(nwdp),
        "nwdp_source_feature_geometry_metadata": dict(source_features),
        "runtime_and_project_match_counts": dict(runtime),
        "feasibility": {
            "zone_layers_available": all(layer["healthy"] for layer in zone_layers),
            "safe_nwdp_village_matches_available": nwdp["safe_direct_auto_candidates"] > 0,
            "full_polygon_overlay_requires_raw_geojson_or_runtime_geometry": True,
            "db_source_feature_table_currently_has_bbox_centroid_hash_metadata": True,
            "db_source_feature_table_currently_does_not_store_full_geometry": True,
            "recommended_next_step": (
                "Use local raw NWDP GeoJSON files plus candidate/source_feature indexes to run a sampled "
                "read-only polygon overlay against normalized CoRE zone GeoJSONs."
            ),
        },
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
        "zone_layer_count": len(zone_layers),
        "safe_direct_auto_candidates": nwdp["safe_direct_auto_candidates"],
        "safe_direct_auto_villages": nwdp["safe_direct_auto_villages"],
        "recommended_next_step": result["feasibility"]["recommended_next_step"],
    }, indent=2, default=str))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
