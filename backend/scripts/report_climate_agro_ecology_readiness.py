#!/usr/bin/env python3
"""Read-only climate/agro-ecology readiness and gap audit.

Summarizes climate/agro-ecology mappings, crop suitability rules, district
coverage, and missing coverage. It does not seed, promote, activate runtime
lookup, call external APIs, or change Android behavior.
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

from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402

DEFAULT_OUT_DIR = ROOT / "data/staged/core_stack/climate_agro_ecology_readiness"


def i(value) -> int:
    return int(value or 0)


def pct(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator, 6)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    where = ["s.is_active = true", "d.is_active = true"]
    params = {"limit": args.limit}

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
        climate_mapping_districts as (
          select distinct
            m.id as mapping_id,
            d.id as district_id,
            m.region_code,
            m.scope_level,
            m.review_status,
            m.confidence
          from geography_climate_region_mappings m
          join geography_states s on s.lgd_code::text = m.state_lgd_code::text
          join geography_districts d
            on d.state_id = s.id
           and d.lgd_code::text = m.district_lgd_code::text
          where m.is_active = true
            and m.district_lgd_code is not null

          union

          select distinct
            m.id as mapping_id,
            v.district_id,
            m.region_code,
            m.scope_level,
            m.review_status,
            m.confidence
          from geography_climate_region_mappings m
          join geography_villages v on v.lgd_code::text = m.village_lgd_code::text
          join geography_districts d on d.id = v.district_id
          join geography_states s on s.id = d.state_id
          where m.is_active = true
            and m.village_lgd_code is not null
            and (m.state_lgd_code is null or s.lgd_code::text = m.state_lgd_code::text)

          union

          select distinct
            m.id as mapping_id,
            d.id as district_id,
            m.region_code,
            m.scope_level,
            m.review_status,
            m.confidence
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
            count(distinct cmd.mapping_id)::bigint as climate_mapping_count,
            count(distinct cmd.region_code)::bigint as climate_region_count,
            count(distinct r.id)::bigint as crop_climate_rule_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'STATE')::bigint as state_scope_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'DISTRICT')::bigint as district_scope_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'VILLAGE')::bigint as village_scope_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.review_status = 'MANUAL_REVIEW')::bigint as manual_review_mapping_count
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
          coalesce(c.climate_mapping_count, 0) as climate_mapping_count,
          coalesce(c.climate_region_count, 0) as climate_region_count,
          coalesce(c.crop_climate_rule_count, 0) as crop_climate_rule_count,
          coalesce(c.state_scope_mapping_count, 0) as state_scope_mapping_count,
          coalesce(c.district_scope_mapping_count, 0) as district_scope_mapping_count,
          coalesce(c.village_scope_mapping_count, 0) as village_scope_mapping_count,
          coalesce(c.approved_mapping_count, 0) as approved_mapping_count,
          coalesce(c.manual_review_mapping_count, 0) as manual_review_mapping_count
        from base b
        left join climate_by_district c on c.district_id = b.district_id
        order by b.state_or_ut, b.district
        limit :limit
    """

    raw_sql = """
        select
          (select count(*)::bigint from geography_climate_regions where is_active = true) as active_climate_region_count,
          (select count(distinct region_system)::bigint from geography_climate_regions where is_active = true) as active_region_system_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true) as active_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'STATE') as state_scope_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'DISTRICT') as district_scope_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'VILLAGE') as village_scope_mapping_count,
          (select count(*)::bigint from crop_climate_suitability_rules where is_active = true) as active_crop_climate_rule_count,
          (select count(distinct crop_code)::bigint from crop_climate_suitability_rules where is_active = true) as crops_with_climate_rule_count,
          (select count(*)::bigint from crops where is_active = true) as active_crop_count,
          (select count(*)::bigint from crop_climate_suitability_overrides where is_active = true) as active_crop_climate_override_count
    """

    mapping_breakdown_sql = """
        select
          coalesce(scope_level, 'UNKNOWN') as scope_level,
          coalesce(review_status, 'UNKNOWN') as review_status,
          coalesce(confidence, 'UNKNOWN') as confidence,
          count(*)::bigint as row_count
        from geography_climate_region_mappings
        where is_active = true
        group by scope_level, review_status, confidence
        order by row_count desc, scope_level, review_status, confidence
    """

    region_rule_gap_sql = """
        select
          r.region_system,
          r.region_code,
          r.region_name,
          count(rule.id)::bigint as active_rule_count
        from geography_climate_regions r
        left join crop_climate_suitability_rules rule
          on rule.region_code = r.region_code
         and rule.is_active = true
        where r.is_active = true
        group by r.region_system, r.region_code, r.region_name
        having count(rule.id) = 0
        order by r.region_system, r.region_code
        limit 200
    """

    crop_rule_gap_sql = """
        select
          c.code as crop_code,
          c.canonical_name as crop_name,
          count(rule.id)::bigint as active_rule_count
        from crops c
        left join crop_climate_suitability_rules rule
          on rule.crop_code = c.code
         and rule.is_active = true
        where c.is_active = true
        group by c.code, c.canonical_name
        having count(rule.id) = 0
        order by c.canonical_name
        limit 200
    """

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(sql), params).mappings()]
        raw = {key: i(value) for key, value in dict(conn.execute(text(raw_sql)).items()).items()} if False else None
        raw = {key: i(value) for key, value in dict(conn.execute(text(raw_sql)).mappings().one()).items()}
        mapping_breakdown = [dict(row) for row in conn.execute(text(mapping_breakdown_sql)).mappings()]
        region_rule_gaps = [dict(row) for row in conn.execute(text(region_rule_gap_sql)).mappings()]
        crop_rule_gaps = [dict(row) for row in conn.execute(text(crop_rule_gap_sql)).mappings()]

    int_fields = [key for key in rows[0].keys() if key.endswith("_count")] if rows else []
    normalized = []
    for row in rows:
        clean = dict(row)
        for field in int_fields:
            clean[field] = i(clean[field])

        clean["has_climate_mapping"] = clean["climate_mapping_count"] > 0
        clean["has_crop_climate_rules"] = clean["crop_climate_rule_count"] > 0
        clean["climate_admin_review_ready"] = clean["has_climate_mapping"]
        clean["climate_runtime_ready"] = clean["has_climate_mapping"] and clean["has_crop_climate_rules"]
        clean["needs_climate_mapping"] = clean["climate_mapping_count"] == 0
        clean["needs_crop_climate_rules"] = clean["climate_mapping_count"] > 0 and clean["crop_climate_rule_count"] == 0
        normalized.append(clean)

    districts_with_mapping = sum(1 for row in normalized if row["climate_mapping_count"] > 0)
    districts_with_rules = sum(1 for row in normalized if row["crop_climate_rule_count"] > 0)

    state_summary: dict[str, dict] = {}
    for row in normalized:
        state = row["state_or_ut"]
        bucket = state_summary.setdefault(
            state,
            {
                "state_or_ut": state,
                "district_count": 0,
                "districts_with_climate_mapping": 0,
                "districts_without_climate_mapping": 0,
                "districts_with_crop_climate_rules": 0,
                "lgd_village_count": 0,
                "climate_mapping_count": 0,
                "climate_region_count": 0,
                "crop_climate_rule_count": 0,
            },
        )
        bucket["district_count"] += 1
        bucket["districts_with_climate_mapping"] += 1 if row["climate_mapping_count"] > 0 else 0
        bucket["districts_without_climate_mapping"] += 1 if row["climate_mapping_count"] == 0 else 0
        bucket["districts_with_crop_climate_rules"] += 1 if row["crop_climate_rule_count"] > 0 else 0
        bucket["lgd_village_count"] += row["lgd_village_count"]
        bucket["climate_mapping_count"] += row["climate_mapping_count"]
        bucket["climate_region_count"] += row["climate_region_count"]
        bucket["crop_climate_rule_count"] += row["crop_climate_rule_count"]

    summary = {
        "state_district_row_count": len(normalized),
        "lgd_village_count": sum(row["lgd_village_count"] for row in normalized),
        "districts_with_climate_mapping": districts_with_mapping,
        "districts_without_climate_mapping": len(normalized) - districts_with_mapping,
        "districts_with_crop_climate_rules": districts_with_rules,
        "districts_without_crop_climate_rules": len(normalized) - districts_with_rules,
        "climate_mapping_district_coverage_ratio": pct(districts_with_mapping, len(normalized)),
        "crop_climate_rule_district_coverage_ratio": pct(districts_with_rules, len(normalized)),
        "matrix_climate_mapping_count": sum(row["climate_mapping_count"] for row in normalized),
        "matrix_climate_region_count": sum(row["climate_region_count"] for row in normalized),
        "matrix_crop_climate_rule_count": sum(row["crop_climate_rule_count"] for row in normalized),
        **raw,
        "regions_without_active_rules_count": len(region_rule_gaps),
        "active_crops_without_climate_rules_count": len(crop_rule_gaps),
    }

    readiness = {
        "lgd_state_district_reference_ready": summary["state_district_row_count"] > 0,
        "climate_regions_seeded": summary["active_climate_region_count"] > 0,
        "climate_mappings_seeded": summary["active_climate_mapping_count"] > 0,
        "crop_climate_rules_seeded": summary["active_crop_climate_rule_count"] > 0,
        "all_districts_have_climate_mapping": summary["districts_without_climate_mapping"] == 0,
        "all_districts_have_crop_climate_rules": summary["districts_without_crop_climate_rules"] == 0,
        "ready_for_admin_review": summary["active_climate_mapping_count"] > 0,
        "ready_for_runtime_enablement": (
            summary["districts_without_climate_mapping"] == 0
            and summary["districts_without_crop_climate_rules"] == 0
            and len(region_rule_gaps) == 0
        ),
        "ready_for_android_behavior_change": False,
    }

    result = {
        "schema_version": "climate_agro_ecology_readiness_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_CLIMATE_AGRO_ECOLOGY_READINESS_AUDIT",
        "filters": {
            "state_or_ut": args.state_or_ut,
            "district": args.district,
            "limit": args.limit,
        },
        "summary": summary,
        "readiness": readiness,
        "state_summary": sorted(state_summary.values(), key=lambda item: item["state_or_ut"]),
        "district_rows": normalized,
        "mapping_breakdown": [
            {**row, "row_count": i(row["row_count"])}
            for row in mapping_breakdown
        ],
        "region_rule_gaps_sample": [
            {**row, "active_rule_count": i(row["active_rule_count"])}
            for row in region_rule_gaps
        ],
        "crop_rule_gaps_sample": [
            {**row, "active_rule_count": i(row["active_rule_count"])}
            for row in crop_rule_gaps
        ],
        "source_posture": {
            "lgd_is_canonical_runtime_identity": True,
            "climate_layer_admin_review_only_until_full_coverage": True,
            "external_provider_activation_required_by_this_report": False,
            "android_behavior_change_supported_by_this_report": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "climate_regions_written": False,
            "climate_mappings_written": False,
            "crop_climate_rules_written": False,
            "external_api_called": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "recommended_next_steps": [
            "Use district gaps to prioritize climate/agro-ecology coverage before runtime enablement.",
            "Add source references and review status upgrades before treating mappings as production-grade advice.",
            "Add dry-run/apply workflow only after read-only coverage gaps are understood.",
            "Keep Android behavior unchanged until climate coverage and rule completeness are explicitly approved.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "climate_agro_ecology_readiness_report.json"
    district_csv_path = args.output_dir / "climate_agro_ecology_readiness_by_district.csv"
    state_csv_path = args.output_dir / "climate_agro_ecology_readiness_by_state.csv"

    result["output_files"] = {
        "json": str(json_path),
        "district_csv": str(district_csv_path),
        "state_csv": str(state_csv_path),
    }

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with district_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(normalized[0].keys()) if normalized else [])
        writer.writeheader()
        writer.writerows(normalized)

    with state_csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(result["state_summary"][0].keys()) if result["state_summary"] else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result["state_summary"])

    print(json.dumps({
        "healthy": result["healthy"],
        "json": str(json_path),
        "district_csv": str(district_csv_path),
        "state_csv": str(state_csv_path),
        "summary": summary,
        "readiness": readiness,
        "top_missing_districts": [row for row in normalized if row["needs_climate_mapping"]][:20],
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
