#!/usr/bin/env python3
"""Regression for disabled climate/agro-ecology runtime enablement apply guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402


OUT_DIR = Path("/tmp/climate-agro-ecology-runtime-enable-apply-disabled-guard-regression")
SCRIPT = ROOT / "backend/scripts/apply_climate_agro_ecology_runtime_enablement_disabled.py"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:3000])
    if not condition:
        raise AssertionError(label)


def table_exists(db, table: str) -> bool:
    return bool(db.execute(text("""
        select exists (
          select 1
          from information_schema.tables
          where table_schema = 'public'
            and table_name = :table
        )
    """), {"table": table}).scalar())


def count_or_zero(db, table: str, where: str = "true") -> int:
    if not table_exists(db, table):
        return 0
    return int(db.execute(text(f"select count(*)::bigint from {table} where {where}")).scalar() or 0)


def table_counts(db) -> dict[str, int]:
    return {
        "climate_region_rows": count_or_zero(db, "geography_climate_regions"),
        "active_climate_region_rows": count_or_zero(db, "geography_climate_regions", "is_active = true"),
        "climate_mapping_rows": count_or_zero(db, "geography_climate_region_mappings"),
        "active_climate_mapping_rows": count_or_zero(db, "geography_climate_region_mappings", "is_active = true"),
        "crop_climate_rule_rows": count_or_zero(db, "crop_climate_suitability_rules"),
        "active_crop_climate_rule_rows": count_or_zero(db, "crop_climate_suitability_rules", "is_active = true"),
        "crop_climate_override_rows": count_or_zero(db, "crop_climate_suitability_overrides"),
        "active_crop_climate_override_rows": count_or_zero(db, "crop_climate_suitability_overrides", "is_active = true"),
        "project_app_config_audit_rows": count_or_zero(db, "project_app_config_audit_events"),
        "weather_provider_config_rows": count_or_zero(db, "weather_provider_configs"),
        "weather_snapshot_rows": count_or_zero(db, "weather_snapshots"),
        "soil_enrichment_snapshot_rows": count_or_zero(db, "soil_enrichment_snapshots"),
        "soil_enrichment_job_audit_rows": count_or_zero(db, "soil_enrichment_job_audit_events"),
    }


def run_guard(*args: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(OUT_DIR),
            "--limit",
            "5000",
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )


def read_audit() -> dict:
    return json.loads((OUT_DIR / "climate_agro_ecology_runtime_enablement_apply_disabled_audit.json").read_text(encoding="utf-8"))


def assert_counts_unchanged(db, before: dict[str, int], label: str) -> None:
    after = table_counts(db)
    check(after == before, label, {"before": before, "after": after})


def main() -> int:
    print("=" * 72)
    print("CLIMATE AGRO-ECOLOGY RUNTIME ENABLEMENT APPLY DISABLED GUARD REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before = table_counts(db)

        no_apply = run_guard()
        check(no_apply.returncode != 0, "Missing apply flag exits non-zero", no_apply.stdout[-2000:])
        data = read_audit()
        check(data["schema_version"] == "climate_agro_ecology_runtime_enablement_apply_disabled_guard.v1", "Schema version is stable", data)
        check(data["mode"] == "DISABLED_CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_APPLY_GUARD", "Mode is disabled guard", data)
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["apply_requested"] is False, "No-apply attempt is recorded", data)
        check(data["dry_run"]["healthy"] is True, "Guard embeds healthy dry-run", data["dry_run"]["summary"])
        assert_counts_unchanged(db, before, "No-apply guard leaves DB counts unchanged")

        missing_flag = run_guard(
            "--apply",
            "--rollback-token",
            "climate-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(missing_flag.returncode != 0, "Missing enable policy flag exits non-zero", missing_flag.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ENABLE_CLIMATE_RUNTIME_POLICY_FLAG_REQUIRED", "Enable policy flag is required", data)
        assert_counts_unchanged(db, before, "Missing-enable-flag guard leaves DB counts unchanged")

        missing_rollback = run_guard(
            "--apply",
            "--enable-climate-runtime",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(missing_rollback.returncode != 0, "Missing rollback/disable plan exits non-zero", missing_rollback.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ROLLBACK_OR_DISABLE_PLAN_REQUIRED", "Rollback/disable plan is required", data)
        assert_counts_unchanged(db, before, "Missing-rollback guard leaves DB counts unchanged")

        disabled = run_guard(
            "--apply",
            "--enable-climate-runtime",
            "--rollback-token",
            "climate-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(disabled.returncode != 0, "Disabled climate runtime apply exits non-zero", disabled.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "CLIMATE_AGRO_ECOLOGY_RUNTIME_ENABLEMENT_APPLY_DISABLED_BY_POLICY", "Apply remains disabled by policy", data)
        check(data["apply_requested"] is True, "Apply attempt is recorded", data)
        check(data["enable_climate_runtime_requested"] is True, "Future enable flag is recorded", data)
        check(data["dry_run_confirmed"] is True, "Dry-run confirmation is recorded", data)
        check(data["admin_confirmation"] is True, "Admin confirmation is recorded", data)
        check(data["rollback_token"] == "climate-disabled-guard-regression", "Rollback token is recorded", data)
        check(data["counts_unchanged"] is True, "Audit reports unchanged DB counts", data)

        summary = data["dry_run"]["summary"]
        check(summary["active_climate_region_count"] > 0, "Dry-run sees climate regions", summary)
        check(summary["active_climate_mapping_count"] > 0, "Dry-run sees climate mappings", summary)
        check(summary["active_crop_climate_rule_count"] > 0, "Dry-run sees crop climate rules", summary)
        check(summary["planned_runtime_config_write_count"] == 0, "Dry-run plans no runtime config writes", summary)
        check(summary["planned_mapping_write_count"] == 0, "Dry-run plans no mapping writes", summary)
        check(summary["planned_rule_write_count"] == 0, "Dry-run plans no rule writes", summary)

        policy = data["policy"]
        check(policy["real_apply_supported"] is False, "Real apply remains unsupported", policy)
        check(policy["future_enable_policy_flag_required"] is True, "Future enable flag required", policy)
        check(policy["rollback_or_disable_plan_required_before_real_apply"] is True, "Rollback/disable plan required", policy)
        check(policy["dry_run_required_before_real_apply"] is True, "Dry-run required", policy)
        check(policy["external_provider_call_allowed"] is False, "External provider calls are not allowed", policy)
        check(policy["android_behavior_change_allowed"] is False, "Android behavior change is not allowed", policy)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Guard attempts no DB writes", guardrails)
        check(guardrails["climate_mappings_written"] is False, "Guard writes no climate mappings", guardrails)
        check(guardrails["crop_climate_rules_written"] is False, "Guard writes no crop climate rules", guardrails)
        check(guardrails["runtime_config_written"] is False, "Guard writes no runtime config", guardrails)
        check(guardrails["provider_config_changed"] is False, "Guard changes no provider config", guardrails)
        check(guardrails["external_api_called"] is False, "Guard calls no external APIs", guardrails)
        check(guardrails["provider_worker_executed"] is False, "Guard runs no provider workers", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Guard keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Guard keeps Android unchanged", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_admin_review"] is True, "Ready for admin review", readiness)
        check("ready_for_admin_runtime_preview" in readiness, "Admin runtime preview readiness is reported", readiness)
        check(readiness["ready_for_broad_runtime_enablement"] is False, "Not ready for broad runtime enablement", readiness)
        check(readiness["ready_for_climate_runtime_apply"] is False, "Not ready for climate runtime apply", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)

        check((OUT_DIR / "climate_agro_ecology_runtime_enablement_apply_disabled_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "climate_agro_ecology_runtime_enablement_apply_disabled_districts.csv").exists(), "District CSV is written", str(OUT_DIR))

        assert_counts_unchanged(db, before, "Disabled apply guard leaves DB counts unchanged")

        print("=" * 72)
        print("CLIMATE AGRO-ECOLOGY RUNTIME ENABLEMENT APPLY DISABLED GUARD REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
