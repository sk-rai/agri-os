#!/usr/bin/env python3
"""Guarded NWDP demographic profile import apply command.

This command can insert inactive, not-promoted demographic profile rows for one
explicit state/UT only. It does not promote profiles, activate candidates,
update LGD geography, enable runtime lookup, or change Android behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-profile-import-apply.json")
DEFAULT_RAW_DIR = ROOT / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SOURCE_VERSION = "20260824T110250Z"


sys.path.insert(0, str(ROOT / "backend"))
from scripts.plan_nwdp_demographic_enrichment_import import (  # noqa: E402
    build_profile_preview,
    clean_key,
    load_settings_url,
    normalize_state_key,
)


def json_default(value: Any) -> str:
    return str(value)


def state_key_aliases(state_or_ut: str) -> list[str]:
    """Return conservative normalized aliases for singular/plural state labels."""

    key = normalize_state_key(state_or_ut)
    aliases = {key}

    if key.endswith("s"):
        aliases.add(key[:-1])
    else:
        aliases.add(f"{key}s")

    if key in {"arunachal_pradesh", "arunanchal_pradesh"}:
        aliases.update({"arunachal_pradesh", "arunanchal_pradesh"})

    if key in {"dadra_and_nagar_haveli_and_daman_and_diu", "dadra_and_nagar_haveli_and_daman_diu", "dadra_and_nagar_havelli_and_daman_and_diu"}:
        aliases.update({"dadra_and_nagar_haveli_and_daman_and_diu", "dadra_and_nagar_haveli_and_daman_diu", "dadra_and_nagar_havelli_and_daman_and_diu"})

    return sorted(alias for alias in aliases if alias)


def raw_geojson_paths_for_state(raw_dir: Path, state_or_ut: str) -> list[Path]:
    requested_state_keys = set(state_key_aliases(state_or_ut))
    paths = sorted(raw_dir.glob("*.geojson"))
    matching = [path for path in paths if normalize_state_key(path.stem) in requested_state_keys]
    fallback = [path for path in paths if path not in matching]
    return matching + fallback

def query_safe_candidates_for_state(state_or_ut: str) -> list[dict[str, Any]]:
    """Load only safe direct-code candidates for one import-batch state/UT."""

    engine = create_engine(load_settings_url())
    requested_state_key = normalize_state_key(state_or_ut)
    requested_state_keys = state_key_aliases(state_or_ut)

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
                  c.metadata,
                  b.state_or_ut
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches b on b.id = c.import_batch_id
                where b.source_system = :source_system
                  and lower(
                    regexp_replace(
                      replace(replace(replace(coalesce(b.state_or_ut, ''), '&', 'and'), '.', ''), ',', ''),
                      '\\s+',
                      '_',
                      'g'
                    )
                  ) = any(cast(:state_keys as text[]))
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
                order by c.created_at, c.id
                """
            ),
            {
                "source_system": SOURCE_SYSTEM,
                "state_keys": requested_state_keys,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def build_base_result(args: argparse.Namespace) -> dict:
    return {
        "schema_version": "nwdp_demographic_profile_import_apply.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "ONE_STATE_INACTIVE_PROFILE_APPLY",
        "target_table": "geography_village_demographic_profiles",
        "state_or_ut": args.state_or_ut,
        "apply": bool(args.apply),
        "limit": args.limit,
        "max_rows": args.max_rows,
        "claim_boundary": (
            "Guarded one-state demographic profile import inserts inactive, "
            "not-promoted NWDP-derived profile rows only. It does not promote "
            "profiles, activate candidates, update LGD geography, enable runtime "
            "lookup, change Android behavior, or claim official Census import."
        ),
        "selection_policy": {
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
            "state_scope_required": True,
            "all_state_apply_allowed": False,
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "candidate_review_status_required": "AUTO_CANDIDATE",
            "candidate_promotion_status_required": "NOT_PROMOTED",
            "candidate_proposed_village_id_required": True,
            "raw_feature_required": True,
        },
        "insert_policy": {
            "profile_review_status": "AUTO_CANDIDATE",
            "profile_promotion_status": "NOT_PROMOTED",
            "profile_is_active": False,
            "insert_scope": "inactive demographic profile rows only",
            "runtime_table_write_allowed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
        },
        "planned_scope": {
            "allowed_future_scope": "single state/UT inactive profile rows only",
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "candidate_review_status_required": "AUTO_CANDIDATE",
            "candidate_promotion_status_required": "NOT_PROMOTED",
            "profile_review_status": "AUTO_CANDIDATE",
            "profile_promotion_status": "NOT_PROMOTED",
            "profile_is_active": False,
        },
        "idempotency_policy": {
            "primary_dedupe_key": ["source_system", "source_version", "source_feature_id"],
            "skip_existing_source_feature": True,
            "do_not_update_existing_profiles": True,
            "do_not_delete_existing_profiles": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "profiles_promoted": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_profile_apply": False,
            "ready_for_state_scoped_apply_design": True,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
        "apply_result": {
            "policy_flag_present": True,
            "planned_insert_count": 0,
            "inserted_count": 0,
            "skipped_existing_count": 0,
            "missing_raw_feature_count": 0,
            "state_district_summary": [],
            "sample_inserted_source_feature_ids": [],
        },
        "error": None,
        "output": str(args.output),
    }


def find_state_profiles(state_or_ut: str, raw_dir: Path, limit: int) -> list[dict[str, Any]]:
    requested_state_keys = state_key_aliases(state_or_ut)
    candidates = query_safe_candidates_for_state(state_or_ut)
    candidates_by_index = {
        int(row["source_feature_index"]): row
        for row in candidates
        if row.get("source_feature_index") is not None
    }

    profiles: list[dict[str, Any]] = []

    for raw_path in raw_geojson_paths_for_state(raw_dir, state_or_ut):
        if not candidates_by_index:
            break

        data = json.loads(raw_path.read_text(encoding="utf-8"))
        for idx, feature in enumerate(data.get("features", [])):
            candidate = candidates_by_index.get(idx)
            if candidate is None:
                continue

            props = {clean_key(k): v for k, v in feature.get("properties", {}).items()}
            profile = build_profile_preview(candidate, props)
            profile_state_key = normalize_state_key(profile.get("source_state_name"))

            if profile_state_key not in requested_state_keys:
                continue

            profile["source_properties"] = props
            profile["match_evidence"] = {
                "candidate_id": str(candidate.get("candidate_id")),
                "candidate_bucket": "DIRECT_VLCODE_MATCH",
                "candidate_review_status": "AUTO_CANDIDATE",
                "candidate_promotion_status": "NOT_PROMOTED",
                "apply_scope": "one_state_inactive_profile_apply",
            }
            profiles.append(profile)

            if limit > 0 and len(profiles) >= limit:
                return profiles

    return profiles


def existing_source_feature_ids(conn, profiles: list[dict[str, Any]]) -> set[str]:
    ids = [profile["source_feature_id"] for profile in profiles if profile.get("source_feature_id")]
    if not ids:
        return set()

    rows = conn.execute(
        text("""
            select source_feature_id::text as source_feature_id
            from geography_village_demographic_profiles
            where source_system = :source_system
              and source_version = :source_version
              and source_feature_id = any(cast(:source_feature_ids as uuid[]))
        """),
        {
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
            "source_feature_ids": ids,
        },
    ).mappings().all()

    return {str(row["source_feature_id"]) for row in rows}


def insert_profiles(conn, profiles: list[dict[str, Any]]) -> int:
    inserted = 0

    for profile in profiles:
        conn.execute(
            text("""
                insert into geography_village_demographic_profiles (
                    id,
                    village_id,
                    source_system,
                    source_version,
                    source_feature_id,
                    source_feature_index,
                    source_vlcode,
                    source_state_name,
                    source_district_name,
                    source_subdistrict_name,
                    source_village_name,
                    total_population,
                    male_population,
                    female_population,
                    total_households,
                    average_household_size,
                    rural_urban,
                    nearest_town_name,
                    nearest_town_distance_km,
                    total_geographical_area,
                    forest_area,
                    net_area_sown,
                    total_unirrigated_land,
                    area_irrigated_by_source,
                    handpump_status,
                    tapwater_treated_status,
                    source_properties,
                    match_evidence,
                    review_status,
                    is_active,
                    promotion_status
                )
                values (
                    cast(:id as uuid),
                    cast(:village_id as uuid),
                    :source_system,
                    :source_version,
                    cast(:source_feature_id as uuid),
                    :source_feature_index,
                    :source_vlcode,
                    :source_state_name,
                    :source_district_name,
                    :source_subdistrict_name,
                    :source_village_name,
                    :total_population,
                    :male_population,
                    :female_population,
                    :total_households,
                    :average_household_size,
                    :rural_urban,
                    :nearest_town_name,
                    :nearest_town_distance_km,
                    :total_geographical_area,
                    :forest_area,
                    :net_area_sown,
                    :total_unirrigated_land,
                    :area_irrigated_by_source,
                    :handpump_status,
                    :tapwater_treated_status,
                    cast(:source_properties as jsonb),
                    cast(:match_evidence as jsonb),
                    'AUTO_CANDIDATE',
                    false,
                    'NOT_PROMOTED'
                )
            """),
            {
                **profile,
                "id": str(uuid.uuid4()),
                "source_properties": json.dumps(profile.get("source_properties") or {}, default=json_default),
                "match_evidence": json.dumps(profile.get("match_evidence") or {}, default=json_default),
            },
        )
        inserted += 1

    return inserted


def summarize_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], int] = {}
    for profile in profiles:
        key = (
            str(profile.get("source_state_name") or ""),
            str(profile.get("source_district_name") or ""),
        )
        grouped[key] = grouped.get(key, 0) + 1

    return [
        {
            "state_or_ut": state,
            "district": district,
            "planned_profile_rows": count,
            "auto_candidate_count": count,
            "manual_review_count": 0,
            "approved_for_promotion_count": 0,
            "blocked_count": 0,
            "rejected_count": 0,
        }
        for (state, district), count in sorted(grouped.items())
    ]


def write_result(args: argparse.Namespace, result: dict, exit_code: int) -> int:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=json_default))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-rows", type=int, default=1000)
    args = parser.parse_args()

    result = build_base_result(args)

    if not args.state_or_ut:
        result["mode"] = "APPLY_DISABLED_GUARDRAIL"
        result["error"] = "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_REQUIRES_STATE_SCOPE"
        result["apply_result"]["requires_state_scope"] = True
        result["apply_result"]["state_scope_present"] = False
        result["apply_result"]["apply_implemented"] = True
        return write_result(args, result, 1)

    result["apply_result"]["requires_state_scope"] = True
    result["apply_result"]["state_scope_present"] = True
    result["apply_result"]["apply_implemented"] = True

    if not args.apply:
        result["mode"] = "APPLY_DISABLED_GUARDRAIL"
        result["error"] = "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_FLAG_REQUIRED"
        return write_result(args, result, 1)

    profiles = find_state_profiles(args.state_or_ut, args.raw_dir, args.limit)
    result["apply_result"]["planned_insert_count"] = len(profiles)
    result["apply_result"]["state_district_summary"] = summarize_profiles(profiles)

    if not profiles:
        result["error"] = "NO_ELIGIBLE_NWDP_DEMOGRAPHIC_PROFILES_FOR_STATE"
        return write_result(args, result, 1)

    if len(profiles) > args.max_rows:
        result["error"] = "NWDP_DEMOGRAPHIC_PROFILE_IMPORT_APPLY_MAX_ROWS_EXCEEDED"
        return write_result(args, result, 1)

    engine = create_engine(load_settings_url())

    with engine.begin() as conn:
        existing = existing_source_feature_ids(conn, profiles)
        profiles_to_insert = [
            profile for profile in profiles
            if str(profile.get("source_feature_id")) not in existing
        ]
        inserted = insert_profiles(conn, profiles_to_insert)

    result["healthy"] = True
    result["guardrails"]["db_writes_attempted"] = True
    result["guardrails"]["demographic_profile_rows_written"] = inserted > 0
    result["readiness"]["ready_for_profile_apply"] = True
    result["apply_result"]["inserted_count"] = inserted
    result["apply_result"]["skipped_existing_count"] = len(profiles) - inserted
    result["apply_result"]["sample_inserted_source_feature_ids"] = [
        str(profile.get("source_feature_id")) for profile in profiles_to_insert[:10]
    ]

    return write_result(args, result, 0)


if __name__ == "__main__":
    raise SystemExit(main())
