#!/usr/bin/env python3
"""Regression for NWDP demographic schema migration local apply validation plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_schema_migration_apply_validation.py"
OUTPUT = Path("/tmp/nwdp-demographic-schema-migration-apply-validation-plan-regression.json")


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

    check(OUTPUT.exists(), "Apply validation plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Apply validation plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_schema_migration_apply_validation_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "DRY_RUN_LOCAL_MIGRATION_APPLY_VALIDATION_PLAN", "Plan is dry-run", data)
    check(data["healthy"] is True, "Plan is healthy", data)
    check(data["target_revision"] == "057", "Target revision is 057", data)
    check(data["target_table"] == "geography_village_demographic_profiles", "Target table is profile table", data)

    check("cd backend && ../venv/bin/alembic upgrade head" == data["apply_command"], "Apply command is explicit", data)

    pre = data["pre_apply_checks"]
    post = data["post_apply_checks"]
    check(any("migration file regression passes" in item for item in pre), "Pre-apply includes migration file regression", pre)
    check(any("target table does not already exist" in item for item in pre), "Pre-apply checks target table absence", pre)
    check(any("current revision is 057/head" in item for item in post), "Post-apply checks Alembic revision", post)
    check(any("row count is 0" in item for item in post), "Post-apply checks empty table", post)
    check(any("expected columns exist" in item for item in post), "Post-apply checks columns", post)
    check(any("expected indexes exist" in item for item in post), "Post-apply checks indexes", post)
    check(any("full NWDP boundary regression runner passes" in item for item in post), "Post-apply reruns full regression", post)

    columns = set(data["expected_columns"])
    for column in ["village_id", "source_system", "source_version", "total_population", "total_households", "source_properties", "match_evidence", "is_active", "promotion_status"]:
        check(column in columns, f"Expected column listed: {column}")

    indexes = set(data["expected_indexes"])
    check("uq_geography_village_demographic_profiles_source_feature" in indexes, "Source-feature unique index listed", indexes)
    check("uq_geography_village_demographic_profiles_active_promoted" in indexes, "Active-promoted unique index listed", indexes)

    guardrails = data["guardrails"]
    check(all(value is False for value in guardrails.values()), "All guardrails remain false", guardrails)
    check(guardrails["alembic_upgrade_executed"] is False, "Plan does not run Alembic", guardrails)
    check(guardrails["db_connection_attempted"] is False, "Plan does not connect to DB", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Plan writes no rows", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_local_migration_apply_validation"] is True, "Ready for local apply validation", readiness)
    check(readiness["ready_for_demographic_profile_import_apply"] is False, "Not ready for profile import apply", readiness)
    check(readiness["ready_for_runtime_lookup_enablement"] is False, "Not ready for runtime lookup", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Not ready for Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC SCHEMA MIGRATION APPLY VALIDATION PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
