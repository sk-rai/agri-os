#!/usr/bin/env python3
"""Plan local validation for applying NWDP demographic schema migration 057.

This is a dry-run/checklist artifact only. It does not run Alembic, does not
connect to the database, does not apply DDL, and does not insert profile rows.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_plan() -> dict:
    return {
        "schema_version": "nwdp_demographic_schema_migration_apply_validation_plan.v1",
        "mode": "DRY_RUN_LOCAL_MIGRATION_APPLY_VALIDATION_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_revision": "057",
        "target_migration": "backend/alembic/versions/057_add_village_demographic_profiles.py",
        "target_table": "geography_village_demographic_profiles",
        "claim_boundary": (
            "Validation plan only. Does not run Alembic, does not apply DDL, does not insert "
            "demographic profiles, does not enable lookup/runtime behavior, and does not change Android."
        ),
        "pre_apply_checks": [
            "Confirm working tree has no unintended tracked modifications.",
            "Confirm migration file regression passes.",
            "Confirm Alembic current revision before upgrade.",
            "Confirm target table does not already exist, or if it exists, stop and inspect.",
        ],
        "apply_command": "cd backend && ../venv/bin/alembic upgrade head",
        "post_apply_checks": [
            "Confirm Alembic current revision is 057/head.",
            "Confirm geography_village_demographic_profiles exists.",
            "Confirm table row count is 0 immediately after migration.",
            "Confirm expected columns exist.",
            "Confirm expected indexes exist.",
            "Confirm foreign key to geography_villages exists.",
            "Confirm no geography_villages rows were updated.",
            "Confirm full NWDP boundary regression runner passes.",
        ],
        "expected_columns": [
            "id",
            "village_id",
            "source_system",
            "source_version",
            "source_feature_id",
            "source_feature_index",
            "source_vlcode",
            "source_state_name",
            "source_district_name",
            "source_subdistrict_name",
            "source_village_name",
            "total_population",
            "male_population",
            "female_population",
            "total_households",
            "average_household_size",
            "rural_urban",
            "nearest_town_name",
            "nearest_town_distance_km",
            "total_geographical_area",
            "forest_area",
            "non_agricultural_area",
            "barren_uncultivable_land",
            "permanent_pastures_grazing_area",
            "culturable_waste_land",
            "fallow_land_other_than_current",
            "current_fallow_area",
            "net_area_sown",
            "total_unirrigated_land",
            "area_irrigated_by_source",
            "canals_area",
            "wells_tube_wells_area",
            "tanks_lakes_area",
            "waterfall_area",
            "other_source_area",
            "tapwater_treated_status",
            "tapwater_untreated_status",
            "covered_well_status",
            "uncovered_well_status",
            "handpump_status",
            "tubewell_borehole_status",
            "spring_status",
            "river_canal_status",
            "tank_pond_lake_status",
            "closed_drainage_status",
            "open_drainage_status",
            "village_pin_code_status",
            "source_properties",
            "match_evidence",
            "review_status",
            "is_active",
            "promotion_status",
            "created_at",
            "updated_at",
        ],
        "expected_indexes": [
            "ix_geography_village_demographic_profiles_village_id",
            "ix_geography_village_demographic_profiles_source",
            "ix_geography_village_demographic_profiles_source_vlcode",
            "ix_geography_village_demographic_profiles_review",
            "uq_geography_village_demographic_profiles_source_feature",
            "uq_geography_village_demographic_profiles_active_promoted",
        ],
        "guardrails": {
            "alembic_upgrade_executed": False,
            "db_connection_attempted": False,
            "schema_migration_applied": False,
            "demographic_profile_rows_written": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_local_migration_apply_validation": True,
            "ready_for_demographic_profile_import_apply": False,
            "ready_for_admin_preview_endpoint": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-demographic-schema-migration-apply-validation-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
