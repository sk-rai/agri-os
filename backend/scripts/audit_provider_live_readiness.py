#!/usr/bin/env python3
"""Audit live provider readiness without making external calls or printing secrets.

This is read-only. It checks provider config posture, env-var presence, approval
gates, runtime policy, and whether demo/live testing can be enabled safely.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal

EXPECTED_ENV_KEYS = {
    "weather": [
        "OPENWEATHER_API_KEY",
        "WEATHER_API_KEY",
        "OPEN_METEO_API_KEY",
    ],
    "soil": [
        "SOILGRIDS_API_KEY",
        "SLUSI_API_KEY",
        "GOOGLE_EARTH_ENGINE_SERVICE_ACCOUNT",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ],
    "geocoding": [
        "GOOGLE_MAPS_API_KEY",
        "BING_MAPS_API_KEY",
        "MAPBOX_API_KEY",
    ],
}

TABLE_CANDIDATES = [
    "weather_providers",
    "weather_provider_configs",
    "soil_enrichment_provider_configs",
    "provider_configs",
    "external_provider_configs",
]


def env_presence() -> dict:
    result = {}
    for group, keys in EXPECTED_ENV_KEYS.items():
        result[group] = {
            key: {
                "present": bool(os.getenv(key)),
                "value_printed": False,
            }
            for key in keys
        }
    return result


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def row_count(db, table_name: str) -> int:
    return int(db.execute(text(f"select count(*) from {table_name}")).scalar() or 0)


def safe_column_list(db, table_name: str) -> list[str]:
    rows = db.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_name = :table_name
            order by ordinal_position
        """),
        {"table_name": table_name},
    ).all()
    return [row[0] for row in rows]


def provider_table_summaries(db) -> list[dict]:
    summaries = []
    for table in TABLE_CANDIDATES:
        exists = table_exists(db, table)
        summary = {
            "table": table,
            "exists": exists,
            "row_count": 0,
            "columns": [],
            "safe_summary": [],
        }
        if not exists:
            summaries.append(summary)
            continue

        columns = safe_column_list(db, table)
        summary["columns"] = columns
        summary["row_count"] = row_count(db, table)

        printable_columns = [
            col for col in [
                "tenant_id",
                "provider",
                "provider_name",
                "provider_type",
                "service_type",
                "status",
                "is_active",
                "live_execution_enabled",
                "live_execution_status",
                "demo_mode",
                "timeout_seconds",
                "max_retries",
                "rate_limit_window_seconds",
                "max_requests_per_window",
                "updated_at",
            ]
            if col in columns
        ]

        if printable_columns and summary["row_count"] > 0:
            selected = ", ".join(printable_columns)
            rows = db.execute(text(f"select {selected} from {table} limit 20")).mappings().all()
            summary["safe_summary"] = [dict(row) for row in rows]

        summaries.append(summary)

    return summaries


def classify_readiness(env: dict, tables: list[dict]) -> dict:
    any_weather_key = any(item["present"] for item in env["weather"].values())
    any_soil_key = any(item["present"] for item in env["soil"].values())
    any_geocoding_key = any(item["present"] for item in env["geocoding"].values())

    existing_provider_tables = [table for table in tables if table["exists"]]
    live_enabled_rows = []
    blocked_rows = []

    for table in existing_provider_tables:
        for row in table.get("safe_summary") or []:
            if row.get("live_execution_enabled") is True:
                live_enabled_rows.append({"table": table["table"], "row": row})
            if row.get("live_execution_status") in {"BLOCKED_UNTIL_APPROVED", "DISABLED", "NOT_CONFIGURED"}:
                blocked_rows.append({"table": table["table"], "row": row})

    return {
        "weather_env_present": any_weather_key,
        "soil_env_present": any_soil_key,
        "geocoding_env_present": any_geocoding_key,
        "provider_config_tables_present": bool(existing_provider_tables),
        "live_enabled_provider_rows": len(live_enabled_rows),
        "blocked_or_disabled_provider_rows": len(blocked_rows),
        "safe_for_demo_live_weather_test": any_weather_key and len(live_enabled_rows) > 0,
        "safe_for_demo_live_soil_test": any_soil_key and len(live_enabled_rows) > 0,
        "safe_for_bulk_geocoding": False,
        "reason_geocoding_not_bulk_safe": "Bulk geocoding requires provider terms, caching policy, budget, and rate-limit approval.",
    }


def main() -> int:
    db = SessionLocal()
    try:
        env = env_presence()
        tables = provider_table_summaries(db)
        readiness = classify_readiness(env, tables)
        result = {
            "schema_version": "provider_live_readiness_audit.v1",
            "secrets_printed": False,
            "external_calls_made": False,
            "env_presence": env,
            "provider_tables": tables,
            "readiness": readiness,
            "next_actions": [
                "Choose live-test providers explicitly; do not enable all providers globally.",
                "Add credentials through environment/secret manager only; never commit them.",
                "Set provider config live_execution_enabled only for test tenant/provider after review.",
                "Keep timeout, retry, and rate limits small for demo testing.",
                "Run live smoke tests with one parcel/farmer first, then inspect snapshots and logs.",
                "Do not bulk-geocode villages until provider terms and cache policy are reviewed.",
            ],
        }
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
