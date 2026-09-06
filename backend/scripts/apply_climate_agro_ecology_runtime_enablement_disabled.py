#!/usr/bin/env python3
"""Disabled apply guard for climate/agro-ecology runtime enablement.

This command intentionally refuses real runtime enablement. It wraps the
climate runtime dry-run plan and writes durable JSON/CSV audit files so a future
apply implementation can be reviewed safely.
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

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402


SCHEMA_VERSION = "climate_agro_ecology_runtime_enablement_apply_disabled_guard.v1"


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text("""
        select exists (
          select 1 from information_schema.tables
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
        "climate_region_rows": count_or_zero(conn, "geography_climate_regions"),
        "active_climate_region_rows": count_or_zero(conn, "geography_climate_regions", "is_active = true"),
        "climate_mapping_rows": count_or_zero(conn, "geography_climate_region_mappings"),
        "active_climate_mapping_rows": count_or_zero(conn, "geography_climate_region_mappings", "is_active = true"),
        "crop_climate_rule_rows": count_or_zero(conn, "crop_climate_suitability_rules"),
        "active_crop_climate_rule_rows": count_or_zero(conn, "crop_climate_suitability_rules", "is_active = true"),
        "crop_climate_override_rows": count_or_zero(conn, "crop_climate_suitability_overrides"),
        "active_crop_climate_override_rows": count_or_zero(conn, "crop_climate_suitability_overrides", "is_active = true"),
        "project_app_config_audit_rows": count_or_zero(conn, "project_app_config_audit_events"),
        "weather_provider_config_rows": count_or_zero(conn, "weather_provider_configs"),
        "weather_snapshot_rows": count_or_zero(conn, "weather_snapshots"),
        "soil_enrichment_snapshot_rows": count_or_zero(conn, "soil_enrichment_snapshots"),
        "soil_enrichment_job_audit_rows": count_or_zero(conn, "soil_enrichment_job_audit_events"),
    }


def write_district_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "state_or_ut",
        "district",
        "state_lgd_code",
        "district_lgd_code",
        "climate_mapping_count",
        "climate_region_count",
        "crop_climate_rule_count",
        "district_ready_for_admin_runtime_preview",
        "planned_runtime_enablement_action",
        "blocker",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_dry_run(output_dir: Path, state_or_ut: str, district: str, limit: int) -> dict[str, Any]:
    dry_run_dir = output_dir / "dry_run_source"
    dry_run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "backend/scripts/plan_climate_agro_ecology_runtime_enablement_dry_run.py"),
        "--output-dir",
        str(dry_run_dir),
        "--limit",
        str(limit),
    ]
    if state_or_ut:
        cmd.extend(["--state-or-ut", state_or_ut])
    if district:
        cmd.extend(["--district", district])

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=240,
    )

    report_path = dry_run_dir / "climate_agro_ecology_runtime_enablement_dry_run.json"
    if not report_path.exists():
        return {
            "healthy": False,
            "error": "CLIMATE_DRY_RUN_DID_NOT_WRITE_JSON",
            "returncode": proc.returncode,
            "output": proc.stdout[-4000:],
        }

    data = json.loads(report_path.read_text(encoding="utf-8"))
    data["_dry_run_returncode"] = proc.returncode
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled climate/agro-ecology runtime enablement apply guard.")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--output-dir", default="/tmp/climate-agro-ecology-runtime-enable-apply-disabled")
    parser.add_argument("--apply", action="store_true", help="Records an explicit apply attempt, but real apply remains disabled.")
    parser.add_argument("--enable-climate-runtime", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--dry-run-confirmed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state_or_ut = args.state_or_ut.strip()
    district = args.district.strip()

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        before = table_counts(conn)

    dry_run = run_dry_run(output_dir, state_or_ut, district, args.limit)

    with engine.connect() as conn:
        after = table_counts(conn)

    if not args.apply:
        error = "EXPLICIT_APPLY_FLAG_REQUIRED"
    elif not args.enable_climate_runtime:
        error = "ENABLE_CLIMATE_RUNTIME_POLICY_FLAG_REQUIRED"
    elif not args.rollback_token.strip():
        error = "ROLLBACK_OR_DISABLE_PLAN_REQUIRED"
    elif not args.dry_run_confirmed:
        error = "DRY_RUN_CONFIRMATION_REQUIRED"
    elif not args.admin_confirmation:
        error = "ADMIN_CONFIRMATION_REQUIRED"
    else:
        error = "CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_APPLY_DISABLED_BY_POLICY"

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "DISABLED_CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_APPLY_GUARD",
        "error": error,
        "filters": {
            "state_or_ut": state_or_ut or None,
            "district": district or None,
            "limit": args.limit,
        },
        "apply_requested": bool(args.apply),
        "enable_climate_runtime_requested": bool(args.enable_climate_runtime),
        "dry_run_confirmed": bool(args.dry_run_confirmed),
        "admin_confirmation": bool(args.admin_confirmation),
        "rollback_token": args.rollback_token.strip() or None,
        "claim_boundary": "This guard is intentionally non-mutating. It audits climate/agro-ecology runtime enablement readiness but refuses to write mappings, rules, runtime config, provider config, snapshots, audits, or Android behavior changes.",
        "dry_run": dry_run,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "policy": {
            "real_apply_supported": False,
            "explicit_apply_flag_required": True,
            "future_enable_policy_flag_required": True,
            "rollback_or_disable_plan_required_before_real_apply": True,
            "dry_run_required_before_real_apply": True,
            "admin_confirmation_required_before_real_apply": True,
            "runtime_config_write_allowed": False,
            "mapping_write_allowed": False,
            "crop_climate_rule_write_allowed": False,
            "external_provider_call_allowed": False,
            "provider_worker_execution_allowed": False,
            "android_behavior_change_allowed": False,
            "broad_runtime_requires_all_districts_mapped_and_all_regions_crops_ruled": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "climate_mappings_written": False,
            "crop_climate_rules_written": False,
            "runtime_config_written": False,
            "provider_config_changed": False,
            "external_api_called": False,
            "provider_worker_executed": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_admin_review": bool(dry_run.get("readiness", {}).get("ready_for_admin_review")),
            "ready_for_admin_runtime_preview": bool(dry_run.get("readiness", {}).get("ready_for_admin_runtime_preview")),
            "ready_for_broad_runtime_enablement": False,
            "ready_for_climate_runtime_apply": False,
            "ready_for_android_behavior_change": False,
            "ready_for_real_apply_implementation_design": bool(dry_run.get("healthy")),
        },
        "output_files": {
            "json": str(output_dir / "climate_agro_ecology_runtime_enablement_apply_disabled_audit.json"),
            "csv": str(output_dir / "climate_agro_ecology_runtime_enablement_apply_disabled_districts.csv"),
        },
    }

    json_path = output_dir / "climate_agro_ecology_runtime_enablement_apply_disabled_audit.json"
    csv_path = output_dir / "climate_agro_ecology_runtime_enablement_apply_disabled_districts.csv"

    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_district_csv(csv_path, dry_run.get("district_rows", []))

    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
