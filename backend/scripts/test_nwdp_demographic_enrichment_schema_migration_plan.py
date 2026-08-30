#!/usr/bin/env python3
"""Regression for NWDP demographic enrichment schema migration dry-run plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_enrichment_schema_migration.py"
OUTPUT = Path("/tmp/nwdp-demographic-enrichment-schema-migration-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
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

    check(OUTPUT.exists(), "Migration plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Migration plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_enrichment_schema_migration_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "DRY_RUN_SCHEMA_MIGRATION_PLAN", "Plan is dry run", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Plan targets profile table", data)

    columns = data["columns"]
    required_columns = [
        "village_id uuid not null references geography_villages(id)",
        "source_system varchar not null",
        "source_version varchar not null",
        "source_feature_id uuid null",
        "source_vlcode varchar null",
        "total_population integer null",
        "total_households integer null",
        "net_area_sown numeric null",
        "handpump_status varchar null",
        "source_properties jsonb not null default '{}'",
        "match_evidence jsonb not null default '{}'",
        "is_active boolean not null default false",
        "promotion_status varchar not null default 'NOT_PROMOTED'",
    ]
    for column in required_columns:
        check(column in columns, f"Column planned: {column}", columns)

    indexes = data["indexes"]
    index_names = {item["name"] for item in indexes}
    check("ix_geography_village_demographic_profiles_village_id" in index_names, "Village index planned", indexes)
    check("ix_geography_village_demographic_profiles_source" in index_names, "Source version index planned", indexes)
    check("uq_geography_village_demographic_profiles_source_feature" in index_names, "Source feature uniqueness planned", indexes)
    check("uq_geography_village_demographic_profiles_active_promoted" in index_names, "Active promoted uniqueness planned", indexes)

    behavior = data["expected_migration_behavior"]
    check(behavior["create_table"] is True, "Migration would create table", behavior)
    check(behavior["create_indexes"] is True, "Migration would create indexes", behavior)
    check(behavior["insert_rows"] is False, "Migration inserts no rows", behavior)
    check(behavior["update_geography_villages"] is False, "Migration does not update geography master", behavior)
    check(behavior["enable_runtime_lookup"] is False, "Migration enables no runtime lookup", behavior)
    check(behavior["change_android_behavior"] is False, "Migration changes no Android behavior", behavior)

    guardrails = data["guardrails"]
    check(all(value is False for value in guardrails.values()), "All guardrails remain false", guardrails)
    check(guardrails["schema_migration_file_created"] is False, "No migration file created", guardrails)
    check(guardrails["schema_migration_applied"] is False, "No migration applied", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "No profiles written", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Official Census not claimed", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_schema_migration_file"] is True, "Ready for migration file authoring", readiness)
    check(readiness["ready_for_schema_migration_apply"] is False, "Not ready to apply migration", readiness)
    check(readiness["ready_for_demographic_profile_apply"] is False, "Not ready for profile apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android behavior change", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT SCHEMA MIGRATION PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
