#!/usr/bin/env python3
"""Disposable PostgreSQL verification for migration 071.

This script is destructive within the explicitly named disposable database. It
never creates or drops a database and never prints its URL or credentials.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url


ROOT = Path(__file__).resolve().parents[1]
DATABASE_ENV = "MIGRATION_071_DATABASE_URL"
APPROVAL_ENV = "MIGRATION_071_DISPOSABLE_APPROVED"
TEMPLATE_ENV = "MIGRATION_071_CLEAN_TEMPLATE"
DATABASE_NAME = re.compile(r"^agrios_migration_071_disposable_[a-z0-9_]+$")

ACTIVITY_ID = UUID("71000000-0000-0000-0000-000000000001")
CYCLE_ID = UUID("71000000-0000-0000-0000-000000000002")
FARMER_ID = UUID("71000000-0000-0000-0000-000000000003")
ACTOR_ID = UUID("71000000-0000-0000-0000-000000000004")
EVENT_ID = UUID("71000000-0000-0000-0000-000000000005")
AUDIT_ID = UUID("71000000-0000-0000-0000-000000000006")
TENANT_ID = "migration-071-disposable"


class VerificationFailure(RuntimeError):
    pass


def check(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationFailure(code)


def approved_url() -> str:
    check(os.environ.get(APPROVAL_ENV) == "YES", "DISPOSABLE_APPROVAL_REQUIRED")
    check(os.environ.get(TEMPLATE_ENV) == "template0", "TEMPLATE0_PROVISIONING_REQUIRED")
    raw = os.environ.get(DATABASE_ENV, "")
    check(bool(raw), "DISPOSABLE_DATABASE_URL_REQUIRED")
    url = make_url(raw)
    check(
        url.drivername in {"postgresql", "postgresql+psycopg2"},
        "PSYCOPG2_POSTGRESQL_REQUIRED",
    )
    check(
        url.host in {"localhost", "127.0.0.1", "::1"},
        "LOCAL_POSTGRESQL_REQUIRED",
    )
    check(url.port == 5432, "LOCAL_POSTGRESQL_PORT_5432_REQUIRED")
    check(not url.query, "DATABASE_OPTIONS_REJECTED")
    check(bool(url.username), "DATABASE_USER_REQUIRED")
    check(bool(url.database and DATABASE_NAME.fullmatch(url.database)), "DATABASE_NAME_REJECTED")
    return raw


def configure_application_environment(database_url: str) -> None:
    url = make_url(database_url)
    os.environ["APP_ENVIRONMENT"] = "test"
    os.environ["DB_USER"] = url.username or ""
    os.environ["DB_PASSWORD"] = url.password or ""
    os.environ["DB_HOST"] = url.host or ""
    os.environ["DB_PORT"] = str(url.port or 5432)
    os.environ["DB_NAME"] = url.database or ""
    os.environ.pop("DB_SSLMODE", None)


def alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@contextmanager
def verified_connection(engine: Engine, expected_name: str):
    with engine.connect() as connection:
        admit_connection(connection, expected_name, require_empty=False)
        try:
            yield connection
        finally:
            connection.rollback()


def revision(engine: Engine, expected_name: str) -> str | None:
    with verified_connection(engine, expected_name) as connection:
        return connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one_or_none()


def admit_connection(connection, expected_name: str, *, require_empty: bool) -> None:
    connection.execute(text("SET SESSION search_path TO public, pg_catalog"))
    connection.execute(text("SET SESSION lock_timeout TO '5s'"))
    connection.execute(text("SET SESSION statement_timeout TO '120s'"))
    connection.execute(text("SET SESSION idle_in_transaction_session_timeout TO '30s'"))

    current_name = connection.execute(text("SELECT current_database()" )).scalar_one()
    check(current_name == expected_name, "CONNECTED_DATABASE_MISMATCH")
    server_address, server_port = connection.execute(
        text("SELECT host(inet_server_addr()), inet_server_port()")
    ).one()
    check(server_address is not None, "TCP_SERVER_ADDRESS_REQUIRED")
    try:
        actual_address = ipaddress.ip_address(server_address)
    except ValueError as exc:
        raise VerificationFailure("SERVER_ADDRESS_INVALID") from exc
    check(actual_address.is_loopback, "ACTUAL_SERVER_NOT_LOOPBACK")
    check(server_port == 5432, "ACTUAL_SERVER_PORT_MISMATCH")
    recovery = connection.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
    check(recovery is False, "PRIMARY_DATABASE_REQUIRED")
    search_path = connection.execute(text("SELECT current_schemas(false)" )).scalar_one()
    check(search_path == ["public", "pg_catalog"], "SEARCH_PATH_MISMATCH")
    available_extensions = set(
        connection.execute(
            text(
                "SELECT name FROM pg_available_extensions "
                "WHERE name IN ('postgis', 'pg_trgm')"
            )
        ).scalars()
    )
    check(available_extensions == {"postgis", "pg_trgm"}, "REQUIRED_EXTENSIONS_UNAVAILABLE")

    if require_empty:
        unexpected_schemas = connection.execute(
            text(
                "SELECT count(*) FROM pg_namespace "
                "WHERE nspname <> 'public' "
                "AND nspname <> 'information_schema' "
                "AND nspname NOT LIKE 'pg\\_%' ESCAPE '\\'"
            )
        ).scalar_one()
        public_relations = connection.execute(
            text(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public'"
            )
        ).scalar_one()
        public_types = connection.execute(
            text(
                "SELECT count(*) FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public'"
            )
        ).scalar_one()
        public_routines = connection.execute(
            text(
                "SELECT count(*) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public'"
            )
        ).scalar_one()
        unexpected_extensions = connection.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'")
        ).scalar_one()
        event_triggers = connection.execute(
            text("SELECT count(*) FROM pg_event_trigger")
        ).scalar_one()
        check(unexpected_schemas == 0, "UNEXPECTED_USER_SCHEMA")
        check(public_relations == 0, "UNEXPECTED_PUBLIC_RELATION")
        check(public_types == 0, "UNEXPECTED_PUBLIC_TYPE")
        check(public_routines == 0, "UNEXPECTED_PUBLIC_ROUTINE")
        check(unexpected_extensions == 0, "UNEXPECTED_EXTENSION")
        check(event_triggers == 0, "UNEXPECTED_EVENT_TRIGGER")

    connection.commit()


def run_alembic(
    engine: Engine,
    config: Config,
    expected_name: str,
    action: str,
    target: str,
    *,
    require_empty: bool = False,
) -> None:
    with engine.connect() as connection:
        admit_connection(connection, expected_name, require_empty=require_empty)
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = "public"
        try:
            if action == "upgrade":
                command.upgrade(config, target)
            elif action == "downgrade":
                command.downgrade(config, target)
            else:
                raise VerificationFailure("ALEMBIC_ACTION_INVALID")
        finally:
            config.attributes.pop("connection", None)
            config.attributes.pop("version_table_schema", None)


def insert_retained_activity(engine: Engine, expected_name: str) -> dict[str, Any]:
    now = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)
    with verified_connection(engine, expected_name) as connection:
        connection.execute(
            text(
                "INSERT INTO crop_activities ("
                "id, crop_cycle_id, tenant_id, farmer_id, activity_type, "
                "activity_date, logged_by, notes, created_at, updated_at"
                ") VALUES ("
                ":id, :cycle, :tenant, :farmer, 'OTHER', :activity_date, "
                ":actor, 'migration-071-sentinel', :created_at, :updated_at"
                ")"
            ),
            {
                "id": ACTIVITY_ID,
                "cycle": CYCLE_ID,
                "tenant": TENANT_ID,
                "farmer": FARMER_ID,
                "activity_date": date(2026, 11, 17),
                "actor": ACTOR_ID,
                "created_at": now,
                "updated_at": now,
            },
        )
        snapshot = connection.execute(
            text("SELECT to_jsonb(a) FROM crop_activities a WHERE id = :id"),
            {"id": ACTIVITY_ID},
        ).scalar_one()
        connection.commit()
        return snapshot


def activity_snapshot(
    engine: Engine,
    expected_name: str,
    *,
    strip_071: bool,
) -> dict[str, Any]:
    with verified_connection(engine, expected_name) as connection:
        value = connection.execute(
            text("SELECT to_jsonb(a) FROM crop_activities a WHERE id = :id"),
            {"id": ACTIVITY_ID},
        ).scalar_one()
    if strip_071:
        value = dict(value)
        value.pop("irrigation_source")
        value.pop("duration_hours")
    return value


def assert_071_schema(
    engine: Engine,
    expected_name: str,
    expected_binding_counts: tuple[int, int] = (0, 0),
) -> None:
    def expect_column(
        columns: dict[str, dict[str, Any]],
        name: str,
        type_name: str,
        nullable: bool,
        *,
        length: int | None = None,
        precision: int | None = None,
        scale: int | None = None,
        timezone: bool | None = None,
    ) -> None:
        column = columns.get(name)
        check(column is not None, f"COLUMN_MISSING_{name}")
        if timezone is None:
            check(str(column["type"]).upper() == type_name, f"COLUMN_TYPE_{name}")
        else:
            check(isinstance(column["type"], DateTime), f"COLUMN_TYPE_{name}")
            check(column["type"].timezone is timezone, f"COLUMN_TIMEZONE_{name}")
        check(column["nullable"] is nullable, f"COLUMN_NULLABLE_{name}")
        check(column["default"] is None, f"COLUMN_DEFAULT_{name}")
        if length is not None:
            check(column["type"].length == length, f"COLUMN_LENGTH_{name}")
        if precision is not None:
            check(column["type"].precision == precision, f"COLUMN_PRECISION_{name}")
            check(column["type"].scale == scale, f"COLUMN_SCALE_{name}")

    with verified_connection(engine, expected_name) as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names(schema="public"))
        check("crop_activity_command_bindings" in tables, "COMMAND_TABLE_MISSING")
        check("crop_activity_sync_event_bindings" in tables, "EVENT_TABLE_MISSING")

        command_columns = {
            column["name"]: column
            for column in inspector.get_columns(
                "crop_activity_command_bindings", schema="public"
            )
        }
        event_columns = {
            column["name"]: column
            for column in inspector.get_columns(
                "crop_activity_sync_event_bindings", schema="public"
            )
        }
        activity_columns = {
            column["name"]: column
            for column in inspector.get_columns("crop_activities", schema="public")
        }
        check(
            set(command_columns)
            == {
                "activity_id", "tenant_id", "actor_id", "farmer_id",
                "crop_cycle_id", "origin_kind", "origin_event_id",
                "intent_version", "intent_canonical", "intent_sha256",
                "resolved_stage_id", "result_version", "result_payload",
                "audit_correlation_id", "created_at",
            },
            "COMMAND_COLUMN_SET_MISMATCH",
        )
        check(
            set(event_columns)
            == {
                "event_id", "tenant_id", "actor_id", "activity_id",
                "intent_version", "intent_canonical", "intent_sha256",
                "outcome", "created_at",
            },
            "EVENT_COLUMN_SET_MISMATCH",
        )

        for name in (
            "activity_id", "actor_id", "farmer_id", "crop_cycle_id",
            "audit_correlation_id",
        ):
            expect_column(command_columns, name, "UUID", False)
        expect_column(command_columns, "tenant_id", "VARCHAR(50)", False, length=50)
        expect_column(command_columns, "origin_kind", "VARCHAR(10)", False, length=10)
        expect_column(command_columns, "origin_event_id", "UUID", True)
        expect_column(command_columns, "intent_version", "VARCHAR(40)", False, length=40)
        expect_column(command_columns, "intent_canonical", "TEXT", False)
        expect_column(command_columns, "intent_sha256", "CHAR(64)", False, length=64)
        expect_column(command_columns, "resolved_stage_id", "UUID", True)
        expect_column(command_columns, "result_version", "VARCHAR(40)", False, length=40)
        expect_column(command_columns, "result_payload", "JSONB", False)
        expect_column(
            command_columns,
            "created_at",
            "TIMESTAMP",
            False,
            timezone=True,
        )

        for name in ("event_id", "actor_id", "activity_id"):
            expect_column(event_columns, name, "UUID", False)
        expect_column(event_columns, "tenant_id", "VARCHAR(50)", False, length=50)
        expect_column(event_columns, "intent_version", "VARCHAR(40)", False, length=40)
        expect_column(event_columns, "intent_canonical", "TEXT", False)
        expect_column(event_columns, "intent_sha256", "CHAR(64)", False, length=64)
        expect_column(event_columns, "outcome", "VARCHAR(20)", False, length=20)
        expect_column(
            event_columns,
            "created_at",
            "TIMESTAMP",
            False,
            timezone=True,
        )

        expect_column(activity_columns, "irrigation_source", "VARCHAR(100)", True, length=100)
        expect_column(
            activity_columns,
            "duration_hours",
            "NUMERIC(10, 2)",
            True,
            precision=10,
            scale=2,
        )

        command_pk = inspector.get_pk_constraint(
            "crop_activity_command_bindings", schema="public"
        )
        event_pk = inspector.get_pk_constraint(
            "crop_activity_sync_event_bindings", schema="public"
        )
        check(command_pk["constrained_columns"] == ["activity_id"], "COMMAND_PK_MISMATCH")
        check(event_pk["constrained_columns"] == ["event_id"], "EVENT_PK_MISMATCH")

        command_fks = {
            item["name"]: item for item in inspector.get_foreign_keys(
                "crop_activity_command_bindings", schema="public"
            )
        }
        event_fks = {
            item["name"]: item for item in inspector.get_foreign_keys(
                "crop_activity_sync_event_bindings", schema="public"
            )
        }

        def expect_fk(
            foreign_keys: dict[str, dict[str, Any]],
            name: str,
            local: list[str],
            referred_table: str,
            remote: list[str],
        ) -> None:
            foreign_key = foreign_keys.get(name)
            check(foreign_key is not None, f"FK_MISSING_{name}")
            check(foreign_key["constrained_columns"] == local, f"FK_LOCAL_{name}")
            check(foreign_key["referred_schema"] in {None, "public"}, f"FK_SCHEMA_{name}")
            check(foreign_key["referred_table"] == referred_table, f"FK_TABLE_{name}")
            check(foreign_key["referred_columns"] == remote, f"FK_REMOTE_{name}")
            check(foreign_key["options"].get("ondelete") == "RESTRICT", f"FK_DELETE_{name}")

        expect_fk(
            command_fks,
            "fk_crop_activity_command_binding_activity",
            ["activity_id"],
            "crop_activities",
            ["id"],
        )
        expect_fk(
            event_fks,
            "fk_crop_activity_sync_event_binding_event",
            ["event_id"],
            "sync_processed_events",
            ["event_id"],
        )
        expect_fk(
            event_fks,
            "fk_crop_activity_sync_event_binding_activity",
            ["activity_id"],
            "crop_activity_command_bindings",
            ["activity_id"],
        )

        check_expressions = dict(
            connection.execute(
                text(
                    "SELECT con.conname, pg_get_expr(con.conbin, con.conrelid) "
                    "FROM pg_constraint con "
                    "JOIN pg_class rel ON rel.oid = con.conrelid "
                    "JOIN pg_namespace n ON n.oid = rel.relnamespace "
                    "WHERE n.nspname = 'public' AND con.contype = 'c' "
                    "AND rel.relname IN ("
                    "'crop_activity_command_bindings', "
                    "'crop_activity_sync_event_bindings')"
                )
            ).all()
        )

        def evaluate_check(name: str, values_sql: str, parameters: dict[str, Any]) -> bool:
            expression = check_expressions.get(name)
            check(expression is not None, f"CHECK_MISSING_{name}")
            return bool(
                connection.execute(
                    text(f"SELECT ({expression}) FROM ({values_sql}) AS candidate"),
                    parameters,
                ).scalar_one()
            )

        zero_uuid = UUID(int=0)
        for kind, event_id, expected in (
            ("DIRECT", None, True),
            ("DIRECT", zero_uuid, False),
            ("SYNC", zero_uuid, True),
            ("SYNC", None, False),
            ("OTHER", None, False),
        ):
            parameters = {"kind": kind, "event": event_id}
            check(
                evaluate_check(
                    "ck_crop_activity_command_binding_origin_kind",
                    "SELECT CAST(:kind AS varchar(10)) AS origin_kind, "
                    "CAST(:event AS uuid) AS origin_event_id",
                    parameters,
                ) is (kind in {"DIRECT", "SYNC"}),
                "ORIGIN_KIND_CHECK_SEMANTICS",
            )
            check(
                evaluate_check(
                    "ck_crop_activity_command_binding_origin_event",
                    "SELECT CAST(:kind AS varchar(10)) AS origin_kind, "
                    "CAST(:event AS uuid) AS origin_event_id",
                    parameters,
                ) is expected,
                "ORIGIN_EVENT_CHECK_SEMANTICS",
            )
        for value, expected in (("COMMITTED", True), ("FAILED", False)):
            check(
                evaluate_check(
                    "ck_crop_activity_sync_event_binding_outcome",
                    "SELECT CAST(:outcome AS varchar(20)) AS outcome",
                    {"outcome": value},
                ) is expected,
                "OUTCOME_CHECK_SEMANTICS",
            )

        command_indexes = {
            item["name"]: item for item in inspector.get_indexes(
                "crop_activity_command_bindings", schema="public"
            )
        }
        check(
            command_indexes.get("idx_crop_activity_command_binding_tenant_cycle", {}).get("column_names")
            == ["tenant_id", "crop_cycle_id"],
            "TENANT_CYCLE_INDEX_MISMATCH",
        )
        check(
            command_indexes.get("idx_crop_activity_command_binding_tenant_event", {}).get("column_names")
            == ["tenant_id", "origin_event_id"],
            "TENANT_EVENT_INDEX_MISMATCH",
        )
        for name in (
            "idx_crop_activity_command_binding_tenant_cycle",
            "idx_crop_activity_command_binding_tenant_event",
        ):
            index = command_indexes.get(name, {})
            check(index.get("unique") is False, f"INDEX_UNIQUE_{name}")
            check(
                index.get("dialect_options", {}).get("postgresql_where") is None,
                f"INDEX_PARTIAL_{name}",
            )

        event_unique = {
            item["name"]: item for item in inspector.get_unique_constraints(
                "crop_activity_sync_event_bindings", schema="public"
            )
        }
        check(
            event_unique.get("uq_crop_activity_sync_event_binding_activity", {}).get("column_names")
            == ["activity_id"],
            "ACTIVITY_UNIQUE_MISMATCH",
        )

        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM public.crop_activity_command_bindings), "
                "(SELECT count(*) FROM public.crop_activity_sync_event_bindings)"
            )
        ).one()
    check(tuple(counts) == expected_binding_counts, "BINDING_COUNTS_MISMATCH")


def assert_070_schema(engine: Engine, expected_name: str) -> None:
    with verified_connection(engine, expected_name) as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names(schema="public"))
        check("crop_activity_command_bindings" not in tables, "COMMAND_TABLE_RETAINED")
        check("crop_activity_sync_event_bindings" not in tables, "EVENT_TABLE_RETAINED")
        activity_columns = {
            column["name"] for column in inspector.get_columns(
                "crop_activities", schema="public"
            )
        }
        check("irrigation_source" not in activity_columns, "IRRIGATION_SOURCE_RETAINED")
        check("duration_hours" not in activity_columns, "DURATION_HOURS_RETAINED")


def insert_bindings(engine: Engine, expected_name: str) -> None:
    now = datetime(2026, 11, 17, 0, 1, tzinfo=timezone.utc)
    canonical = '{"fixture":"migration-071"}'
    digest = "0" * 64
    with verified_connection(engine, expected_name) as connection:
        connection.execute(
            text(
                "INSERT INTO sync_processed_events ("
                "event_id, tenant_id, actor_id, entity_type, entity_id, operation, "
                "server_version, processed_at, status"
                ") VALUES ("
                ":event, :tenant, :actor, 'crop_activity', :activity, 'CREATE', "
                "1, :created_at, 'COMMITTED')"
            ),
            {
                "event": EVENT_ID,
                "tenant": TENANT_ID,
                "actor": ACTOR_ID,
                "activity": ACTIVITY_ID,
                "created_at": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO crop_activity_command_bindings ("
                "activity_id, tenant_id, actor_id, farmer_id, crop_cycle_id, "
                "origin_kind, origin_event_id, intent_version, intent_canonical, "
                "intent_sha256, result_version, result_payload, "
                "audit_correlation_id, created_at"
                ") VALUES ("
                ":activity, :tenant, :actor, :farmer, :cycle, 'SYNC', :event, "
                "'crop_activity_intent.v1', :canonical, :digest, "
                "'crop_activity_result.v1', CAST(:result AS jsonb), :audit, :created_at)"
            ),
            {
                "activity": ACTIVITY_ID,
                "tenant": TENANT_ID,
                "actor": ACTOR_ID,
                "farmer": FARMER_ID,
                "cycle": CYCLE_ID,
                "event": EVENT_ID,
                "canonical": canonical,
                "digest": digest,
                "result": json.dumps({"activity_id": str(ACTIVITY_ID)}),
                "audit": AUDIT_ID,
                "created_at": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO crop_activity_sync_event_bindings ("
                "event_id, tenant_id, actor_id, activity_id, intent_version, "
                "intent_canonical, intent_sha256, outcome, created_at"
                ") VALUES ("
                ":event, :tenant, :actor, :activity, 'crop_activity_intent.v1', "
                ":canonical, :digest, 'COMMITTED', :created_at)"
            ),
            {
                "event": EVENT_ID,
                "tenant": TENANT_ID,
                "actor": ACTOR_ID,
                "activity": ACTIVITY_ID,
                "canonical": canonical,
                "digest": digest,
                "created_at": now,
            },
        )
        connection.commit()


def delete_bindings(engine: Engine, expected_name: str) -> None:
    with verified_connection(engine, expected_name) as connection:
        event_result = connection.execute(
            text(
                "DELETE FROM crop_activity_sync_event_bindings "
                "WHERE event_id = :event AND activity_id = :activity"
            ),
            {"event": EVENT_ID, "activity": ACTIVITY_ID},
        )
        command_result = connection.execute(
            text(
                "DELETE FROM crop_activity_command_bindings "
                "WHERE activity_id = :activity AND origin_event_id = :event"
            ),
            {"activity": ACTIVITY_ID, "event": EVENT_ID},
        )
        processed_result = connection.execute(
            text("DELETE FROM sync_processed_events WHERE event_id = :event"),
            {"event": EVENT_ID},
        )
        check(event_result.rowcount == 1, "EVENT_BINDING_DELETE_COUNT")
        check(command_result.rowcount == 1, "COMMAND_BINDING_DELETE_COUNT")
        check(processed_result.rowcount == 1, "PROCESSED_EVENT_DELETE_COUNT")
        connection.commit()


def binding_snapshot(engine: Engine, expected_name: str) -> dict[str, Any]:
    with verified_connection(engine, expected_name) as connection:
        processed = connection.execute(
            text("SELECT to_jsonb(e) FROM sync_processed_events e WHERE event_id = :event"),
            {"event": EVENT_ID},
        ).scalar_one()
        command_binding = connection.execute(
            text(
                "SELECT to_jsonb(b) FROM crop_activity_command_bindings b "
                "WHERE activity_id = :activity"
            ),
            {"activity": ACTIVITY_ID},
        ).scalar_one()
        event_binding = connection.execute(
            text(
                "SELECT to_jsonb(b) FROM crop_activity_sync_event_bindings b "
                "WHERE event_id = :event"
            ),
            {"event": EVENT_ID},
        ).scalar_one()
    return {
        "processed_event": processed,
        "command_binding": command_binding,
        "event_binding": event_binding,
    }


def set_irrigation_field(
    engine: Engine,
    expected_name: str,
    column: str,
    value: Any,
) -> None:
    check(column in {"irrigation_source", "duration_hours"}, "IRRIGATION_COLUMN_INVALID")
    with verified_connection(engine, expected_name) as connection:
        result = connection.execute(
            text(f"UPDATE crop_activities SET {column} = :value WHERE id = :id"),
            {"value": value, "id": ACTIVITY_ID},
        )
        check(result.rowcount == 1, f"{column.upper()}_UPDATE_COUNT")
        connection.commit()


def expect_downgrade_refusal(
    config: Config,
    engine: Engine,
    expected_name: str,
    code: str,
    expected_binding_counts: tuple[int, int],
    expected_activity: dict[str, Any],
    expected_bindings: dict[str, Any] | None = None,
) -> None:
    try:
        run_alembic(engine, config, expected_name, "downgrade", "070")
    except RuntimeError as exc:
        check("071_DOWNGRADE_BLOCKED" in str(exc), f"{code}_WRONG_ERROR")
    else:
        raise VerificationFailure(f"{code}_NOT_REFUSED")
    check(revision(engine, expected_name) == "071", f"{code}_REVISION_CHANGED")
    assert_071_schema(engine, expected_name, expected_binding_counts)
    check(
        activity_snapshot(engine, expected_name, strip_071=False) == expected_activity,
        f"{code}_ACTIVITY_CHANGED",
    )
    if expected_bindings is not None:
        check(
            binding_snapshot(engine, expected_name) == expected_bindings,
            f"{code}_BINDINGS_CHANGED",
        )


def migration_chain_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "alembic/versions").glob("*.py")):
        name = path.name.encode("utf-8")
        body = path.read_bytes()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def main() -> None:
    phase = "guard"
    engine: Engine | None = None
    try:
        database_url = approved_url()
        url = make_url(database_url)
        database_name = url.database or ""
        configure_application_environment(database_url)
        engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
        config = alembic_config(database_url)
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        migration_sha = hashlib.sha256(
            (ROOT / "alembic/versions/071_add_crop_activity_command_bindings.py").read_bytes()
        ).hexdigest()
        environment_sha = hashlib.sha256((ROOT / "alembic/env.py").read_bytes()).hexdigest()
        chain_sha = migration_chain_sha256()
        print(
            "MIGRATION_071_SOURCE_SHA256 "
            f"script={script_sha} migration={migration_sha} "
            f"environment={environment_sha} chain={chain_sha}"
        )

        phase = "upgrade-070"
        run_alembic(
            engine,
            config,
            database_name,
            "upgrade",
            "070",
            require_empty=True,
        )
        print("MIGRATION_071_EMPTY_DATABASE_OK")
        check(revision(engine, database_name) == "070", "REVISION_070_REQUIRED")
        before = insert_retained_activity(engine, database_name)
        print("MIGRATION_071_BASELINE_070_OK")

        phase = "upgrade-071"
        run_alembic(engine, config, database_name, "upgrade", "071")
        check(revision(engine, database_name) == "071", "REVISION_071_REQUIRED")
        assert_071_schema(engine, database_name)
        check(
            activity_snapshot(engine, database_name, strip_071=True) == before,
            "UPGRADE_CHANGED_ACTIVITY",
        )
        upgraded = activity_snapshot(engine, database_name, strip_071=False)
        check(upgraded["irrigation_source"] is None, "IRRIGATION_SOURCE_DEFAULT_NOT_NULL")
        check(upgraded["duration_hours"] is None, "DURATION_HOURS_DEFAULT_NOT_NULL")
        print("MIGRATION_071_UPGRADE_OK")

        phase = "clean-downgrade"
        run_alembic(engine, config, database_name, "downgrade", "070")
        check(
            revision(engine, database_name) == "070",
            "CLEAN_DOWNGRADE_REVISION_MISMATCH",
        )
        assert_070_schema(engine, database_name)
        check(
            activity_snapshot(engine, database_name, strip_071=False) == before,
            "DOWNGRADE_CHANGED_ACTIVITY",
        )
        print("MIGRATION_071_CLEAN_DOWNGRADE_OK")

        phase = "normal-reopen"
        run_alembic(engine, config, database_name, "upgrade", "071")
        engine.dispose()
        engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
        check(revision(engine, database_name) == "071", "REOPEN_REVISION_MISMATCH")
        assert_071_schema(engine, database_name)
        reopened = activity_snapshot(engine, database_name, strip_071=False)
        check(reopened["irrigation_source"] is None, "REOPEN_IRRIGATION_SOURCE_NOT_NULL")
        check(reopened["duration_hours"] is None, "REOPEN_DURATION_HOURS_NOT_NULL")
        check(
            activity_snapshot(engine, database_name, strip_071=True) == before,
            "REOPEN_CHANGED_ACTIVITY",
        )
        print("MIGRATION_071_REOPEN_OK")

        phase = "binding-refusal"
        insert_bindings(engine, database_name)
        bindings_before = binding_snapshot(engine, database_name)
        binding_activity_before = activity_snapshot(engine, database_name, strip_071=False)
        expect_downgrade_refusal(
            config,
            engine,
            database_name,
            "BINDING_DOWNGRADE",
            (1, 1),
            binding_activity_before,
            bindings_before,
        )
        print("MIGRATION_071_BINDING_DOWNGRADE_REFUSED")
        delete_bindings(engine, database_name)

        phase = "irrigation-source-refusal"
        set_irrigation_field(engine, database_name, "irrigation_source", "CANAL")
        source_before = activity_snapshot(engine, database_name, strip_071=False)
        check(source_before["irrigation_source"] == "CANAL", "SOURCE_SEED_MISMATCH")
        check(source_before["duration_hours"] is None, "SOURCE_SEED_DURATION_NOT_NULL")
        expect_downgrade_refusal(
            config,
            engine,
            database_name,
            "IRRIGATION_SOURCE_DOWNGRADE",
            (0, 0),
            source_before,
        )
        print("MIGRATION_071_IRRIGATION_SOURCE_DOWNGRADE_REFUSED")
        set_irrigation_field(engine, database_name, "irrigation_source", None)

        phase = "duration-refusal"
        set_irrigation_field(engine, database_name, "duration_hours", "1.25")
        duration_before = activity_snapshot(engine, database_name, strip_071=False)
        check(duration_before["irrigation_source"] is None, "DURATION_SEED_SOURCE_NOT_NULL")
        check(str(duration_before["duration_hours"]) == "1.25", "DURATION_SEED_MISMATCH")
        expect_downgrade_refusal(
            config,
            engine,
            database_name,
            "DURATION_DOWNGRADE",
            (0, 0),
            duration_before,
        )
        print("MIGRATION_071_DURATION_DOWNGRADE_REFUSED")
        set_irrigation_field(engine, database_name, "duration_hours", None)

        phase = "final-clean-reopen"
        run_alembic(engine, config, database_name, "downgrade", "070")
        assert_070_schema(engine, database_name)
        check(
            activity_snapshot(engine, database_name, strip_071=False) == before,
            "FINAL_DOWNGRADE_CHANGED_ACTIVITY",
        )
        run_alembic(engine, config, database_name, "upgrade", "071")
        engine.dispose()
        engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
        assert_071_schema(engine, database_name)
        check(
            activity_snapshot(engine, database_name, strip_071=True) == before,
            "FINAL_REOPEN_CHANGED_ACTIVITY",
        )
        final_activity = activity_snapshot(engine, database_name, strip_071=False)
        check(final_activity["irrigation_source"] is None, "FINAL_SOURCE_NOT_NULL")
        check(final_activity["duration_hours"] is None, "FINAL_DURATION_NOT_NULL")
        check(revision(engine, database_name) == "071", "FINAL_REVISION_MISMATCH")
        print("MIGRATION_071_POSTGRES_OK")
    except Exception as exc:
        print(
            f"MIGRATION_071_FAILED phase={phase} type={type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
