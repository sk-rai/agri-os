#!/usr/bin/env python3
"""Disabled apply guard for external API/provider runtime enablement.

This command intentionally refuses real external provider enablement. It wraps
the read-only external API readiness report and writes durable JSON/CSV audit
files without making provider calls, running workers, changing provider config,
enabling schedulers, enabling runtime lookup, or changing Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402


SCHEMA_VERSION = "external_api_enablement_apply_disabled_guard.v1"


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text("""
        select exists (
          select 1
          from information_schema.tables
          where table_schema = 'public'
            and table_name = :table
        )
    """), {"table": table}).scalar())


def count_or_zero(conn, table: str, where: str = "true") -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(text(f"select count(*)::bigint from {table} where {where}")).scalar() or 0)


def table_counts(conn) -> dict[str, int]:
    return {
        "weather_provider_config_rows": count_or_zero(conn, "weather_provider_configs"),
        "weather_provider_enabled_rows": count_or_zero(conn, "weather_provider_configs", "is_enabled = true"),
        "weather_snapshot_rows": count_or_zero(conn, "weather_snapshots"),
        "weather_fresh_snapshot_rows": count_or_zero(conn, "weather_snapshots", "expires_at is null or expires_at > now()"),
        "soil_enrichment_snapshot_rows": count_or_zero(conn, "soil_enrichment_snapshots"),
        "soil_enrichment_available_snapshot_rows": count_or_zero(conn, "soil_enrichment_snapshots", "status = 'AVAILABLE'"),
        "soil_enrichment_job_audit_rows": count_or_zero(conn, "soil_enrichment_job_audit_events"),
        "soil_enrichment_failed_job_audit_rows": count_or_zero(conn, "soil_enrichment_job_audit_events", "status = 'FAILED'"),
        "field_event_external_api_rows": count_or_zero(conn, "field_event_reports", "source = 'EXTERNAL_API'"),
        "project_app_config_audit_rows": count_or_zero(conn, "project_app_config_audit_events"),
    }


def run_readiness(output_dir: Path) -> dict[str, Any]:
    readiness_dir = output_dir / "readiness_source"
    readiness_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/report_external_api_readiness.py"),
            "--output-dir",
            str(readiness_dir),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=240,
    )

    report_path = readiness_dir / "external_api_readiness_report.json"
    if not report_path.exists():
        return {
            "healthy": False,
            "error": "EXTERNAL_API_READINESS_REPORT_DID_NOT_WRITE_JSON",
            "returncode": proc.returncode,
            "output": proc.stdout[-4000:],
        }

    data = json.loads(report_path.read_text(encoding="utf-8"))
    data["_readiness_returncode"] = proc.returncode
    return data


def write_provider_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
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
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled external API/provider runtime enablement apply guard.")
    parser.add_argument("--surface", default="", help="Required future scope, e.g. WEATHER or SOIL_ENRICHMENT.")
    parser.add_argument("--provider-code", default="", help="Required future provider code, e.g. OPEN_METEO.")
    parser.add_argument("--tenant-id", default="", help="Optional tenant scope.")
    parser.add_argument("--output-dir", default="/tmp/external-api-enable-apply-disabled")
    parser.add_argument("--apply", action="store_true", help="Records an explicit apply attempt, but real apply remains disabled.")
    parser.add_argument("--enable-external-api-runtime", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--dry-run-confirmed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    surface = args.surface.strip().upper()
    provider_code = args.provider_code.strip().upper()
    tenant_id = args.tenant_id.strip()

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        before = table_counts(conn)

    readiness_report = run_readiness(output_dir)

    with engine.connect() as conn:
        after = table_counts(conn)

    if not args.apply:
        error = "EXPLICIT_APPLY_FLAG_REQUIRED"
    elif not surface or not provider_code:
        error = "PROVIDER_SURFACE_AND_CODE_SCOPE_REQUIRED"
    elif not args.enable_external_api_runtime:
        error = "ENABLE_EXTERNAL_API_RUNTIME_POLICY_FLAG_REQUIRED"
    elif not args.rollback_token.strip():
        error = "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED"
    elif not args.dry_run_confirmed:
        error = "DRY_RUN_CONFIRMATION_REQUIRED"
    elif not args.admin_confirmation:
        error = "ADMIN_CONFIRMATION_REQUIRED"
    else:
        error = "EXTERNAL_API_RUNTIME_ENABLEMENT_APPLY_DISABLED_BY_POLICY"

    provider_rows = readiness_report.get("provider_rows", [])
    matching_provider_rows = [
        row for row in provider_rows
        if str(row.get("surface", "")).upper() == surface
        and str(row.get("provider_code", "")).upper() == provider_code
        and (not tenant_id or str(row.get("tenant_id") or "") == tenant_id)
    ]

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "DISABLED_EXTERNAL_API_RUNTIME_ENABLEMENT_APPLY_GUARD",
        "error": error,
        "filters": {
            "surface": surface or None,
            "provider_code": provider_code or None,
            "tenant_id": tenant_id or None,
        },
        "apply_requested": bool(args.apply),
        "enable_external_api_runtime_requested": bool(args.enable_external_api_runtime),
        "dry_run_confirmed": bool(args.dry_run_confirmed),
        "admin_confirmation": bool(args.admin_confirmation),
        "rollback_token": args.rollback_token.strip() or None,
        "claim_boundary": "This guard is intentionally non-mutating. It audits external API readiness but refuses to call providers, run provider workers, change provider configuration, enable live execution, enable schedulers, write snapshots/audits, enable runtime lookup, print secrets, or change Android behavior.",
        "readiness_report": readiness_report,
        "matching_provider_rows": matching_provider_rows,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "policy": {
            "real_apply_supported": False,
            "explicit_apply_flag_required": True,
            "surface_and_provider_scope_required": True,
            "future_enable_policy_flag_required": True,
            "rollback_or_supersession_plan_required_before_real_apply": True,
            "dry_run_required_before_real_apply": True,
            "admin_confirmation_required_before_real_apply": True,
            "provider_credentials_review_required": True,
            "rate_limit_and_cost_guardrails_required": True,
            "worker_scheduler_enablement_review_required": True,
            "failure_retry_audit_review_required": True,
            "external_provider_call_allowed": False,
            "provider_worker_execution_allowed": False,
            "provider_config_write_allowed": False,
            "scheduler_enablement_allowed": False,
            "snapshot_write_allowed": False,
            "secret_output_allowed": False,
            "runtime_lookup_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "external_api_called": False,
            "provider_worker_executed": False,
            "provider_config_changed": False,
            "provider_live_execution_enabled": False,
            "provider_scheduler_enabled": False,
            "provider_snapshot_written": False,
            "provider_audit_written": False,
            "secrets_printed": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_admin_review": bool(readiness_report.get("readiness", {}).get("ready_for_admin_review")),
            "ready_for_weather_runtime_provider_execution": False,
            "ready_for_soil_runtime_provider_execution": False,
            "ready_for_external_api_runtime_use": False,
            "ready_for_external_api_apply": False,
            "ready_for_android_behavior_change": False,
            "ready_for_real_apply_implementation_design": bool(readiness_report.get("healthy")),
        },
        "output_files": {
            "json": str(output_dir / "external_api_enablement_apply_disabled_audit.json"),
            "csv": str(output_dir / "external_api_enablement_apply_disabled_providers.csv"),
        },
    }

    json_path = output_dir / "external_api_enablement_apply_disabled_audit.json"
    csv_path = output_dir / "external_api_enablement_apply_disabled_providers.csv"

    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_provider_csv(csv_path, matching_provider_rows or provider_rows)

    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
