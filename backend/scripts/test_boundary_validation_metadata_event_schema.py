#!/usr/bin/env python3
"""Regression for boundary validation metadata event schema."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402

TABLE = "geography_boundary_validation_metadata_events"
FIXTURE_ID = "9a18114f-5350-5173-97df-f24e1e64c30b"
SOURCE_SHA256 = "a" * 64
PLAN_CHECKSUM = "b" * 64
ROLLBACK_TOKEN = "boundary-validation-event-schema-regression"


def check(condition: bool, label: str, value: Any = None) -> None:
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(json.dumps(value, indent=2, sort_keys=True, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def count_rows(connection) -> int:
    return int(
        connection.execute(
            text(f"select count(*) from {TABLE}")
        ).scalar_one()
    )


def expect_integrity_error(connection, statement, parameters, label) -> None:
    savepoint = connection.begin_nested()
    try:
        connection.execute(statement, parameters)
    except IntegrityError:
        savepoint.rollback()
        print(f"PASS {label}")
        return
    savepoint.rollback()
    raise AssertionError(label)


def insert_statement():
    return text(f"""
        insert into {TABLE} (
          id,
          source_feature_id,
          import_batch_id,
          source_system,
          state_or_ut,
          source_feature_index,
          source_sha256,
          plan_checksum,
          geometry_hash_algorithm,
          rollback_token,
          apply_status,
          before_values,
          planned_values,
          after_values,
          apply_report,
          rollback_report,
          metadata,
          applied_by,
          applied_at,
          is_active,
          version
        )
        values (
          cast(:id as uuid),
          cast(:source_feature_id as uuid),
          cast(:import_batch_id as uuid),
          :source_system,
          :state_or_ut,
          :source_feature_index,
          :source_sha256,
          :plan_checksum,
          :geometry_hash_algorithm,
          :rollback_token,
          :apply_status,
          cast(:before_values as jsonb),
          cast(:planned_values as jsonb),
          cast(:after_values as jsonb),
          cast(:apply_report as jsonb),
          cast(:rollback_report as jsonb),
          cast(:metadata as jsonb),
          :applied_by,
          now(),
          :is_active,
          'v1.0'
        )
    """)


def parameters(
    event_id: str,
    import_batch_id: str,
    *,
    source_sha256: str = SOURCE_SHA256,
    plan_checksum: str = PLAN_CHECKSUM,
    apply_status: str = "PLANNED",
    is_active: bool = False,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "source_feature_id": FIXTURE_ID,
        "import_batch_id": import_batch_id,
        "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
        "state_or_ut": "Andaman and Nicobar Islands",
        "source_feature_index": 0,
        "source_sha256": source_sha256,
        "plan_checksum": plan_checksum,
        "geometry_hash_algorithm":
            "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
        "rollback_token": ROLLBACK_TOKEN,
        "apply_status": apply_status,
        "before_values": json.dumps({
            "geometry_validation_status": "NOT_VALIDATED",
        }),
        "planned_values": json.dumps({
            "geometry_validation_status": "VALIDATED",
        }),
        "after_values": json.dumps({}),
        "apply_report": json.dumps({}),
        "rollback_report": json.dumps({}),
        "metadata": json.dumps({"regression": True}),
        "applied_by": "schema-regression",
        "is_active": is_active,
    }


def main() -> int:
    print("=" * 76)
    print("BOUNDARY VALIDATION METADATA EVENT SCHEMA REGRESSION")
    print("=" * 76)

    inspector = inspect(engine)

    check(inspector.has_table(TABLE), "Validation event table exists")

    columns = {
        column["name"]: column
        for column in inspector.get_columns(TABLE)
    }
    required_columns = {
        "id",
        "source_feature_id",
        "import_batch_id",
        "source_system",
        "state_or_ut",
        "source_feature_index",
        "source_sha256",
        "plan_checksum",
        "geometry_hash_algorithm",
        "rollback_token",
        "apply_status",
        "before_values",
        "planned_values",
        "after_values",
        "apply_report",
        "rollback_report",
        "metadata",
        "applied_by",
        "applied_at",
        "rolled_back_by",
        "rolled_back_at",
        "created_at",
        "updated_at",
        "is_active",
        "version",
    }

    check(
        required_columns == set(columns),
        "Validation event columns are exact",
        {
            "missing": sorted(required_columns - set(columns)),
            "unexpected": sorted(set(columns) - required_columns),
        },
    )

    for name in [
        "id",
        "source_feature_id",
        "import_batch_id",
        "source_sha256",
        "plan_checksum",
        "rollback_token",
        "apply_status",
        "before_values",
        "planned_values",
        "after_values",
        "is_active",
    ]:
        check(
            columns[name]["nullable"] is False,
            f"Required column is non-nullable: {name}",
        )

    indexes = {
        index["name"]: index
        for index in inspector.get_indexes(TABLE)
    }
    required_indexes = {
        "idx_gb_validation_events_source",
        "idx_gb_validation_events_batch",
        "idx_gb_validation_events_state",
        "idx_gb_validation_events_rollback",
        "uq_gb_validation_events_identity",
        "uq_gb_validation_events_active_source",
    }
    check(
        required_indexes.issubset(indexes),
        "Required event indexes exist",
        sorted(indexes),
    )
    check(
        indexes["uq_gb_validation_events_identity"]["unique"] is True,
        "Apply identity index is unique",
    )
    check(
        indexes["uq_gb_validation_events_active_source"]["unique"] is True,
        "Active source index is unique",
    )

    foreign_keys = inspector.get_foreign_keys(TABLE)
    referred_tables = {
        foreign_key["referred_table"]
        for foreign_key in foreign_keys
    }
    check(
        "geography_boundary_source_features" in referred_tables,
        "Source feature foreign key exists",
    )
    check(
        "geography_boundary_import_batches" in referred_tables,
        "Import batch foreign key exists",
    )

    with engine.connect() as baseline_connection:
        baseline = count_rows(baseline_connection)

    with engine.connect() as connection:
        transaction = connection.begin()

        fixture = connection.execute(text("""
            select import_batch_id::text
            from geography_boundary_source_features
            where id = cast(:fixture_id as uuid)
        """), {"fixture_id": FIXTURE_ID}).mappings().one()

        import_batch_id = fixture["import_batch_id"]
        first_id = str(uuid.uuid4())

        connection.execute(
            insert_statement(),
            parameters(first_id, import_batch_id),
        )
        check(
            count_rows(connection) == baseline + 1,
            "Planned inactive event can be inserted",
        )

        expect_integrity_error(
            connection,
            insert_statement(),
            parameters(str(uuid.uuid4()), import_batch_id),
            "Duplicate apply identity is rejected",
        )

        expect_integrity_error(
            connection,
            insert_statement(),
            parameters(
                str(uuid.uuid4()),
                import_batch_id,
                plan_checksum="c" * 64,
                apply_status="PLANNED",
                is_active=True,
            ),
            "Active planned event violates status constraint",
        )

        connection.execute(text(f"""
            update {TABLE}
            set
              apply_status = 'APPLIED',
              is_active = true,
              after_values = cast(:after_values as jsonb)
            where id = cast(:event_id as uuid)
        """), {
            "event_id": first_id,
            "after_values": json.dumps({
                "geometry_validation_status": "VALIDATED",
            }),
        })

        check(
            connection.execute(text(f"""
                select apply_status = 'APPLIED' and is_active = true
                from {TABLE}
                where id = cast(:event_id as uuid)
            """), {"event_id": first_id}).scalar_one() is True,
            "Applied event may be active",
        )

        expect_integrity_error(
            connection,
            insert_statement(),
            parameters(
                str(uuid.uuid4()),
                import_batch_id,
                source_sha256="d" * 64,
                plan_checksum="e" * 64,
                apply_status="APPLIED",
                is_active=True,
            ),
            "Second active event for source feature is rejected",
        )

        transaction.rollback()

    with engine.connect() as connection:
        check(
            count_rows(connection) == baseline,
            "Regression transaction leaves event count unchanged",
        )

    print("=" * 76)
    print(
        "BOUNDARY VALIDATION METADATA EVENT SCHEMA REGRESSION PASSED"
    )
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
