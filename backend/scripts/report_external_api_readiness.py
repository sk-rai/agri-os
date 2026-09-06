#!/usr/bin/env python3
"""Read-only external API/provider readiness report.

This report inventories provider-backed application surfaces without making
network calls, enabling provider execution, mutating worker queues, or changing
Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.modules.media.provider_runtime_policy import provider_live_execution_status, provider_runtime_policy_from_config


SCHEMA_VERSION = "external_api_readiness_report.v1"


def db_url_from_settings() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def bool_config(value: Any, key: str) -> bool:
    return isinstance(value, dict) and value.get(key) is True


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text("""
        select exists (
          select 1
          from information_schema.tables
          where table_schema = 'public'
            and table_name = :table
        )
    """), {"table": table}).scalar())


def safe_count(conn, table: str, where: str = "true") -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(text(f"select count(*)::bigint from {table} where {where}")).scalar() or 0)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def weather_rows(conn) -> list[dict[str, Any]]:
    if not table_exists(conn, "weather_provider_configs"):
        return []

    rows = []
    for row in conn.execute(text("""
        select
          tenant_id,
          provider_code,
          display_name,
          provider_type,
          refresh_interval_hours,
          is_enabled,
          last_refresh_at,
          next_refresh_at,
          config,
          metadata
        from weather_provider_configs
        order by tenant_id, provider_code
    """)).mappings().all():
        item = row_dict(row)
        config = item.get("config") or {}
        policy = provider_runtime_policy_from_config(config).to_dict()
        live = provider_live_execution_status(config)
        rows.append({
            "surface": "WEATHER",
            "tenant_id": item.get("tenant_id"),
            "provider_code": item.get("provider_code"),
            "display_name": item.get("display_name"),
            "provider_type": item.get("provider_type"),
            "is_enabled": bool(item.get("is_enabled")),
            "demo_mode": bool(policy.get("demo_mode")),
            "live_execution_enabled": bool(live.get("live_execution_enabled")),
            "live_execution_status": live.get("live_execution_status"),
            "refresh_interval_hours": item.get("refresh_interval_hours"),
            "last_refresh_at": item.get("last_refresh_at"),
            "next_refresh_at": item.get("next_refresh_at"),
            "timeout_seconds": policy.get("timeout_seconds"),
            "max_retries": policy.get("max_retries"),
            "rate_limit_window_seconds": policy.get("rate_limit_window_seconds"),
            "max_requests_per_window": policy.get("max_requests_per_window"),
            "ready_for_runtime_use": bool(item.get("is_enabled")) and bool(live.get("live_execution_enabled")),
            "ready_for_android_behavior_change": False,
        })
    return rows


def soil_provider_rows(conn) -> list[dict[str, Any]]:
    """Summarize provider surfaces inferred from soil enrichment snapshots/audits.

    Soil enrichment currently has adapter/worker support and audit/snapshot rows,
    not a dedicated provider config table. Treat providers as review-visible but
    live execution disabled until an explicit config surface exists.
    """

    providers: set[str] = set()
    if table_exists(conn, "soil_enrichment_snapshots"):
        providers.update(
            str(value)
            for value in conn.execute(text("""
                select distinct provider
                from soil_enrichment_snapshots
                where provider is not null
                order by provider
            """)).scalars().all()
        )
    if table_exists(conn, "soil_enrichment_job_audit_events"):
        providers.update(
            str(value)
            for value in conn.execute(text("""
                select distinct provider
                from soil_enrichment_job_audit_events
                where provider is not null
                order by provider
            """)).scalars().all()
        )

    default_providers = {"SOILGRIDS", "OPEN_METEO_SOIL", "SHC_SLUSI"}
    providers.update(default_providers)

    return [
        {
            "surface": "SOIL_ENRICHMENT",
            "tenant_id": None,
            "provider_code": provider,
            "display_name": provider.replace("_", " ").title(),
            "provider_type": "EXTERNAL_API_OR_MANUAL_REFERENCE",
            "is_enabled": False,
            "demo_mode": False,
            "live_execution_enabled": False,
            "live_execution_status": "BLOCKED_UNTIL_APPROVED",
            "refresh_interval_hours": None,
            "last_refresh_at": None,
            "next_refresh_at": None,
            "timeout_seconds": 20,
            "max_retries": 2,
            "rate_limit_window_seconds": 60,
            "max_requests_per_window": 60,
            "ready_for_runtime_use": False,
            "ready_for_android_behavior_change": False,
        }
        for provider in sorted(providers)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only external API/provider readiness report.")
    parser.add_argument("--output-dir", default="/tmp/external-api-readiness")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        weather = weather_rows(conn)
        soil = soil_provider_rows(conn)
        provider_rows = weather + soil

        summary = {
            "provider_surface_count": len(provider_rows),
            "weather_provider_config_count": len(weather),
            "weather_provider_enabled_count": sum(1 for row in weather if row["is_enabled"]),
            "weather_live_execution_enabled_count": sum(1 for row in weather if row["live_execution_enabled"]),
            "weather_demo_mode_provider_count": sum(1 for row in weather if row["demo_mode"]),
            "soil_provider_surface_count": len(soil),
            "soil_live_execution_enabled_count": 0,
            "weather_snapshot_count": safe_count(conn, "weather_snapshots"),
            "weather_fresh_snapshot_count": safe_count(conn, "weather_snapshots", "expires_at is null or expires_at > now()"),
            "soil_enrichment_snapshot_count": safe_count(conn, "soil_enrichment_snapshots"),
            "soil_enrichment_available_snapshot_count": safe_count(conn, "soil_enrichment_snapshots", "status = 'AVAILABLE'"),
            "soil_enrichment_job_audit_count": safe_count(conn, "soil_enrichment_job_audit_events"),
            "soil_enrichment_failed_job_audit_count": safe_count(conn, "soil_enrichment_job_audit_events", "status = 'FAILED'"),
            "field_event_external_api_count": safe_count(conn, "field_event_reports", "source = 'EXTERNAL_API'"),
            "providers_ready_for_live_runtime_count": sum(1 for row in provider_rows if row["ready_for_runtime_use"]),
        }

    readiness = {
        "ready_for_admin_review": True,
        "ready_for_weather_runtime_provider_execution": summary["weather_live_execution_enabled_count"] > 0,
        "ready_for_soil_runtime_provider_execution": False,
        "ready_for_external_api_runtime_use": summary["providers_ready_for_live_runtime_count"] > 0,
        "ready_for_android_behavior_change": False,
        "requires_provider_credentials_review": True,
        "requires_live_execution_policy_approval": True,
        "requires_rate_limit_and_cost_guardrails": True,
        "requires_worker_scheduler_enablement_review": True,
        "requires_failure_retry_audit_review": True,
    }

    guardrails = {
        "external_api_called": False,
        "provider_worker_executed": False,
        "provider_config_changed": False,
        "provider_live_execution_enabled": False,
        "db_writes_attempted": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_EXTERNAL_API_READINESS_REPORT",
        "claim_boundary": "This report is read-only. It inventories weather, soil enrichment, and external-provider readiness without making provider calls, running workers, changing provider configuration, enabling live execution, enabling runtime lookup, or changing Android behavior.",
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "provider_rows": provider_rows,
        "runtime_policy": {
            "central_http_boundary": "app.modules.media.provider_http_client.execute_provider_http_request",
            "live_execution_default": "BLOCKED_UNTIL_APPROVED",
            "retryable_http_statuses": [408, 425, 429, 500, 502, 503, 504],
            "non_retryable_http_statuses": [400, 401, 403, 404, 422],
        },
        "known_application_surfaces": [
            {
                "surface": "WEATHER",
                "read_endpoints": [
                    "GET /api/v1/weather/providers",
                    "GET /api/v1/weather/snapshots/latest",
                    "GET /api/v1/weather/providers/refresh-plan",
                    "GET /api/v1/weather/operations/health",
                ],
                "worker_endpoint": "POST /api/v1/weather/refresh-worker/run-due",
                "runtime_status": "backend-owned; live provider execution approval-gated",
            },
            {
                "surface": "SOIL_ENRICHMENT",
                "read_endpoints": [
                    "GET /api/v1/soil-profiles/enrichments/latest",
                    "GET /api/v1/soil-profiles/enrichments/summary",
                    "GET /api/v1/soil-profiles/enrichments/queue",
                    "GET /api/v1/soil-profiles/enrichments/jobs/audit",
                    "GET /api/v1/soil-profiles/enrichments/operations/health",
                ],
                "worker_endpoint": "POST /api/v1/soil-profiles/enrichments/worker/run-queue",
                "runtime_status": "backend-owned; live provider execution approval-gated",
            },
            {
                "surface": "FIELD_EVENTS",
                "readiness_note": "External API-origin field events are supported by schema, but no runtime external ingestion is enabled by this report.",
                "runtime_status": "not enabled for autonomous external ingestion",
            },
        ],
        "recommended_next_steps": [
            "Expose this read-only external API readiness summary in the geography/layer readiness endpoint or a dedicated admin endpoint.",
            "Add web admin visibility for provider live-execution status, freshness, failures, and blockers.",
            "Before any apply/enablement, require explicit policy flag, credentials review, rate-limit/cost guardrails, dry-run, audit JSON/CSV, and rollback/disable plan.",
            "Keep Android behavior unchanged until a separate product decision enables provider-backed runtime behavior.",
        ],
        "output_files": {
            "json": str(output_dir / "external_api_readiness_report.json"),
            "csv": str(output_dir / "external_api_readiness_providers.csv"),
        },
    }

    (output_dir / "external_api_readiness_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "external_api_readiness_providers.csv",
        provider_rows,
        [
            "surface",
            "tenant_id",
            "provider_code",
            "display_name",
            "provider_type",
            "is_enabled",
            "demo_mode",
            "live_execution_enabled",
            "live_execution_status",
            "ready_for_runtime_use",
            "ready_for_android_behavior_change",
            "timeout_seconds",
            "max_retries",
            "rate_limit_window_seconds",
            "max_requests_per_window",
        ],
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
