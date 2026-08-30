#!/usr/bin/env python3
"""Memory-safe read-only dry-run plan for NWDP demographic enrichment profiles.

Processes one raw NWDP state GeoJSON at a time and counts profile rows that
could attach to geography_villages via guarded direct-code candidates.

No DB writes are attempted.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = ROOT / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-enrichment-import-plan.json")
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def clean_key(key: Any) -> str:
    return str(key).strip().replace("\n", "")


def numeric(value: Any) -> float:
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def first_value(props: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in props and props[key] not in (None, "", " "):
            return props[key]
    return None


def load_settings_url() -> str:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import settings

    url = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    if not url:
        raise RuntimeError("Database URL not found in backend settings")
    return str(url)


def normalize_state_key(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    for old, new in {"&": "and", ".": "", ",": ""}.items():
        text_value = text_value.replace(old, new)
    return "_".join(text_value.split())


def candidate_state_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for col in ("source_names", "source_codes", "metadata", "match_evidence"):
        payload = row.get(col) or {}
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            key_l = str(key).lower()
            if "state" in key_l and value:
                keys.add(normalize_state_key(value))
            if key_l in {"state_file", "source_state_file"} and value:
                keys.add(normalize_state_key(value))
    return keys


def query_safe_candidates() -> list[dict[str, Any]]:
    engine = create_engine(load_settings_url())

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select
                  c.id as candidate_id,
                  c.source_feature_id,
                  c.source_feature_index,
                  c.proposed_village_id,
                  c.proposed_village_lgd_code,
                  c.source_names,
                  c.source_codes,
                  c.match_evidence,
                  c.metadata
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches b on b.id = c.import_batch_id
                where b.source_system = :source_system
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
                order by c.created_at, c.id
                """
            ),
            {"source_system": SOURCE_SYSTEM},
        ).mappings().all()

    return [dict(row) for row in rows]


def build_profile_preview(candidate: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    return {
        "village_id": str(candidate["proposed_village_id"]),
        "source_system": SOURCE_SYSTEM,
        "source_version": "20260824T110250Z",
        "source_feature_id": str(candidate["source_feature_id"]) if candidate.get("source_feature_id") else None,
        "source_feature_index": candidate.get("source_feature_index"),
        "source_vlcode": str(first_value(props, "vlcode") or candidate.get("proposed_village_lgd_code") or ""),
        "source_state_name": first_value(props, "state_name", "state"),
        "source_district_name": first_value(props, "district"),
        "source_subdistrict_name": first_value(props, "subdistric", "subdistrict"),
        "source_village_name": first_value(props, "village"),
        "total_population": int(numeric(props.get("total_population_village"))),
        "male_population": int(numeric(props.get("total_male_population_village"))),
        "female_population": int(numeric(props.get("total_female_population_village"))),
        "total_households": int(numeric(props.get("total_households"))),
        "average_household_size": numeric(props.get("avg_household")),
        "rural_urban": first_value(props, "total_urban_rural"),
        "nearest_town_name": first_value(props, "nearest_town_name", "nearest_tonearest_town_name"),
        "nearest_town_distance_km": numeric(props.get("nearest_town_distance_from_village")),
        "total_geographical_area": numeric(props.get("total_geographical_area")),
        "forest_area": numeric(props.get("forest_area")),
        "net_area_sown": numeric(props.get("net_area_sown")),
        "total_unirrigated_land": numeric(props.get("total_unirrigated_land")),
        "area_irrigated_by_source": numeric(props.get("area_irrigated_by_source")),
        "handpump_status": first_value(props, "handpump_status"),
        "tapwater_treated_status": first_value(props, "tapwater_treated_status"),
        "review_status": "AUTO_CANDIDATE",
        "is_active": False,
        "promotion_status": "NOT_PROMOTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--sample-limit", type=int, default=25)
    args = parser.parse_args()

    candidates = query_safe_candidates()
    by_state: dict[str, dict[int, dict[str, Any]]] = {}
    missing_state_key_count = 0

    for row in candidates:
        state_keys = candidate_state_keys(row)
        if not state_keys:
            missing_state_key_count += 1
            continue
        feature_index = row.get("source_feature_index")
        if feature_index is None:
            continue
        for state_key in state_keys:
            by_state.setdefault(state_key, {})[int(feature_index)] = row

    planned = 0
    considered = 0
    missing_raw_feature = 0
    population_nonzero = 0
    household_nonzero = 0
    state_counts: Counter[str] = Counter()
    state_district_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    planned_review_status_counts: Counter[str] = Counter()
    planned_promotion_status_counts: Counter[str] = Counter()
    planned_active_count = 0
    profile_samples = []
    raw_geojson_file_count = 0

    for path in sorted(args.raw_dir.glob("*.geojson")):
        state_key = normalize_state_key(path.stem)
        candidates_for_state = by_state.get(state_key, {})
        if not candidates_for_state:
            continue

        raw_geojson_file_count += 1
        data = json.loads(path.read_text(encoding="utf-8"))

        for idx, feature in enumerate(data.get("features", [])):
            candidate = candidates_for_state.get(idx)
            if candidate is None:
                continue

            considered += 1
            props = {clean_key(k): v for k, v in feature.get("properties", {}).items()}
            profile = build_profile_preview(candidate, props)

            planned += 1
            state_name = str(profile.get("source_state_name") or path.stem)
            district_name = str(profile.get("source_district_name") or "")
            state_counts[state_name] += 1
            state_district_counts[(state_name, district_name)][profile["review_status"]] += 1
            planned_review_status_counts[profile["review_status"]] += 1
            planned_promotion_status_counts[profile["promotion_status"]] += 1
            if profile["is_active"]:
                planned_active_count += 1

            if profile["total_population"] > 0:
                population_nonzero += 1
            if profile["total_households"] > 0:
                household_nonzero += 1
            if len(profile_samples) < args.sample_limit:
                profile_samples.append(profile)

            if args.limit > 0 and planned >= args.limit:
                break

        if args.limit > 0 and planned >= args.limit:
            break

    result = {
        "schema_version": "nwdp_demographic_enrichment_import_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": planned > 0,
        "mode": "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_IMPORT_PLAN",
        "source_system": SOURCE_SYSTEM,
        "raw_dir": str(args.raw_dir),
        "raw_geojson_file_count_with_matches": raw_geojson_file_count,
        "limit": args.limit,
        "safe_candidate_count_loaded": len(candidates),
        "candidate_missing_state_key_count": missing_state_key_count,
        "candidate_count_considered": considered,
        "planned_profile_rows": planned,
        "missing_raw_feature_count": missing_raw_feature,
        "population_nonzero_count": population_nonzero,
        "household_nonzero_count": household_nonzero,
        "population_nonzero_ratio": round(population_nonzero / planned, 6) if planned else 0,
        "household_nonzero_ratio": round(household_nonzero / planned, 6) if planned else 0,
        "state_counts": state_counts.most_common(),
        "planned_review_status_counts": dict(sorted(planned_review_status_counts.items())),
        "planned_promotion_status_counts": dict(sorted(planned_promotion_status_counts.items())),
        "planned_active_profile_rows": planned_active_count,
        "planned_promoted_profile_rows": planned_promotion_status_counts.get("PROMOTED", 0),
        "planned_approved_vs_manual_review": {
            "approved_for_promotion_count": planned_review_status_counts.get("APPROVED_FOR_PROMOTION", 0),
            "manual_review_count": planned_review_status_counts.get("MANUAL_REVIEW", 0),
        },
        "planned_state_district_summary": [
            {
                "state_or_ut": state,
                "district": district,
                "planned_profile_rows": sum(counter.values()),
                "auto_candidate_count": counter.get("AUTO_CANDIDATE", 0),
                "manual_review_count": counter.get("MANUAL_REVIEW", 0),
                "approved_for_promotion_count": counter.get("APPROVED_FOR_PROMOTION", 0),
                "blocked_count": counter.get("BLOCKED", 0),
                "rejected_count": counter.get("REJECTED", 0),
            }
            for (state, district), counter in sorted(state_district_counts.items())
        ],
        "sample_profile_rows": profile_samples,
        "notes": [
            "Dry-run plan only; no demographic profile rows are written.",
            "Uses only guarded DIRECT_VLCODE_MATCH / AUTO_CANDIDATE / NOT_PROMOTED candidates with proposed_village_id.",
            "Official Census 2011 PCA/DCHB remains separate and is not claimed as imported.",
            "Processes raw GeoJSON one file at a time to avoid loading all national geometries into memory.",
        ],
        "guardrails": {
            "db_writes_attempted": False,
            "schema_migration_created": False,
            "demographic_profile_rows_written": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_schema_migration_plan": planned > 0,
            "ready_for_demographic_profile_apply": False,
            "ready_for_admin_preview_endpoint": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "output": str(args.output),
        "healthy": result["healthy"],
        "safe_candidate_count_loaded": result["safe_candidate_count_loaded"],
        "candidate_missing_state_key_count": result["candidate_missing_state_key_count"],
        "candidate_count_considered": result["candidate_count_considered"],
        "planned_profile_rows": result["planned_profile_rows"],
        "planned_review_status_counts": result["planned_review_status_counts"],
        "planned_state_district_summary_count": len(result["planned_state_district_summary"]),
        "population_nonzero_ratio": result["population_nonzero_ratio"],
        "household_nonzero_ratio": result["household_nonzero_ratio"],
    }, indent=2))

    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
