#!/usr/bin/env python3
"""Regression for read-only NWDP demographic enrichment import dry-run plan."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/plan_nwdp_demographic_enrichment_import.py"
OUTPUT = Path("/tmp/nwdp-demographic-enrichment-import-plan-regression.json")


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--limit",
            "250",
            "--sample-limit",
            "5",
            "--output",
            str(OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Import plan writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "Import plan exits zero", data)
    check(data["schema_version"] == "nwdp_demographic_enrichment_import_plan.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_IMPORT_PLAN", "Plan is read-only", data)
    check(data["healthy"] is True, "Plan is healthy", data)

    check(data["safe_candidate_count_loaded"] >= 450000, "Plan loads safe candidate universe", data)
    check(data["candidate_missing_state_key_count"] == 0, "Plan resolves candidate state keys", data)
    check(data["candidate_count_considered"] == 250, "Plan considers capped sample", data)
    check(data["planned_profile_rows"] == 250, "Plan creates capped profile preview rows", data)
    check(data["missing_raw_feature_count"] == 0, "Plan finds raw features for sampled candidates", data)

    check(data["population_nonzero_count"] > 0, "Plan counts non-zero population rows", data)
    check(data["household_nonzero_count"] > 0, "Plan counts non-zero household rows", data)
    check(data["population_nonzero_ratio"] > 0, "Plan reports population non-zero ratio", data)
    check(data["household_nonzero_ratio"] > 0, "Plan reports household non-zero ratio", data)

    sample = data["sample_profile_rows"][0]
    check(sample["village_id"], "Sample attaches to master village id", sample)
    check(sample["source_system"] == "NWDP_GSI_VILLAGE_BOUNDARY", "Sample preserves source system", sample)
    check(sample["source_feature_index"] == 0, "Sample preserves source feature index", sample)
    check(sample["source_vlcode"], "Sample preserves source vlcode", sample)
    check("total_population" in sample, "Sample includes total population field", sample)
    check("total_households" in sample, "Sample includes household field", sample)
    check("net_area_sown" in sample, "Sample includes land-use field", sample)
    check("handpump_status" in sample, "Sample includes amenity field", sample)

    notes = data["notes"]
    check(any("no demographic profile rows are written" in note for note in notes), "Plan states no profile writes", notes)
    check(any("Official Census 2011" in note for note in notes), "Plan keeps official Census separate", notes)
    check(any("one file at a time" in note for note in notes), "Plan documents memory-safe raw processing", notes)

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Plan attempts no DB writes", guardrails)
    check(guardrails["schema_migration_created"] is False, "Plan creates no migration", guardrails)
    check(guardrails["demographic_profile_rows_written"] is False, "Plan writes no demographic profiles", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Plan does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Plan does not claim official Census import", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Plan keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_schema_migration_plan"] is True, "Plan is ready for schema migration planning", readiness)
    check(readiness["ready_for_demographic_profile_apply"] is False, "Plan is not apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Plan does not change Android", readiness)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT IMPORT PLAN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
