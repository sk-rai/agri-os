#!/usr/bin/env python3
"""Read-only plan for NWDP demographic enrichment schema and guarded import."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_plan() -> dict:
    return {
        "schema_version": "nwdp_demographic_enrichment_schema_plan.v1",
        "mode": "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_SCHEMA_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "Design plan only. NWDP raw village boundary properties contain demographic, land-use, "
            "water-source, and amenity-like fields that can enrich matched LGD master villages. "
            "This is not an official Census 2011 PCA/DCHB import and does not change Android behavior."
        ),
        "current_evidence": {
            "existing_geography_master": {
                "table": "geography_villages",
                "known_count": 576083,
                "known_lgd_code_count": 576083,
                "current_census_name_count": 0,
                "current_census_village_code_count": 0,
                "role": "Canonical Android/admin state-district-tehsil-village identity hierarchy.",
            },
            "nwdp_demographic_source": {
                "raw_dir": "data/raw/nwdp_boundary_all_state/20260824T110250Z",
                "raw_geojson_file_count": 36,
                "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
                "feature_count": 654285,
                "population_nonzero_count": 605657,
                "population_coverage_ratio": 0.925678,
                "households_nonzero_count": 605657,
                "household_coverage_ratio": 0.925678,
                "official_census_import": False,
            },
            "nwdp_boundary_crosswalk": {
                "candidate_table": "geography_boundary_crosswalk_candidates",
                "safe_join_policy": "Only rows already matched to proposed_village_id through guarded NWDP direct-code candidate logic are eligible for auto demographic enrichment.",
                "manual_review_rows_excluded_from_auto_apply": True,
                "blocked_rows_excluded_from_auto_apply": True,
            },
        },
        "recommended_schema": {
            "table": "geography_village_demographic_profiles",
            "purpose": "Source-versioned demographic/amenity enrichment records attached to canonical LGD villages without overwriting geography master identity.",
            "identity_columns": [
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
            ],
            "core_demographic_columns": [
                "total_population integer null",
                "male_population integer null",
                "female_population integer null",
                "total_households integer null",
                "average_household_size numeric null",
                "rural_urban varchar null",
                "nearest_town_name varchar null",
                "nearest_town_distance_km numeric null",
            ],
            "land_use_columns": [
                "total_geographical_area numeric null",
                "forest_area numeric null",
                "non_agricultural_area numeric null",
                "barren_uncultivable_land numeric null",
                "permanent_pastures_grazing_area numeric null",
                "culturable_waste_land numeric null",
                "fallow_land_other_than_current numeric null",
                "current_fallow_area numeric null",
                "net_area_sown numeric null",
            ],
            "water_irrigation_columns": [
                "total_unirrigated_land numeric null",
                "area_irrigated_by_source numeric null",
                "canals_area numeric null",
                "wells_tube_wells_area numeric null",
                "tanks_lakes_area numeric null",
                "waterfall_area numeric null",
                "other_source_area numeric null",
            ],
            "amenity_status_columns": [
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
            ],
            "audit_columns": [
                "source_properties jsonb not null default '{}'",
                "match_evidence jsonb not null default '{}'",
                "review_status varchar not null default 'AUTO_CANDIDATE'",
                "is_active boolean not null default false",
                "promotion_status varchar not null default 'NOT_PROMOTED'",
                "created_at timestamptz not null",
                "updated_at timestamptz not null",
            ],
            "indexes": [
                "unique active profile per village_id/source_system/source_version when promoted",
                "index village_id",
                "index source_system/source_version",
                "index source_vlcode",
                "index review_status/promotion_status/is_active",
            ],
        },
        "guarded_import_workflow": {
            "phase_1_read_only_plan": "Define schema and guardrails only.",
            "phase_2_dry_run": {
                "expected_script": "backend/scripts/plan_nwdp_demographic_enrichment_import.py",
                "writes_db": False,
                "outputs": [
                    "eligible_profile_count",
                    "population_nonzero_count",
                    "household_nonzero_count",
                    "zero_or_missing_demographic_count",
                    "state_wise_counts",
                    "field_quality_warnings",
                    "sample_profile_rows",
                ],
            },
            "phase_3_schema_migration": {
                "allowed": "Create empty target table and indexes only.",
                "not_allowed": "No profile row insertion in migration.",
            },
            "phase_4_apply_disabled_endpoint": {
                "purpose": "Expose future admin contract while returning 501 until dry-run/review is accepted.",
                "writes_db": False,
            },
            "phase_5_guarded_apply": {
                "requires_admin_edit_permission": True,
                "requires_dry_run_artifact": True,
                "requires_source_version": True,
                "requires_explicit_apply_gate": True,
                "default_profile_status": "inactive / not promoted",
            },
            "phase_6_android_readiness": {
                "requires_promoted_active_profiles": True,
                "requires_backend_read_api": True,
                "android_behavior_change": "separate checkpoint only",
            },
        },
        "official_census_path": {
            "status": "not loaded locally",
            "recommended_separate_tables": [
                "geography_census_locations",
                "geography_census_village_profiles",
                "geography_census_lgd_crosswalk_candidates",
            ],
            "reason": "Official Census 2011 PCA/DCHB data has different source lineage and must not be conflated with NWDP demographic attributes.",
        },
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
            "ready_for_dry_run_import_plan": True,
            "ready_for_schema_migration": False,
            "ready_for_demographic_profile_apply": False,
            "ready_for_admin_preview_endpoint": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-demographic-enrichment-schema-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
