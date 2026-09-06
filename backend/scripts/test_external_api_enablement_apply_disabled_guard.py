#!/usr/bin/env python3
"""Regression for disabled external API/provider runtime enablement apply guard."""

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


OUT_DIR = Path("/tmp/external-api-enable-apply-disabled-guard-regression")
SCRIPT = ROOT / "backend/scripts/apply_external_api_enablement_disabled.py"


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
        "weather_provider_config_rows": count_or_zero(db, "weather_provider_configs"),
        "weather_provider_enabled_rows": count_or_zero(db, "weather_provider_configs", "is_enabled = true"),
        "weather_snapshot_rows": count_or_zero(db, "weather_snapshots"),
        "weather_fresh_snapshot_rows": count_or_zero(db, "weather_snapshots", "expires_at is null or expires_at > now()"),
        "soil_enrichment_snapshot_rows": count_or_zero(db, "soil_enrichment_snapshots"),
        "soil_enrichment_available_snapshot_rows": count_or_zero(db, "soil_enrichment_snapshots", "status = 'AVAILABLE'"),
        "soil_enrichment_job_audit_rows": count_or_zero(db, "soil_enrichment_job_audit_events"),
        "soil_enrichment_failed_job_audit_rows": count_or_zero(db, "soil_enrichment_job_audit_events", "status = 'FAILED'"),
        "field_event_external_api_rows": count_or_zero(db, "field_event_reports", "source = 'EXTERNAL_API'"),
        "project_app_config_audit_rows": count_or_zero(db, "project_app_config_audit_events"),
    }


def run_guard(*args: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(OUT_DIR),
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )


def read_audit() -> dict:
    return json.loads((OUT_DIR / "external_api_enablement_apply_disabled_audit.json").read_text(encoding="utf-8"))


def assert_counts_unchanged(db, before: dict[str, int], label: str) -> None:
    after = table_counts(db)
    check(after == before, label, {"before": before, "after": after})


def main() -> int:
    print("=" * 72)
    print("EXTERNAL API ENABLEMENT APPLY DISABLED GUARD REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        before = table_counts(db)

        no_apply = run_guard()
        check(no_apply.returncode != 0, "Missing apply flag exits non-zero", no_apply.stdout[-2000:])
        data = read_audit()
        check(data["schema_version"] == "external_api_enablement_apply_disabled_guard.v1", "Schema version is stable", data)
        check(data["mode"] == "DISABLED_EXTERNAL_API_RUNTIME_ENABLEMENT_APPLY_GUARD", "Mode is disabled guard", data)
        check(data["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", data)
        check(data["apply_requested"] is False, "No-apply attempt is recorded", data)
        check(data["readiness_report"]["healthy"] is True, "Guard embeds healthy readiness report", data["readiness_report"]["summary"])
        assert_counts_unchanged(db, before, "No-apply guard leaves DB counts unchanged")

        missing_scope = run_guard(
            "--apply",
            "--enable-external-api-runtime",
            "--rollback-token",
            "external-api-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(missing_scope.returncode != 0, "Missing provider scope exits non-zero", missing_scope.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "PROVIDER_SURFACE_AND_CODE_SCOPE_REQUIRED", "Provider surface/code scope is required", data)
        assert_counts_unchanged(db, before, "Missing-scope guard leaves DB counts unchanged")

        missing_flag = run_guard(
            "--apply",
            "--surface",
            "WEATHER",
            "--provider-code",
            "OPEN_METEO",
            "--rollback-token",
            "external-api-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(missing_flag.returncode != 0, "Missing enable policy flag exits non-zero", missing_flag.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ENABLE_EXTERNAL_API_RUNTIME_POLICY_FLAG_REQUIRED", "Enable policy flag is required", data)
        assert_counts_unchanged(db, before, "Missing-enable-flag guard leaves DB counts unchanged")

        missing_rollback = run_guard(
            "--apply",
            "--surface",
            "WEATHER",
            "--provider-code",
            "OPEN_METEO",
            "--enable-external-api-runtime",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(missing_rollback.returncode != 0, "Missing rollback/supersession plan exits non-zero", missing_rollback.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED", "Rollback/supersession plan is required", data)
        assert_counts_unchanged(db, before, "Missing-rollback guard leaves DB counts unchanged")

        disabled = run_guard(
            "--apply",
            "--surface",
            "WEATHER",
            "--provider-code",
            "OPEN_METEO",
            "--enable-external-api-runtime",
            "--rollback-token",
            "external-api-disabled-guard-regression",
            "--dry-run-confirmed",
            "--admin-confirmation",
        )
        check(disabled.returncode != 0, "Disabled external API runtime apply exits non-zero", disabled.stdout[-2000:])
        data = read_audit()
        check(data["error"] == "EXTERNAL_API_RUNTIME_ENABLEMENT_APPLY_DISABLED_BY_POLICY", "Apply remains disabled by policy", data)
        check(data["apply_requested"] is True, "Apply attempt is recorded", data)
        check(data["enable_external_api_runtime_requested"] is True, "Future enable flag is recorded", data)
        check(data["dry_run_confirmed"] is True, "Dry-run confirmation is recorded", data)
        check(data["admin_confirmation"] is True, "Admin confirmation is recorded", data)
        check(data["rollback_token"] == "external-api-disabled-guard-regression", "Rollback token is recorded", data)
        check(data["counts_unchanged"] is True, "Audit reports unchanged DB counts", data)

        summary = data["readiness_report"]["summary"]
        check(summary["provider_surface_count"] >= 0, "Provider surface count is readable", summary)
        check("weather_provider_config_count" in summary, "Weather provider config count is readable", summary)
        check("soil_provider_surface_count" in summary, "Soil provider surface count is readable", summary)
        check("providers_ready_for_live_runtime_count" in summary, "Runtime-ready provider count is readable", summary)

        policy = data["policy"]
        check(policy["real_apply_supported"] is False, "Real apply remains unsupported", policy)
        check(policy["surface_and_provider_scope_required"] is True, "Provider scope required", policy)
        check(policy["future_enable_policy_flag_required"] is True, "Future enable flag required", policy)
        check(policy["rollback_or_supersession_plan_required_before_real_apply"] is True, "Rollback/supersession required", policy)
        check(policy["provider_credentials_review_required"] is True, "Credentials review required", policy)
        check(policy["rate_limit_and_cost_guardrails_required"] is True, "Rate/cost guardrails required", policy)
        check(policy["worker_scheduler_enablement_review_required"] is True, "Scheduler review required", policy)
        check(policy["external_provider_call_allowed"] is False, "External provider calls are not allowed", policy)
        check(policy["provider_worker_execution_allowed"] is False, "Provider workers are not allowed", policy)
        check(policy["secret_output_allowed"] is False, "Secret output is not allowed", policy)
        check(policy["android_behavior_change_allowed"] is False, "Android behavior change is not allowed", policy)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Guard attempts no DB writes", guardrails)
        check(guardrails["external_api_called"] is False, "Guard calls no external APIs", guardrails)
        check(guardrails["provider_worker_executed"] is False, "Guard runs no provider workers", guardrails)
        check(guardrails["provider_config_changed"] is False, "Guard changes no provider config", guardrails)
        check(guardrails["provider_live_execution_enabled"] is False, "Guard enables no live execution", guardrails)
        check(guardrails["provider_scheduler_enabled"] is False, "Guard enables no scheduler", guardrails)
        check(guardrails["provider_snapshot_written"] is False, "Guard writes no provider snapshots", guardrails)
        check(guardrails["provider_audit_written"] is False, "Guard writes no provider audits", guardrails)
        check(guardrails["secrets_printed"] is False, "Guard prints no secrets", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Guard keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Guard keeps Android unchanged", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_admin_review"] is True, "Ready for admin review", readiness)
        check(readiness["ready_for_external_api_runtime_use"] is False, "Not ready for external API runtime use", readiness)
        check(readiness["ready_for_external_api_apply"] is False, "Not ready for external API apply", readiness)
        check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)

        check((OUT_DIR / "external_api_enablement_apply_disabled_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "external_api_enablement_apply_disabled_providers.csv").exists(), "Provider CSV is written", str(OUT_DIR))

        assert_counts_unchanged(db, before, "Disabled apply guard leaves DB counts unchanged")

        print("=" * 72)
        print("EXTERNAL API ENABLEMENT APPLY DISABLED GUARD REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
