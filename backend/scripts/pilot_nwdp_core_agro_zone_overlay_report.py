#!/usr/bin/env python3
"""Read-only multi-state NWDP village polygon × CoRE/agro-zone overlay pilot report."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from shapely.geometry import shape

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from sample_nwdp_core_agro_zone_overlay import classify_overlay, load_zones

RAW_NWDP_DIR = ROOT / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
DEFAULT_STATES = ["Andaman and Nicobar Islands", "Karnataka", "Maharashtra"]
DEFAULT_SOURCE_CRS = "EPSG:7755"


def db_url() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def candidate_rows(state: str, limit: int) -> list[dict[str, Any]]:
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
            where b.source_system = :source_system
              and b.state_or_ut = :state
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by c.source_feature_index
            limit :limit
        """), {"source_system": SOURCE_SYSTEM, "state": state, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def guardrail_counts() -> dict[str, Any]:
    engine = create_engine(db_url())
    with engine.connect() as conn:
        nwdp = conn.execute(text("""
            select
              count(*) as candidates,
              count(*) filter (where c.is_active = true) as active_candidates,
              count(*) filter (where c.promotion_status <> 'NOT_PROMOTED') as promoted_candidates
            from geography_boundary_crosswalk_candidates c
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            where b.source_system = :source_system
        """), {"source_system": SOURCE_SYSTEM}).mappings().one()
        project_matches = conn.execute(text("select count(*) from geography_boundary_project_matches")).scalar()
        zone_mappings = conn.execute(text("select count(*) from geography_climate_region_mappings")).scalar()
    return {
        "nwdp_candidates": dict(nwdp),
        "project_match_rows": int(project_matches or 0),
        "climate_region_mapping_rows": int(zone_mappings or 0),
    }


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    layer_status: dict[str, Counter] = defaultdict(Counter)
    top_zones: dict[str, Counter] = defaultdict(Counter)
    invalid = 0

    for item in items:
        overlay = item.get("overlay") or {}
        if overlay.get("status") != "OVERLAYED" or not math.isfinite(float(overlay.get("village_area_m2") or 0)):
            invalid += 1
        for layer_key, layer in overlay.get("layers", {}).items():
            layer_status[layer_key][layer["status"]] += 1
            top = layer.get("top_zone")
            if top:
                top_zones[layer_key][f"{top['zone_code']}|{top['zone_name']}"] += 1

    return {
        "invalid_or_missing_geometry_count": invalid,
        "layer_status_counts": {key: dict(value) for key, value in sorted(layer_status.items())},
        "top_zone_counts": {
            key: [{"zone": zone, "count": count} for zone, count in value.most_common(8)]
            for key, value in sorted(top_zones.items())
        },
    }


def run_state(state: str, limit: int, samples: int, zones: list[dict[str, Any]], source_crs: str, dominant: float, review: float) -> dict[str, Any]:
    raw_path = RAW_NWDP_DIR / f"{slug(state)}.geojson"
    rows = candidate_rows(state, limit)

    if not raw_path.exists():
        return {"state_or_ut": state, "healthy": False, "error": "RAW_NWDP_GEOJSON_NOT_FOUND", "raw_nwdp_geojson": str(raw_path), "items": []}

    features = json.loads(raw_path.read_text(encoding="utf-8")).get("features") or []
    items = []

    for row in rows:
        idx = int(row["source_feature_index"])
        if idx >= len(features) or not features[idx].get("geometry"):
            continue
        overlay = classify_overlay(shape(features[idx]["geometry"]), zones, dominant, review, source_crs)
        items.append({"source_feature_index": idx, "candidate": row, "overlay": overlay})

    summary = summarize(items)
    return {
        "state_or_ut": state,
        "healthy": bool(items) and summary["invalid_or_missing_geometry_count"] == 0,
        "raw_nwdp_geojson": str(raw_path),
        "candidate_count": len(rows),
        "sample_count": len(items),
        "summary": summary,
        "items": items[:samples],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", nargs="*", default=DEFAULT_STATES)
    parser.add_argument("--limit-per-state", type=int, default=25)
    parser.add_argument("--samples-per-state", type=int, default=5)
    parser.add_argument("--nwdp-source-crs", default=DEFAULT_SOURCE_CRS)
    parser.add_argument("--dominant-threshold", type=float, default=0.80)
    parser.add_argument("--review-threshold", type=float, default=0.50)
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-core-agro-zone-pilot-overlay-report.json"))
    args = parser.parse_args()

    before = guardrail_counts()
    zones = load_zones()
    states = [run_state(s, args.limit_per_state, args.samples_per_state, zones, args.nwdp_source_crs, args.dominant_threshold, args.review_threshold) for s in args.states]
    after = guardrail_counts()

    layer_totals: dict[str, Counter] = defaultdict(Counter)
    for state in states:
        for layer, counts in state.get("summary", {}).get("layer_status_counts", {}).items():
            layer_totals[layer].update(counts)

    guardrails = {
        "db_writes_attempted": False,
        "core_zone_mappings_written": before["climate_region_mapping_rows"] != after["climate_region_mapping_rows"],
        "nwdp_candidates_activated": before["nwdp_candidates"]["active_candidates"] != after["nwdp_candidates"]["active_candidates"],
        "nwdp_candidates_promoted": before["nwdp_candidates"]["promoted_candidates"] != after["nwdp_candidates"]["promoted_candidates"],
        "project_matching_records_written": before["project_match_rows"] != after["project_match_rows"],
        "runtime_tables_written": False,
        "lookup_api_enabled": False,
        "android_behavior_changed": False,
    }
    guardrails["db_writes_attempted"] = any([
        guardrails["core_zone_mappings_written"],
        guardrails["nwdp_candidates_activated"],
        guardrails["nwdp_candidates_promoted"],
        guardrails["project_matching_records_written"],
    ])

    aggregate = {
        "state_count": len(states),
        "healthy_state_count": sum(1 for state in states if state.get("healthy")),
        "candidate_count": sum(state.get("candidate_count", 0) for state in states),
        "sample_count": sum(state.get("sample_count", 0) for state in states),
        "layer_status_counts": {key: dict(value) for key, value in sorted(layer_totals.items())},
    }

    result = {
        "schema_version": "nwdp_core_agro_zone_pilot_overlay_report.v1",
        "mode": "READ_ONLY_MULTI_STATE_POLYGON_OVERLAY_PILOT_REPORT",
        "healthy": bool(states) and all(state.get("healthy") for state in states) and not guardrails["db_writes_attempted"],
        "nwdp_source_crs": args.nwdp_source_crs,
        "nwdp_target_crs": "EPSG:4326",
        "area_crs": "EPSG:6933",
        "dominant_threshold": args.dominant_threshold,
        "review_threshold": args.review_threshold,
        "limit_per_state": args.limit_per_state,
        "aggregate": aggregate,
        "states": states,
        "db_counts_before": before,
        "db_counts_after": after,
        "guardrails": guardrails,
        "readiness": {
            "ready_for_read_only_national_overlay_report": True,
            "ready_for_core_zone_mapping_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": result["healthy"], "aggregate": aggregate}, indent=2, default=str))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
