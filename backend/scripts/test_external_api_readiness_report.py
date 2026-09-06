#!/usr/bin/env python3
"""Regression for read-only external API/provider readiness report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path("/tmp/external-api-readiness-regression")
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/report_external_api_readiness.py"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("EXTERNAL API READINESS REPORT REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(OUT_DIR)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    check(proc.returncode == 0, "Report exits zero", {"returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr})

    json_path = OUT_DIR / "external_api_readiness_report.json"
    csv_path = OUT_DIR / "external_api_readiness_providers.csv"

    check(json_path.exists(), "Report writes JSON", str(json_path))
    check(csv_path.exists(), "Report writes CSV", str(csv_path))

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    readiness = data["readiness"]
    guardrails = data["guardrails"]

    check(data["schema_version"] == "external_api_readiness_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_EXTERNAL_API_READINESS_REPORT", "Report mode is read-only", data)
    check(data["healthy"] is True, "Report is healthy", data)

    check(summary["provider_surface_count"] >= 1, "Provider surfaces are visible", summary)
    check(summary["weather_provider_config_count"] >= 0, "Weather provider config count is readable", summary)
    check(summary["weather_snapshot_count"] >= 0, "Weather snapshot count is readable", summary)
    check(summary["soil_enrichment_snapshot_count"] >= 0, "Soil enrichment snapshot count is readable", summary)
    check(summary["soil_enrichment_job_audit_count"] >= 0, "Soil enrichment job audit count is readable", summary)
    check(summary["field_event_external_api_count"] >= 0, "External API field event count is readable", summary)

    check(readiness["ready_for_admin_review"] is True, "Ready for admin review", readiness)
    check("ready_for_external_api_runtime_use" in readiness, "Runtime readiness is reported", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)
    check(readiness["requires_provider_credentials_review"] is True, "Provider credentials review is required", readiness)
    check(readiness["requires_live_execution_policy_approval"] is True, "Live execution policy approval is required", readiness)
    check(readiness["requires_rate_limit_and_cost_guardrails"] is True, "Rate limit and cost guardrails are required", readiness)

    check(guardrails["external_api_called"] is False, "Report calls no external APIs", guardrails)
    check(guardrails["provider_worker_executed"] is False, "Report runs no provider workers", guardrails)
    check(guardrails["provider_config_changed"] is False, "Report changes no provider config", guardrails)
    check(guardrails["provider_live_execution_enabled"] is False, "Report enables no provider live execution", guardrails)
    check(guardrails["db_writes_attempted"] is False, "Report attempts no DB writes", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Report keeps Android unchanged", guardrails)

    check(len(data["provider_rows"]) >= 1, "Provider rows are emitted", data["provider_rows"][:5])
    check(any(row["surface"] == "WEATHER" for row in data["provider_rows"]) or summary["weather_provider_config_count"] == 0, "Weather surface is consistent", data["provider_rows"][:5])
    check(any(row["surface"] == "SOIL_ENRICHMENT" for row in data["provider_rows"]), "Soil enrichment surface is visible", data["provider_rows"][:5])
    check(data["runtime_policy"]["live_execution_default"] == "BLOCKED_UNTIL_APPROVED", "Live execution default is blocked", data["runtime_policy"])

    print("=" * 72)
    print("EXTERNAL API READINESS REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
