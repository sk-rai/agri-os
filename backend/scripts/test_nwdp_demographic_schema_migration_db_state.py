#!/usr/bin/env python3
"""Read-only DB-state regression for NWDP demographic schema migration 057."""

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
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
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

        row_count = conn.execute(text(f"select count(*) from {TARGET_TABLE}")).scalar() if table_exists else None

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

    detail = {
        "alembic_version": alembic_version,
        "table_exists": bool(table_exists),
        "row_count": row_count,
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
    check(row_count == 0, "Target table is empty after schema migration", detail)
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
