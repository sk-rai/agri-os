#!/usr/bin/env python3
"""Dry-run migration plan for NWDP demographic enrichment profile schema.

This creates a migration design artifact only. It does not create an Alembic
revision, does not write DB rows, does not import demographic profiles, and does
not change Android/runtime behavior.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


TABLE_NAME = "geography_village_demographic_profiles"


def build_plan() -> dict:
    columns = [
        "id uuid primary key",
        "village_id uuid not null references geography_villages(id)",
        "source_system varchar not null",
        "source_version varchar not null",
        "source_feature_id uuid null",
        "source_feature_index integer null",
        "source_vlcode varchar null",
        "source_state_name varchar null",
        "source_district_name varchar null",
        "source_subdistrict_name varchar null",
        "source_village_name varchar null",
        "total_population integer null",
        "male_population integer null",
        "female_population integer null",
        "total_households integer null",
        "average_household_size numeric null",
        "rural_urban varchar null",
        "nearest_town_name varchar null",
        "nearest_town_distance_km numeric null",
        "total_geographical_area numeric null",
        "forest_area numeric null",
        "non_agricultural_area numeric null",
        "barren_uncultivable_land numeric null",
        "permanent_pastures_grazing_area numeric null",
        "culturable_waste_land numeric null",
        "fallow_land_other_than_current numeric null",
        "current_fallow_area numeric null",
        "net_area_sown numeric null",
        "total_unirrigated_land numeric null",
        "area_irrigated_by_source numeric null",
        "canals_area numeric null",
        "wells_tube_wells_area numeric null",
        "tanks_lakes_area numeric null",
        "waterfall_area numeric null",
        "other_source_area numeric null",
        "tapwater_treated_status varchar null",
        "tapwater_untreated_status varchar null",
        "covered_well_status varchar null",
        "uncovered_well_status varchar null",
        "handpump_status varchar null",
        "tubewell_borehole_status varchar null",
        "spring_status varchar null",
        "river_canal_status varchar null",
        "tank_pond_lake_status varchar null",
        "closed_drainage_status varchar null",
        "open_drainage_status varchar null",
        "village_pin_code_status varchar null",
        "source_properties jsonb not null default '{}'",
        "match_evidence jsonb not null default '{}'",
        "review_status varchar not null default 'AUTO_CANDIDATE'",
        "is_active boolean not null default false",
        "promotion_status varchar not null default 'NOT_PROMOTED'",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz not null default now()",
    ]

    indexes = [
        {
            "name": "ix_geography_village_demographic_profiles_village_id",
            "columns": ["village_id"],
            "unique": False,
        },
        {
            "name": "ix_geography_village_demographic_profiles_source",
            "columns": ["source_system", "source_version"],
            "unique": False,
        },
        {
            "name": "ix_geography_village_demographic_profiles_source_vlcode",
            "columns": ["source_vlcode"],
            "unique": False,
        },
        {
            "name": "ix_geography_village_demographic_profiles_review",
            "columns": ["review_status", "promotion_status", "is_active"],
            "unique": False,
        },
        {
            "name": "uq_geography_village_demographic_profiles_source_feature",
            "columns": ["source_system", "source_version", "source_feature_id"],
            "unique": True,
            "where": "source_feature_id is not null",
        },
        {
            "name": "uq_geography_village_demographic_profiles_active_promoted",
            "columns": ["village_id", "source_system", "source_version"],
            "unique": True,
            "where": "is_active = true and promotion_status = 'PROMOTED'",
        },
    ]

    return {
        "schema_version": "nwdp_demographic_enrichment_schema_migration_plan.v1",
        "mode": "DRY_RUN_SCHEMA_MIGRATION_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_table": TABLE_NAME,
        "purpose": "Create an empty source-versioned demographic/amenity enrichment profile table attached to canonical LGD villages.",
        "claim_boundary": (
            "Migration plan only. It creates no migration file, applies no DDL, inserts no profile rows, "
            "does not claim official Census import, and does not change Android/runtime behavior."
        ),
        "columns": columns,
        "indexes": indexes,
        "expected_migration_behavior": {
            "create_table": True,
            "create_indexes": True,
            "insert_rows": False,
            "update_geography_villages": False,
            "activate_profiles": False,
            "promote_profiles": False,
            "enable_runtime_lookup": False,
            "change_android_behavior": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "schema_migration_file_created": False,
            "schema_migration_applied": False,
            "demographic_profile_rows_written": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_schema_migration_file": True,
            "ready_for_schema_migration_apply": False,
            "ready_for_demographic_profile_apply": False,
            "ready_for_admin_preview_endpoint": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-demographic-enrichment-schema-migration-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
