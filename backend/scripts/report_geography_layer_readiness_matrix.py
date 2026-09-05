#!/usr/bin/env python3
"""Read-only state/district geography layer readiness matrix.

Produces JSON + CSV for admin/web inspection. It does not import, promote,
activate, enable runtime lookup, or change Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

DEFAULT_OUT_DIR = ROOT / "data/staged/core_stack/geography_layer_readiness_matrix"


def i(value) -> int:
    return int(value or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    where = ["s.is_active = true", "d.is_active = true"]
    params = {
        "limit": args.limit,
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
    }

    if args.state_or_ut:
        where.append("lower(trim(s.canonical_name)) = lower(trim(:state_or_ut))")
        params["state_or_ut"] = args.state_or_ut
    if args.district:
        where.append("lower(trim(d.canonical_name)) = lower(trim(:district))")
        params["district"] = args.district

    where_sql = " and ".join(where)

    sql = f"""
        with base as (
          select
            s.id as state_id,
            d.id as district_id,
            s.canonical_name as state_or_ut,
            d.canonical_name as district,
            s.lgd_code::text as state_lgd_code,
            d.lgd_code::text as district_lgd_code,
            count(v.id)::bigint as lgd_village_count
          from geography_states s
          join geography_districts d on d.state_id = s.id
          left join geography_villages v
            on v.district_id = d.id
           and v.is_active = true
          where {where_sql}
          group by s.id, d.id, s.canonical_name, d.canonical_name, s.lgd_code, d.lgd_code
        ),
        pin_by_district as (
          select
            v.district_id,
            count(distinct vpl.geography_village_id)::bigint as pin_linked_village_count,
            count(*)::bigint as pin_link_count
          from geography_village_pin_links vpl
          join geography_villages v on v.id = vpl.geography_village_id
          where vpl.is_active = true
            and vpl.match_status = 'MATCHED'
          group by v.district_id
        ),
        demo_by_district as (
          select
            v.district_id,
            count(*)::bigint as demographic_profile_row_count,
            count(*) filter (
              where p.review_status = 'APPROVED_FOR_PROMOTION'
                and p.promotion_status = 'PROMOTED'
                and p.is_active = true
            )::bigint as demographic_active_promoted_count,
            count(*) filter (where p.review_status = 'BLOCKED')::bigint as demographic_blocked_count,
            count(*) filter (
              where p.review_status = 'APPROVED_FOR_PROMOTION'
                and p.promotion_status = 'NOT_PROMOTED'
                and p.is_active = false
            )::bigint as demographic_remaining_eligible_count
          from geography_village_demographic_profiles p
          join geography_villages v on v.id = p.village_id
          where p.source_system = :source_system
            and p.source_version = :source_version
          group by v.district_id
        ),
        boundary_candidate_keys as (
          select
            c.id,
            coalesce(d_code.id, d_name.id) as district_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status
          from geography_boundary_crosswalk_candidates c
          left join geography_boundary_source_features sf on sf.id = c.source_feature_id
          left join geography_districts d_code
            on d_code.lgd_code::text = c.proposed_district_lgd_code::text
          left join geography_states s_code
            on s_code.id = d_code.state_id
           and s_code.lgd_code::text = c.proposed_state_lgd_code::text
          left join geography_states s_name
            on lower(trim(s_name.canonical_name)) = lower(trim(sf.source_state_name))
          left join geography_districts d_name
            on d_name.state_id = s_name.id
           and lower(trim(d_name.canonical_name)) = lower(trim(sf.source_district_name))
          where coalesce(d_code.id, d_name.id) is not null
        ),
        boundary_by_district as (
          select
            district_id,
            count(*)::bigint as boundary_candidate_count,
            count(*) filter (where candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as boundary_direct_vlcode_match_count,
            count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as boundary_auto_candidate_count,
            count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as boundary_manual_review_count,
            count(*) filter (where review_status = 'BLOCKED')::bigint as boundary_blocked_count,
            count(*) filter (where promotion_status = 'PROMOTED')::bigint as boundary_promoted_candidate_count
          from boundary_candidate_keys
          group by district_id
        ),
        runtime_by_district as (
          select
            district_id,
            count(*)::bigint as boundary_runtime_crosswalk_count,
            count(distinct runtime_feature_id)::bigint as boundary_runtime_feature_count
          from geography_boundary_runtime_crosswalks
          where is_active = true
          group by district_id
        ),
        project_boundary_by_district as (
          select
            v.district_id,
            count(*)::bigint as project_boundary_match_count
          from geography_boundary_project_matches pm
          join geography_villages v on v.id = pm.village_id
          where pm.is_active = true
          group by v.district_id
        ),
        climate_mapping_districts as (
          select distinct m.id, d.id as district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_states s on s.lgd_code::text = m.state_lgd_code::text
          join geography_districts d
            on d.state_id = s.id
           and d.lgd_code::text = m.district_lgd_code::text
          where m.is_active = true
            and m.district_lgd_code is not null

          union

          select distinct m.id, v.district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_villages v on v.lgd_code::text = m.village_lgd_code::text
          join geography_districts d on d.id = v.district_id
          join geography_states s on s.id = d.state_id
          where m.is_active = true
            and m.village_lgd_code is not null
            and (m.state_lgd_code is null or s.lgd_code::text = m.state_lgd_code::text)

          union

          select distinct m.id, d.id as district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_states s on s.lgd_code::text = m.state_lgd_code::text
          join geography_districts d on d.state_id = s.id
          where m.is_active = true
            and m.district_lgd_code is null
            and m.village_lgd_code is null
            and m.scope_level = 'STATE'
        ),
        climate_by_district as (
          select
            cmd.district_id,
            count(distinct cmd.id)::bigint as climate_mapping_count,
            count(distinct cmd.region_code)::bigint as climate_region_count,
            count(distinct r.id)::bigint as crop_climate_rule_count
          from climate_mapping_districts cmd
          left join crop_climate_suitability_rules r
            on r.region_code = cmd.region_code
           and r.is_active = true
          group by cmd.district_id
        )
        select
          b.state_or_ut,
          b.district,
          b.state_lgd_code,
          b.district_lgd_code,
          b.lgd_village_count,

          coalesce(pin.pin_linked_village_count, 0) as pin_linked_village_count,
          coalesce(pin.pin_link_count, 0) as pin_link_count,

          coalesce(demo.demographic_profile_row_count, 0) as demographic_profile_row_count,
          coalesce(demo.demographic_active_promoted_count, 0) as demographic_active_promoted_count,
          coalesce(demo.demographic_blocked_count, 0) as demographic_blocked_count,
          coalesce(demo.demographic_remaining_eligible_count, 0) as demographic_remaining_eligible_count,

          coalesce(boundary.boundary_candidate_count, 0) as boundary_candidate_count,
          coalesce(boundary.boundary_direct_vlcode_match_count, 0) as boundary_direct_vlcode_match_count,
          coalesce(boundary.boundary_auto_candidate_count, 0) as boundary_auto_candidate_count,
          coalesce(boundary.boundary_manual_review_count, 0) as boundary_manual_review_count,
          coalesce(boundary.boundary_blocked_count, 0) as boundary_blocked_count,
          coalesce(boundary.boundary_promoted_candidate_count, 0) as boundary_promoted_candidate_count,

          coalesce(runtime.boundary_runtime_crosswalk_count, 0) as boundary_runtime_crosswalk_count,
          coalesce(runtime.boundary_runtime_feature_count, 0) as boundary_runtime_feature_count,

          coalesce(project_boundary.project_boundary_match_count, 0) as project_boundary_match_count,

          coalesce(climate.climate_mapping_count, 0) as climate_mapping_count,
          coalesce(climate.climate_region_count, 0) as climate_region_count,
          coalesce(climate.crop_climate_rule_count, 0) as crop_climate_rule_count

        from base b
        left join pin_by_district pin on pin.district_id = b.district_id
        left join demo_by_district demo on demo.district_id = b.district_id
        left join boundary_by_district boundary on boundary.district_id = b.district_id
        left join runtime_by_district runtime on runtime.district_id = b.district_id
        left join project_boundary_by_district project_boundary on project_boundary.district_id = b.district_id
        left join climate_by_district climate on climate.district_id = b.district_id
        order by b.state_or_ut, b.district
        limit :limit
    """

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(sql), params).mappings()]

    int_fields = [key for key in rows[0].keys() if key.endswith("_count")] if rows else []
    normalized = []
    for row in rows:
        clean = dict(row)
        for field in int_fields:
            clean[field] = i(clean[field])

        clean["lgd_runtime_ready"] = True
        clean["pin_code_runtime_ready"] = clean["pin_linked_village_count"] > 0
        clean["demographic_admin_ready"] = clean["demographic_active_promoted_count"] > 0
        clean["demographic_android_enabled"] = False
        clean["boundary_admin_review_ready"] = clean["boundary_candidate_count"] > 0
        clean["boundary_runtime_ready"] = False
        clean["boundary_runtime_pilot_present"] = clean["boundary_runtime_feature_count"] > 0
        clean["project_boundary_matching_ready"] = clean["project_boundary_match_count"] > 0
        clean["climate_admin_review_ready"] = clean["climate_mapping_count"] > 0
        clean["climate_runtime_ready"] = clean["climate_mapping_count"] > 0 and clean["crop_climate_rule_count"] > 0
        clean["soi_direct_join_safe"] = False
        clean["bharatlas_operational_review_source"] = True
        normalized.append(clean)

    summary_keys = [key for key in int_fields if key.endswith("_count")]
    summary = {"state_district_row_count": len(normalized)}
    for key in summary_keys:
        summary[key] = sum(row[key] for row in normalized)

    raw_totals_sql = """
        select
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as raw_boundary_candidate_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'AUTO_CANDIDATE') as raw_boundary_auto_candidate_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'MANUAL_REVIEW') as raw_boundary_manual_review_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'BLOCKED') as raw_boundary_blocked_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where candidate_bucket = 'DIRECT_VLCODE_MATCH') as raw_boundary_direct_vlcode_match_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as raw_boundary_promoted_candidate_count,
          (select count(*)::bigint from geography_village_demographic_profiles where source_system = :source_system and source_version = :source_version) as raw_demographic_profile_row_count,
          (select count(*)::bigint from geography_village_demographic_profiles where source_system = :source_system and source_version = :source_version and review_status = 'APPROVED_FOR_PROMOTION' and promotion_status = 'PROMOTED' and is_active = true) as raw_demographic_active_promoted_count,
          (select count(*)::bigint from geography_village_pin_links where is_active = true and match_status = 'MATCHED') as raw_pin_link_count,
          (select count(distinct geography_village_id)::bigint from geography_village_pin_links where is_active = true and match_status = 'MATCHED') as raw_pin_linked_village_count
    """
    with engine.connect() as conn:
        raw_totals = dict(conn.execute(text(raw_totals_sql), {
            "source_system": SOURCE_SYSTEM,
            "source_version": SOURCE_VERSION,
        }).mappings().one())

    raw_totals = {key: i(value) for key, value in raw_totals.items()}

    gap_accounting = {
        "boundary_candidate_raw_count": raw_totals["raw_boundary_candidate_count"],
        "boundary_candidate_matrix_count": summary["boundary_candidate_count"],
        "boundary_candidate_outside_state_district_matrix_count": max(
            raw_totals["raw_boundary_candidate_count"] - summary["boundary_candidate_count"],
            0,
        ),
        "boundary_auto_candidate_raw_count": raw_totals["raw_boundary_auto_candidate_count"],
        "boundary_auto_candidate_matrix_count": summary["boundary_auto_candidate_count"],
        "boundary_manual_review_raw_count": raw_totals["raw_boundary_manual_review_count"],
        "boundary_manual_review_matrix_count": summary["boundary_manual_review_count"],
        "boundary_blocked_raw_count": raw_totals["raw_boundary_blocked_count"],
        "boundary_blocked_matrix_count": summary["boundary_blocked_count"],
        "boundary_direct_vlcode_match_raw_count": raw_totals["raw_boundary_direct_vlcode_match_count"],
        "boundary_direct_vlcode_match_matrix_count": summary["boundary_direct_vlcode_match_count"],
        "boundary_promoted_candidate_raw_count": raw_totals["raw_boundary_promoted_candidate_count"],
        "boundary_promoted_candidate_matrix_count": summary["boundary_promoted_candidate_count"],
        "demographic_profile_raw_count": raw_totals["raw_demographic_profile_row_count"],
        "demographic_profile_matrix_count": summary["demographic_profile_row_count"],
        "demographic_profile_outside_state_district_matrix_count": max(
            raw_totals["raw_demographic_profile_row_count"] - summary["demographic_profile_row_count"],
            0,
        ),
        "demographic_active_promoted_raw_count": raw_totals["raw_demographic_active_promoted_count"],
        "demographic_active_promoted_matrix_count": summary["demographic_active_promoted_count"],
        "pin_link_raw_count": raw_totals["raw_pin_link_count"],
        "pin_link_matrix_count": summary["pin_link_count"],
        "pin_link_outside_state_district_matrix_count": max(
            raw_totals["raw_pin_link_count"] - summary["pin_link_count"],
            0,
        ),
        "pin_linked_village_raw_count": raw_totals["raw_pin_linked_village_count"],
        "pin_linked_village_matrix_count": summary["pin_linked_village_count"],
    }

    result = {
        "schema_version": "geography_layer_readiness_matrix.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": len(normalized) > 0,
        "mode": "READ_ONLY_STATE_DISTRICT_GEOGRAPHY_LAYER_READINESS_MATRIX",
        "filters": {
            "state_or_ut": args.state_or_ut,
            "district": args.district,
            "limit": args.limit,
        },
        "summary": summary,
        "gap_accounting": gap_accounting,
        "rows": normalized,
        "source_posture": {
            "lgd_is_canonical_runtime_identity": True,
            "village_pin_codes_android_ready": True,
            "nwdp_demographic_android_enabled": False,
            "nwdp_boundary_runtime_lookup_enabled": False,
            "soi_direct_lgd_join_safe": False,
            "bharatlas_operational_review_source": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "lgd_geography_overwritten": False,
            "nwdp_demographic_android_enabled": False,
            "nwdp_boundary_runtime_lookup_enabled": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
        },
        "recommended_next_steps": [
            "Expose this matrix through a read-only admin endpoint.",
            "Add a web admin state/district matrix with layer drilldowns.",
            "Use the matrix to prioritize climate coverage, project boundary matching, and selected boundary runtime promotion.",
            "Keep all apply/promote workflows behind dry-run, explicit policy flags, audit output, and rollback/supersession plans.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "geography_layer_readiness_matrix.json"
    csv_path = args.output_dir / "geography_layer_readiness_matrix_by_district.csv"

    result["output_files"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = list(normalized[0].keys()) if normalized else []
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)

    print(json.dumps({
        "healthy": result["healthy"],
        "json": str(json_path),
        "csv": str(csv_path),
        "summary": summary,
        "gap_accounting": gap_accounting,
        "sample_rows": normalized[:5],
    }, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
