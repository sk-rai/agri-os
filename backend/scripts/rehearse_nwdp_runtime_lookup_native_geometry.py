#!/usr/bin/env python3
"""Rollback-only rehearsal for runtime lookup native geometry."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import engine

TABLE = "geography_boundary_runtime_features"
COLUMN = "geometry_wgs84_geom"
INDEX = "idx_boundary_runtime_features_geom_active"

CONSTRAINTS = (
    "ck_boundary_runtime_features_geom_srid",
    "ck_boundary_runtime_features_geom_type",
    "ck_boundary_runtime_features_geom_valid",
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--confirm-rollback-only-rehearsal",
        action="store_true",
    )
    return parser.parse_args()


def snapshot(connection) -> dict:
    row = connection.execute(text("""
        select
          (
            select version_num
            from alembic_version
          ) as alembic_version,
          (
            select count(*)::bigint
            from geography_boundary_runtime_sets
          ) as runtime_set_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
          ) as runtime_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
          ) as runtime_crosswalk_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
            where is_active = true
          ) as active_runtime_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_project_matches
          ) as project_match_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidate_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidate_rows
    """)).mappings().one()

    return {
        key: (
            int(value or 0)
            if key != "alembic_version"
            else str(value)
        )
        for key, value in row.items()
    }


def catalog(connection) -> dict:
    column = connection.execute(text("""
        select
          data_type,
          udt_name,
          is_nullable
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = :table
          and column_name = :column
    """), {
        "table": TABLE,
        "column": COLUMN,
    }).mappings().one_or_none()

    constraints = [
        dict(row)
        for row in connection.execute(text("""
            select
              con.conname as name,
              pg_get_constraintdef(
                con.oid,
                true
              ) as definition
            from pg_constraint con
            join pg_class rel
              on rel.oid = con.conrelid
            join pg_namespace ns
              on ns.oid = rel.relnamespace
            where ns.nspname = current_schema()
              and rel.relname = :table
              and con.conname = any(:names)
            order by con.conname
        """), {
            "table": TABLE,
            "names": list(CONSTRAINTS),
        }).mappings().all()
    ]

    index = connection.execute(text("""
        select
          indexname,
          indexdef
        from pg_indexes
        where schemaname = current_schema()
          and tablename = :table
          and indexname = :index
    """), {
        "table": TABLE,
        "index": INDEX,
    }).mappings().one_or_none()

    return {
        "column": dict(column) if column else None,
        "constraints": constraints,
        "index": dict(index) if index else None,
    }


def main() -> int:
    options = arguments()

    if not options.confirm_rollback_only_rehearsal:
        raise SystemExit(
            "ROLLBACK_ONLY_REHEARSAL_CONFIRMATION_REQUIRED"
        )

    with engine.connect() as connection:
        before = snapshot(connection)
        before_catalog = catalog(connection)

    preflight = {
        "database_revision_is_058":
            before["alembic_version"] == "058",
        "native_geometry_column_absent":
            before_catalog["column"] is None,
        "native_geometry_constraints_absent":
            before_catalog["constraints"] == [],
        "native_geometry_index_absent":
            before_catalog["index"] is None,
        "postgis_geometry_type_available": False,
        "postgis_functions_available": False,
    }

    with engine.connect() as connection:
        capabilities = connection.execute(text("""
            select
              to_regtype('geometry') is not null
                as geometry_type_available,
              to_regprocedure(
                'st_srid(geometry)'
              ) is not null
                as st_srid_available,
              to_regprocedure(
                'st_isvalid(geometry)'
              ) is not null
                as st_isvalid_available,
              to_regprocedure(
                'st_isempty(geometry)'
              ) is not null
                as st_isempty_available
        """)).mappings().one()

    preflight["postgis_geometry_type_available"] = (
        capabilities["geometry_type_available"] is True
    )
    preflight["postgis_functions_available"] = all([
        capabilities["st_srid_available"] is True,
        capabilities["st_isvalid_available"] is True,
        capabilities["st_isempty_available"] is True,
    ])

    if not all(preflight.values()):
        raise SystemExit(
            "NATIVE_GEOMETRY_REHEARSAL_PREFLIGHT_FAILED:"
            + json.dumps(
                preflight,
                sort_keys=True,
            )
        )

    during_catalog = None
    rollback_executed = False
    rehearsal_error = None

    connection = engine.connect()
    transaction = connection.begin()

    try:
        connection.execute(text(
            "set local lock_timeout = '5s'"
        ))
        connection.execute(text(
            "set local statement_timeout = '60s'"
        ))

        connection.execute(text(f"""
            alter table {TABLE}
            add column {COLUMN}
              geometry(Geometry,4326)
              null
        """))

        connection.execute(text(f"""
            alter table {TABLE}
            add constraint
              {CONSTRAINTS[0]}
            check (
              {COLUMN} is null
              or ST_SRID({COLUMN}) = 4326
            )
        """))

        connection.execute(text(f"""
            alter table {TABLE}
            add constraint
              {CONSTRAINTS[1]}
            check (
              {COLUMN} is null
              or ST_GeometryType({COLUMN})
                in (
                  'ST_Polygon',
                  'ST_MultiPolygon'
                )
            )
        """))

        connection.execute(text(f"""
            alter table {TABLE}
            add constraint
              {CONSTRAINTS[2]}
            check (
              {COLUMN} is null
              or (
                ST_IsValid({COLUMN})
                and not ST_IsEmpty({COLUMN})
              )
            )
        """))

        # Transactional equivalent for rollback testing only.
        # Revision 059 uses CREATE INDEX CONCURRENTLY outside a
        # transaction for the actual migration.
        connection.execute(text(f"""
            create index {INDEX}
            on {TABLE}
            using gist ({COLUMN})
            where is_active = true
              and {COLUMN} is not null
        """))

        during_catalog = catalog(connection)

        if during_catalog["column"] is None:
            raise RuntimeError(
                "REHEARSAL_COLUMN_NOT_VISIBLE"
            )
        if len(
            during_catalog["constraints"]
        ) != len(CONSTRAINTS):
            raise RuntimeError(
                "REHEARSAL_CONSTRAINT_COUNT_MISMATCH"
            )
        if during_catalog["index"] is None:
            raise RuntimeError(
                "REHEARSAL_INDEX_NOT_VISIBLE"
            )

    except Exception as exc:
        rehearsal_error = (
            f"{type(exc).__name__}:{exc}"
        )
    finally:
        transaction.rollback()
        rollback_executed = True
        connection.close()

    with engine.connect() as connection:
        after = snapshot(connection)
        after_catalog = catalog(connection)

    checks = {
        "preflight_passed":
            all(preflight.values()),
        "column_visible_during_rehearsal":
            bool(
                during_catalog
                and during_catalog["column"]
            ),
        "three_constraints_visible_during_rehearsal":
            bool(
                during_catalog
                and len(
                    during_catalog["constraints"]
                ) == 3
            ),
        "gist_index_visible_during_rehearsal":
            bool(
                during_catalog
                and during_catalog["index"]
                and "USING gist"
                in during_catalog[
                    "index"
                ]["indexdef"]
            ),
        "partial_index_predicate_visible":
            bool(
                during_catalog
                and during_catalog["index"]
                and "is_active"
                in during_catalog[
                    "index"
                ]["indexdef"]
                and COLUMN
                in during_catalog[
                    "index"
                ]["indexdef"]
            ),
        "rollback_executed":
            rollback_executed,
        "database_counts_unchanged":
            before == after,
        "alembic_version_unchanged":
            before["alembic_version"]
            == after["alembic_version"]
            == "058",
        "column_absent_after_rollback":
            after_catalog["column"] is None,
        "constraints_absent_after_rollback":
            after_catalog["constraints"] == [],
        "index_absent_after_rollback":
            after_catalog["index"] is None,
        "rehearsal_error_absent":
            rehearsal_error is None,
    }

    report = {
        "schema_version":
            "nwdp_runtime_lookup_native_geometry_rehearsal.v1",
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "healthy": all(checks.values()),
        "status": (
            "ROLLBACK_ONLY_REHEARSAL_PASSED"
            if all(checks.values())
            else "ROLLBACK_ONLY_REHEARSAL_FAILED"
        ),
        "mode":
            "CONFIRMED_TRANSACTIONAL_ROLLBACK_ONLY",
        "preflight": preflight,
        "before_database_counts": before,
        "after_database_counts": after,
        "before_catalog": before_catalog,
        "during_catalog": during_catalog,
        "after_catalog": after_catalog,
        "checks": checks,
        "rehearsal_error": rehearsal_error,
        "production_migration_difference": {
            "rehearsal_index_creation":
                "TRANSACTIONAL_CREATE_INDEX",
            "revision_059_index_creation":
                "CREATE_INDEX_CONCURRENTLY",
            "reason": (
                "Concurrent index creation cannot run "
                "inside a rollback transaction. Its "
                "syntax is covered by the migration "
                "static regression."
            ),
        },
        "guardrails": {
            "alembic_upgrade_executed": False,
            "alembic_version_written": False,
            "schema_changes_persisted": False,
            "geometry_backfilled": False,
            "runtime_rows_changed": False,
            "project_matches_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "lookup_endpoint_added": False,
            "lookup_api_enabled": False,
            "source_features_changed": False,
            "source_files_changed": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "migration_rehearsal_complete":
                all(checks.values()),
            "ready_for_migration_apply_proposal":
                all(checks.values()),
            "ready_for_geometry_backfill": False,
            "ready_for_lookup_enablement": False,
            "requires_separate_migration_authorization":
                True,
        },
    }

    options.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    options.output.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        report,
        indent=2,
        sort_keys=True,
        default=str,
    ))

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
