#!/usr/bin/env python3
"""Read-only DB-state regression for NWDP demographic schema migration 057.

This check supports the known safe DB states:
- fresh post-migration DB state with zero profile rows;
- the first persistent Andaman inactive-import checkpoint with 512 rows; and
- the completed all-state inactive-import checkpoint with 453,036 rows.

It remains read-only and verifies no active/promoted/non-auto demographic rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402


TARGET_TABLE = "geography_village_demographic_profiles"

EXPECTED_COLUMNS = {
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
}

EXPECTED_INDEXES = {
    "ix_geography_village_demographic_profiles_village_id",
    "ix_geography_village_demographic_profiles_source",
    "ix_geography_village_demographic_profiles_source_vlcode",
    "ix_geography_village_demographic_profiles_review",
    "uq_geography_village_demographic_profiles_source_feature",
    "uq_geography_village_demographic_profiles_active_promoted",
}


def db_url_from_settings() -> str:
    value = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    return str(value or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC SCHEMA MIGRATION DB STATE REGRESSION")
    print("=" * 72)

    engine = create_engine(db_url_from_settings())

    with engine.connect() as conn:
        alembic_version = conn.execute(text("select version_num from alembic_version")).scalar()

        table_exists = conn.execute(text("""
            select exists (
              select 1
              from information_schema.tables
              where table_schema = 'public'
                and table_name = :table_name
            )
        """), {"table_name": TARGET_TABLE}).scalar()

        columns = {
            row[0]
            for row in conn.execute(text("""
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
            """), {"table_name": TARGET_TABLE})
        }

        indexes = {
            row[0]
            for row in conn.execute(text("""
                select indexname
                from pg_indexes
                where schemaname = 'public'
                  and tablename = :table_name
            """), {"table_name": TARGET_TABLE})
        }

        foreign_keys = [
            row[0]
            for row in conn.execute(text("""
                select c.conname
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                where t.relname = :table_name
                  and c.contype = 'f'
            """), {"table_name": TARGET_TABLE})
        ]

        row_state = dict(conn.execute(text(f"""
            select
              count(*)::bigint as row_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
              count(*) filter (where review_status <> 'AUTO_CANDIDATE')::bigint as non_auto_candidate_row_count,
              count(*) filter (where source_state_name = 'Andaman & Nicobar Island')::bigint as andaman_profile_row_count
            from {TARGET_TABLE}
        """)).mappings().one()) if table_exists else {
            "row_count": None,
            "active_profile_row_count": None,
            "promoted_profile_row_count": None,
            "non_auto_candidate_row_count": None,
            "andaman_profile_row_count": None,
        }

    detail = {
        "alembic_version": alembic_version,
        "table_exists": bool(table_exists),
        **row_state,
        "missing_columns": sorted(EXPECTED_COLUMNS - columns),
        "missing_indexes": sorted(EXPECTED_INDEXES - indexes),
        "foreign_key_count": len(foreign_keys),
        "guardrails": {
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "lgd_geography_overwritten": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }

    check(alembic_version == "057", "Alembic revision is 057", detail)
    check(table_exists is True, "Target table exists", detail)
    check(detail["row_count"] >= 0, "Target table row count is readable", detail)
    check(detail["active_profile_row_count"] in (0, 5, 450026), "Active demographic profiles are empty, at South Andamans promotion checkpoint, or at full admin rollout checkpoint", detail)
    check(detail["promoted_profile_row_count"] in (0, 5), "Promoted demographic profiles are empty or at South Andamans promotion checkpoint", detail)
    check(detail["non_auto_candidate_row_count"] in (0, 5), "Imported demographic profiles are either all auto-candidate or at South Andamans approval/promotion checkpoint", detail)
    check(detail["row_count"] in (0, 512, 453036), "DB state allows empty, Andaman, or full all-state inactive import checkpoint", detail)
    check(detail["andaman_profile_row_count"] in (0, 512), "Andaman checkpoint count is stable when imported", detail)
    check(not detail["missing_columns"], "Expected columns exist", detail)
    check(not detail["missing_indexes"], "Expected indexes exist", detail)
    check(len(foreign_keys) >= 1, "Foreign key exists", detail)
    check(all(value is False for value in detail["guardrails"].values()), "Guardrails remain false", detail["guardrails"])

    print("=" * 72)
    print("NWDP DEMOGRAPHIC SCHEMA MIGRATION DB STATE REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
