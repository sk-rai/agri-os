#!/usr/bin/env python3
"""Regression for NWDP demographic enrichment schema/import workflow plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_enrichment_schema.py"
OUTPUT = Path("/tmp/nwdp-demographic-enrichment-schema-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--output", str(OUTPUT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Schema plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Schema plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_enrichment_schema_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_SCHEMA_PLAN", "Plan is read-only", data)
    check(data["healthy"] is True, "Plan is healthy", data)

    evidence = data["current_evidence"]
    check(evidence["existing_geography_master"]["known_count"] == 576083, "Plan references geography master count", evidence)
    check(evidence["existing_geography_master"]["current_census_village_code_count"] == 0, "Plan records Census code gap", evidence)
    check(evidence["nwdp_demographic_source"]["feature_count"] == 654285, "Plan references NWDP feature count", evidence)
    check(evidence["nwdp_demographic_source"]["population_nonzero_count"] == 605657, "Plan references population coverage", evidence)
    check(evidence["nwdp_demographic_source"]["official_census_import"] is False, "Plan does not call NWDP official Census", evidence)

    schema = data["recommended_schema"]
    check(schema["table"] == "geography_village_demographic_profiles", "Plan names profile table", schema)
    check(any("village_id" in item for item in schema["identity_columns"]), "Schema attaches to geography village id", schema)
    check("total_population integer null" in schema["core_demographic_columns"], "Schema includes total population", schema)
    check("total_households integer null" in schema["core_demographic_columns"], "Schema includes households", schema)
    check("net_area_sown numeric null" in schema["land_use_columns"], "Schema includes net area sown", schema)
    check("handpump_status varchar null" in schema["amenity_status_columns"], "Schema includes amenity status", schema)
    check(any("source_properties jsonb" in item for item in schema["audit_columns"]), "Schema preserves source properties", schema)

    workflow = data["guarded_import_workflow"]
    check(workflow["phase_2_dry_run"]["writes_db"] is False, "Dry run writes no DB rows", workflow)
    check(workflow["phase_3_schema_migration"]["not_allowed"] == "No profile row insertion in migration.", "Migration is schema-only", workflow)
    check(workflow["phase_4_apply_disabled_endpoint"]["writes_db"] is False, "Future disabled endpoint writes nothing", workflow)
    check(workflow["phase_5_guarded_apply"]["requires_admin_edit_permission"] is True, "Apply requires admin edit", workflow)
    check(workflow["phase_6_android_readiness"]["android_behavior_change"] == "separate checkpoint only", "Android is separate checkpoint", workflow)

    census = data["official_census_path"]
    check(census["status"] == "not loaded locally", "Plan records official Census not loaded", census)
    check("geography_census_locations" in census["recommended_separate_tables"], "Plan keeps official Census separate", census)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["schema_migration_created"] is False, "Plan creates no migration", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Plan writes no demographic profiles", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Plan does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Plan does not claim official Census import", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_dry_run_import_plan"] is True, "Plan is ready for dry-run import planning", readiness)
    check(readiness["ready_for_schema_migration"] is False, "Plan is not schema migration", readiness)
    check(readiness["ready_for_demographic_profile_apply"] is False, "Plan is not apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Plan does not change Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT SCHEMA PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
