#!/usr/bin/env python3
"""Read-only NWDP village polygon × CoRE/agro-zone full overlay report.

Writes JSON/CSV report artifacts only. It does not write DB mappings, activate
NWDP candidates, create project matches, enable runtime lookup, or change Android.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
DEFAULT_OUTPUT_DIR = ROOT / "data/staged/core_stack/nwdp_overlay_report"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
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


def raw_path(state: str) -> Path:
    return RAW_NWDP_DIR / f"{slug(state)}.geojson"


def staged_states() -> list[str]:
    engine = create_engine(db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            select distinct b.state_or_ut
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            where b.source_system = :source_system
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by b.state_or_ut
        """), {"source_system": SOURCE_SYSTEM}).scalars().all()
    return [str(row) for row in rows]


def candidate_rows(state: str, limit: int | None) -> list[dict[str, Any]]:
    sql = """
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
    """
    params: dict[str, Any] = {"source_system": SOURCE_SYSTEM, "state": state}
    if limit and limit > 0:
        sql += "\nlimit :limit"
        params["limit"] = limit

    engine = create_engine(db_url())
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
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


def safe_ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def top_zone(layer: dict[str, Any] | None) -> dict[str, Any] | None:
    if not layer:
        return None
    top = layer.get("top_zone")
    return top if isinstance(top, dict) else None


def overlay_state(
    state: str,
    zones: list[dict[str, Any]],
    output_dir: Path,
    source_crs: str,
    dominant_threshold: float,
    review_threshold: float,
    limit: int | None,
    sample_limit: int,
) -> dict[str, Any]:
    state_started = time.perf_counter()
    path = raw_path(state)
    if not path.exists():
        return {
            "state_or_ut": state,
            "healthy": False,
            "error": "RAW_NWDP_GEOJSON_NOT_FOUND",
            "raw_nwdp_geojson": str(path),
        }

    rows = candidate_rows(state, limit)
    features = json.loads(path.read_text(encoding="utf-8")).get("features") or []
    status_counts: dict[str, Counter] = defaultdict(Counter)
    top_zone_counts: dict[str, Counter] = defaultdict(Counter)
    samples: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    invalid_or_missing = 0
    overlaid = 0

    for row in rows:
        idx = int(row["source_feature_index"])
        if idx >= len(features) or not features[idx].get("geometry"):
            invalid_or_missing += 1
            continue

        overlay = classify_overlay(
            shape(features[idx]["geometry"]),
            zones,
            dominant_threshold,
            review_threshold,
            source_crs,
        )

        if overlay.get("status") != "OVERLAYED" or safe_ratio(overlay.get("village_area_m2")) is None:
            invalid_or_missing += 1
            continue

        overlaid += 1
        row_out: dict[str, Any] = {
            "state_or_ut": state,
            "candidate_id": row["candidate_id"],
            "proposed_village_id": row["proposed_village_id"],
            "proposed_village_lgd_code": row["proposed_village_lgd_code"],
            "source_vlcode": row["source_vlcode"],
            "source_village_name": row["source_village_name"],
            "source_district_name": row["source_district_name"],
            "source_subdistrict_name": row["source_subdistrict_name"],
            "source_feature_index": idx,
            "village_area_m2": overlay["village_area_m2"],
        }

        for layer_key, layer in overlay.get("layers", {}).items():
            status = layer["status"]
            status_counts[layer_key][status] += 1
            top = top_zone(layer)
            if top:
                top_zone_counts[layer_key][f"{top['zone_code']}|{top['zone_name']}"] += 1
            row_out[f"{layer_key}_status"] = status
            row_out[f"{layer_key}_zone_code"] = top.get("zone_code") if top else ""
            row_out[f"{layer_key}_zone_name"] = top.get("zone_name") if top else ""
            row_out[f"{layer_key}_overlap_ratio"] = top.get("overlap_ratio") if top else ""

        csv_rows.append(row_out)
        if len(samples) < sample_limit:
            samples.append({"candidate": row, "overlay": overlay})

    state_csv = output_dir / f"{slug(state)}_overlay_rows.csv"
    if csv_rows:
        with state_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)

    elapsed_seconds = time.perf_counter() - state_started
    rows_per_second = overlaid / elapsed_seconds if elapsed_seconds > 0 else None

    return {
        "state_or_ut": state,
        "healthy": bool(rows) and invalid_or_missing == 0,
        "raw_nwdp_geojson": str(path),
        "eligible_candidate_count": len(rows),
        "overlaid_count": overlaid,
        "elapsed_seconds": elapsed_seconds,
        "rows_per_second": rows_per_second,
        "invalid_or_missing_geometry_count": invalid_or_missing,
        "csv": str(state_csv) if csv_rows else None,
        "layer_status_counts": {key: dict(value) for key, value in sorted(status_counts.items())},
        "top_zone_counts": {
            key: [{"zone": zone, "count": count} for zone, count in value.most_common(10)]
            for key, value in sorted(top_zone_counts.items())
        },
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", nargs="*", default=None)
    parser.add_argument("--limit-per-state", type=int, default=0, help="0 means no limit")
    parser.add_argument("--sample-limit-per-state", type=int, default=3)
    parser.add_argument("--nwdp-source-crs", default=DEFAULT_SOURCE_CRS)
    parser.add_argument("--dominant-threshold", type=float, default=0.80)
    parser.add_argument("--review-threshold", type=float, default=0.50)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    run_started = time.perf_counter()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    states = args.states or staged_states()
    limit = args.limit_per_state if args.limit_per_state > 0 else None

    before = guardrail_counts()
    zones = load_zones()
    state_reports = [
        overlay_state(
            state,
            zones,
            output_dir,
            args.nwdp_source_crs,
            args.dominant_threshold,
            args.review_threshold,
            limit,
            args.sample_limit_per_state,
        )
        for state in states
    ]
    after = guardrail_counts()

    layer_totals: dict[str, Counter] = defaultdict(Counter)
    for state in state_reports:
        for layer, counts in state.get("layer_status_counts", {}).items():
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

    elapsed_seconds = time.perf_counter() - run_started
    overlaid_total = sum(state.get("overlaid_count", 0) for state in state_reports)
    rows_per_second = overlaid_total / elapsed_seconds if elapsed_seconds > 0 else None
    estimated_full_eligible_villages = 451465
    estimated_full_seconds = estimated_full_eligible_villages / rows_per_second if rows_per_second else None

    aggregate = {
        "state_count": len(state_reports),
        "healthy_state_count": sum(1 for state in state_reports if state.get("healthy")),
        "eligible_candidate_count": sum(state.get("eligible_candidate_count", 0) for state in state_reports),
        "overlaid_count": overlaid_total,
        "invalid_or_missing_geometry_count": sum(state.get("invalid_or_missing_geometry_count", 0) for state in state_reports),
        "elapsed_seconds": elapsed_seconds,
        "rows_per_second": rows_per_second,
        "estimated_full_eligible_villages": estimated_full_eligible_villages,
        "estimated_full_seconds": estimated_full_seconds,
        "estimated_full_minutes": estimated_full_seconds / 60 if estimated_full_seconds else None,
        "estimated_full_hours": estimated_full_seconds / 3600 if estimated_full_seconds else None,
        "layer_status_counts": {key: dict(value) for key, value in sorted(layer_totals.items())},
    }

    result = {
        "schema_version": "nwdp_core_agro_zone_full_overlay_report.v1",
        "mode": "READ_ONLY_BATCHED_POLYGON_OVERLAY_REPORT",
        "healthy": bool(state_reports) and all(state.get("healthy") for state in state_reports) and not guardrails["db_writes_attempted"],
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "nwdp_source_crs": args.nwdp_source_crs,
        "nwdp_target_crs": "EPSG:4326",
        "area_crs": "EPSG:6933",
        "dominant_threshold": args.dominant_threshold,
        "review_threshold": args.review_threshold,
        "limit_per_state": limit,
        "aggregate": aggregate,
        "states": state_reports,
        "db_counts_before": before,
        "db_counts_after": after,
        "guardrails": guardrails,
        "readiness": {
            "ready_for_full_national_read_only_overlay": args.states is not None,
            "ready_for_core_zone_mapping_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }

    report_json = output_dir / "overlay_report.json"
    summary_csv = output_dir / "state_summary.csv"

    report_json.write_text(json.dumps(result, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "state_or_ut",
            "healthy",
            "eligible_candidate_count",
            "overlaid_count",
            "invalid_or_missing_geometry_count",
            "elapsed_seconds",
            "rows_per_second",
            "csv",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for state in state_reports:
            writer.writerow({key: state.get(key) for key in fields})

    print(json.dumps({
        "healthy": result["healthy"],
        "report_json": str(report_json),
        "summary_csv": str(summary_csv),
        "aggregate": aggregate,
        "guardrails": guardrails,
    }, indent=2, default=str))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
