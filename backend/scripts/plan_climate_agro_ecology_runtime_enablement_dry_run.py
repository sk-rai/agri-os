#!/usr/bin/env python3
"""Dry-run-only climate/agro-ecology runtime enablement plan.

This plan evaluates whether existing climate region mappings and crop climate
rules are ready for broader runtime use. It does not write mappings/rules,
enable flags, call external APIs, run workers, or change Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402


SCHEMA_VERSION = "climate_agro_ecology_runtime_enablement_dry_run.v1"
DEFAULT_OUT_DIR = ROOT / "data/staged/core_stack/climate_agro_ecology_runtime_enablement_dry_run"


def i(value) -> int:
    return int(value or 0)


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run-only climate/agro-ecology runtime enablement plan.")
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    where = ["s.is_active = true", "d.is_active = true"]
    params: dict[str, Any] = {"limit": args.limit}
    if args.state_or_ut:
        where.append("lower(trim(s.canonical_name)) = lower(trim(:state_or_ut))")
        params["state_or_ut"] = args.state_or_ut
    if args.district:
        where.append("lower(trim(d.canonical_name)) = lower(trim(:district))")
        params["district"] = args.district
    where_sql = " and ".join(where)

    district_sql = f"""
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
            count(distinct rule.id)::bigint as crop_climate_rule_count,
            count(distinct rule.crop_code)::bigint as crop_with_rule_count,
            count(distinct cmd.mapping_id) filter (where cmd.review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.review_status = 'MANUAL_REVIEW')::bigint as manual_review_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'STATE')::bigint as state_scope_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'DISTRICT')::bigint as district_scope_mapping_count,
            count(distinct cmd.mapping_id) filter (where cmd.scope_level = 'VILLAGE')::bigint as village_scope_mapping_count
          from climate_mapping_districts cmd
          left join crop_climate_suitability_rules rule
            on rule.region_code = cmd.region_code
           and rule.is_active = true
          group by cmd.district_id
        )
        select
          b.state_or_ut,
          b.district,
          b.state_lgd_code,
          b.district_lgd_code,
          b.lgd_village_count,
          coalesce(c.climate_mapping_count, 0)::bigint as climate_mapping_count,
          coalesce(c.climate_region_count, 0)::bigint as climate_region_count,
          coalesce(c.crop_climate_rule_count, 0)::bigint as crop_climate_rule_count,
          coalesce(c.crop_with_rule_count, 0)::bigint as crop_with_rule_count,
          coalesce(c.approved_mapping_count, 0)::bigint as approved_mapping_count,
          coalesce(c.manual_review_mapping_count, 0)::bigint as manual_review_mapping_count,
          coalesce(c.state_scope_mapping_count, 0)::bigint as state_scope_mapping_count,
          coalesce(c.district_scope_mapping_count, 0)::bigint as district_scope_mapping_count,
          coalesce(c.village_scope_mapping_count, 0)::bigint as village_scope_mapping_count
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
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and review_status = 'APPROVED_FOR_PROMOTION') as approved_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and review_status = 'MANUAL_REVIEW') as manual_review_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'STATE') as state_scope_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'DISTRICT') as district_scope_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'VILLAGE') as village_scope_mapping_count,
          (select count(*)::bigint from crop_climate_suitability_rules where is_active = true) as active_crop_climate_rule_count,
          (select count(distinct crop_code)::bigint from crop_climate_suitability_rules where is_active = true) as crops_with_climate_rule_count,
          (select count(*)::bigint from crops where is_active = true) as active_crop_count,
          (select count(*)::bigint from crop_climate_suitability_overrides where is_active = true) as active_crop_climate_override_count,
          (
            select count(*)::bigint
            from geography_climate_regions region
            where region.is_active = true
              and not exists (
                select 1
                from crop_climate_suitability_rules rule
                where rule.region_code = region.region_code
                  and rule.is_active = true
              )
          ) as regions_without_active_rules_count,
          (
            select count(*)::bigint
            from crops crop
            where crop.is_active = true
              and not exists (
                select 1
                from crop_climate_suitability_rules rule
                where rule.crop_code = crop.code
                  and rule.is_active = true
              )
          ) as active_crops_without_climate_rules_count
    """

    region_gap_sql = """
        select
          region.region_system,
          region.region_code,
          region.region_name,
          count(rule.id)::bigint as active_rule_count
        from geography_climate_regions region
        left join crop_climate_suitability_rules rule
          on rule.region_code = region.region_code
         and rule.is_active = true
        where region.is_active = true
        group by region.region_system, region.region_code, region.region_name
        having count(rule.id) = 0
        order by region.region_system, region.region_code
        limit 100
    """

    crop_gap_sql = """
        select
          crop.code as crop_code,
          crop.canonical_name as crop_name,
          count(rule.id)::bigint as active_rule_count
        from crops crop
        left join crop_climate_suitability_rules rule
          on rule.crop_code = crop.code
         and rule.is_active = true
        where crop.is_active = true
        group by crop.code, crop.canonical_name
        having count(rule.id) = 0
        order by crop.canonical_name
        limit 100
    """

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        district_rows = [row_dict(row) for row in conn.execute(text(district_sql), params).mappings().all()]
        raw = {key: i(value) for key, value in row_dict(conn.execute(text(raw_sql)).mappings().one()).items()}
        region_rule_gaps = [row_dict(row) for row in conn.execute(text(region_gap_sql)).mappings().all()]
        crop_rule_gaps = [row_dict(row) for row in conn.execute(text(crop_gap_sql)).mappings().all()]

    normalized = []
    for row in district_rows:
        clean = dict(row)
        for key in list(clean.keys()):
            if key.endswith("_count"):
                clean[key] = i(clean[key])

        clean["district_has_climate_mapping"] = clean["climate_mapping_count"] > 0
        clean["district_has_crop_climate_rules"] = clean["crop_climate_rule_count"] > 0
        clean["district_ready_for_admin_runtime_preview"] = clean["district_has_climate_mapping"] and clean["district_has_crop_climate_rules"]
        clean["planned_runtime_enablement_action"] = "WOULD_ENABLE_ADMIN_RUNTIME_PREVIEW" if clean["district_ready_for_admin_runtime_preview"] else "BLOCKED_PENDING_COVERAGE"
        clean["blocker"] = None
        if clean["climate_mapping_count"] == 0:
            clean["blocker"] = "MISSING_CLIMATE_MAPPING"
        elif clean["crop_climate_rule_count"] == 0:
            clean["blocker"] = "MISSING_CROP_CLIMATE_RULES"
        normalized.append(clean)

    state_rows: dict[str, dict[str, Any]] = {}
    for row in normalized:
        bucket = state_rows.setdefault(row["state_or_ut"], {
            "state_or_ut": row["state_or_ut"],
            "district_count": 0,
            "districts_ready_for_admin_runtime_preview": 0,
            "districts_without_climate_mapping": 0,
            "districts_without_crop_climate_rules": 0,
            "climate_mapping_count": 0,
            "crop_climate_rule_count": 0,
        })
        bucket["district_count"] += 1
        bucket["districts_ready_for_admin_runtime_preview"] += 1 if row["district_ready_for_admin_runtime_preview"] else 0
        bucket["districts_without_climate_mapping"] += 1 if row["climate_mapping_count"] == 0 else 0
        bucket["districts_without_crop_climate_rules"] += 1 if row["crop_climate_rule_count"] == 0 else 0
        bucket["climate_mapping_count"] += row["climate_mapping_count"]
        bucket["crop_climate_rule_count"] += row["crop_climate_rule_count"]

    state_summary_rows = []
    for row in state_rows.values():
        row["admin_runtime_preview_coverage_ratio"] = ratio(row["districts_ready_for_admin_runtime_preview"], row["district_count"])
        state_summary_rows.append(row)
    state_summary_rows.sort(key=lambda row: (-row["districts_ready_for_admin_runtime_preview"], row["state_or_ut"]))

    districts_ready = sum(1 for row in normalized if row["district_ready_for_admin_runtime_preview"])
    districts_missing_mapping = sum(1 for row in normalized if row["climate_mapping_count"] == 0)
    districts_missing_rules = sum(1 for row in normalized if row["crop_climate_rule_count"] == 0)

    summary = {
        **raw,
        "state_district_row_count": len(normalized),
        "districts_ready_for_admin_runtime_preview": districts_ready,
        "districts_blocked_from_admin_runtime_preview": len(normalized) - districts_ready,
        "districts_without_climate_mapping": districts_missing_mapping,
        "districts_without_crop_climate_rules": districts_missing_rules,
        "admin_runtime_preview_coverage_ratio": ratio(districts_ready, len(normalized)),
        "climate_mapping_district_coverage_ratio": ratio(len(normalized) - districts_missing_mapping, len(normalized)),
        "crop_climate_rule_district_coverage_ratio": ratio(len(normalized) - districts_missing_rules, len(normalized)),
        "planned_runtime_config_write_count": 0,
        "planned_mapping_write_count": 0,
        "planned_rule_write_count": 0,
    }

    readiness = {
        "ready_for_admin_review": raw["active_climate_region_count"] > 0 and raw["active_climate_mapping_count"] > 0,
        "ready_for_admin_runtime_preview": districts_ready > 0,
        "ready_for_broad_runtime_enablement": (
            summary["state_district_row_count"] > 0
            and districts_missing_mapping == 0
            and districts_missing_rules == 0
            and raw["regions_without_active_rules_count"] == 0
            and raw["active_crops_without_climate_rules_count"] == 0
        ),
        "ready_for_android_behavior_change": False,
        "requires_explicit_policy_flag_before_apply": True,
        "requires_admin_review_before_apply": True,
        "requires_gap_closure_before_broad_runtime": True,
        "requires_rollback_or_disable_plan": True,
    }

    guardrails = {
        "db_writes_attempted": False,
        "climate_mappings_written": False,
        "crop_climate_rules_written": False,
        "runtime_config_written": False,
        "runtime_lookup_enabled": False,
        "external_api_called": False,
        "provider_worker_executed": False,
        "android_behavior_changed": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "DRY_RUN_ONLY_CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_PLAN",
        "filters": {
            "state_or_ut": args.state_or_ut,
            "district": args.district,
            "limit": args.limit,
        },
        "claim_boundary": "This dry-run plan evaluates climate/agro-ecology runtime readiness using existing active mappings and crop-climate rules. It does not write mappings, write rules, enable runtime config, call external APIs, run provider workers, or change Android behavior.",
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "district_rows": normalized,
        "state_rows": state_summary_rows,
        "region_rule_gaps": region_rule_gaps,
        "crop_rule_gaps": crop_rule_gaps,
        "policy": {
            "source_tables": [
                "geography_climate_regions",
                "geography_climate_region_mappings",
                "crop_climate_suitability_rules",
                "crop_climate_suitability_overrides",
            ],
            "dry_run_only": True,
            "real_apply_supported_by_this_plan": False,
            "android_behavior_change_supported_by_this_plan": False,
            "external_provider_call_supported_by_this_plan": False,
            "district_runtime_preview_requires_mapping_and_rules": True,
            "broad_runtime_requires_all_districts_mapped_and_all_regions_crops_ruled": True,
        },
        "recommended_next_steps": [
            "Use district/state rows to prioritize missing climate mappings and crop-climate rule gaps.",
            "Add a disabled apply guard before any climate runtime enablement write path.",
            "Keep Android behavior unchanged until broad runtime coverage and product approval are complete.",
        ],
        "output_files": {
            "json": str(output_dir / "climate_agro_ecology_runtime_enablement_dry_run.json"),
            "district_csv": str(output_dir / "climate_agro_ecology_runtime_enablement_districts.csv"),
            "state_csv": str(output_dir / "climate_agro_ecology_runtime_enablement_states.csv"),
            "region_gap_csv": str(output_dir / "climate_agro_ecology_runtime_enablement_region_rule_gaps.csv"),
            "crop_gap_csv": str(output_dir / "climate_agro_ecology_runtime_enablement_crop_rule_gaps.csv"),
        },
    }

    (output_dir / "climate_agro_ecology_runtime_enablement_dry_run.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "climate_agro_ecology_runtime_enablement_districts.csv",
        normalized,
        [
            "state_or_ut",
            "district",
            "state_lgd_code",
            "district_lgd_code",
            "lgd_village_count",
            "climate_mapping_count",
            "climate_region_count",
            "crop_climate_rule_count",
            "crop_with_rule_count",
            "approved_mapping_count",
            "manual_review_mapping_count",
            "district_ready_for_admin_runtime_preview",
            "planned_runtime_enablement_action",
            "blocker",
        ],
    )
    write_csv(
        output_dir / "climate_agro_ecology_runtime_enablement_states.csv",
        state_summary_rows,
        [
            "state_or_ut",
            "district_count",
            "districts_ready_for_admin_runtime_preview",
            "districts_without_climate_mapping",
            "districts_without_crop_climate_rules",
            "climate_mapping_count",
            "crop_climate_rule_count",
            "admin_runtime_preview_coverage_ratio",
        ],
    )
    write_csv(
        output_dir / "climate_agro_ecology_runtime_enablement_region_rule_gaps.csv",
        region_rule_gaps,
        ["region_system", "region_code", "region_name", "active_rule_count"],
    )
    write_csv(
        output_dir / "climate_agro_ecology_runtime_enablement_crop_rule_gaps.csv",
        crop_rule_gaps,
        ["crop_code", "crop_name", "active_rule_count"],
    )

    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "healthy": True,
        "summary": summary,
        "readiness": readiness,
        "outputs": report["output_files"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
