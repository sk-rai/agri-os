#!/usr/bin/env python3
"""Regression for read-only NWDP demographic enrichment readiness audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("backend/scripts/audit_nwdp_demographic_enrichment_readiness.py")
OUTPUT = Path("/tmp/nwdp-demographic-enrichment-readiness-regression.json")
STATE_CSV = Path("/tmp/nwdp-demographic-enrichment-state-summary-regression.csv")


def check(condition: bool, label: str, detail: object | None = None) -> None:
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, default=str)[:5000])
        return
    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, default=str)[:5000])
    raise SystemExit(1)


def main() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(OUTPUT),
            "--state-summary-csv",
            str(STATE_CSV),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    check(OUTPUT.exists(), "Audit writes JSON output", proc.stdout)
    check(STATE_CSV.exists(), "Audit writes state summary CSV")
    check(proc.returncode == 0, "Audit exits zero", {"stdout": proc.stdout, "stderr": proc.stderr})

    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(data["schema_version"] == "nwdp_demographic_enrichment_readiness.v1", "Schema version is stable", data)
    check(data["healthy"] is True, "Audit is healthy", data)
    check(data["mode"] == "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_READINESS", "Audit mode is read-only", data)
    check(data["raw_geojson_file_count"] >= 36, "Audit sees all-state raw NWDP GeoJSON files", data["raw_geojson_file_count"])
    check(data["total_nwdp_features"] >= 600000, "Audit sees national NWDP features", data["total_nwdp_features"])
    check(data["population_nonzero"] >= 600000, "Audit sees broad non-zero population coverage", data["population_nonzero"])
    check(data["households_nonzero"] >= 600000, "Audit sees broad non-zero household coverage", data["households_nonzero"])
    check(data["population_coverage_ratio"] >= 0.90, "Population coverage is above 90%", data["population_coverage_ratio"])
    check(data["household_coverage_ratio"] >= 0.90, "Household coverage is above 90%", data["household_coverage_ratio"])
    check(data["state_count"] >= 36, "Audit covers staged states/UTs", data["state_count"])

    fields = dict(data["top_field_presence"])
    for key in [
        "total_population_village",
        "total_households",
        "total_male_population_village",
        "total_female_population_village",
        "net_area_sown",
        "total_unirrigated_land",
    ]:
        check(key in fields, f"Audit captures {key}", fields)

    check(data["recommended_design"]["do_not_overwrite_lgd"] is True, "Design keeps LGD canonical", data["recommended_design"])
    check(
        data["recommended_design"]["future_official_census_layer_should_remain_separate"] is True,
        "Design keeps future official Census layer separate",
        data["recommended_design"],
    )

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "Audit attempts no DB writes", guardrails)
    check(guardrails["lgd_geography_overwritten"] is False, "Audit does not overwrite LGD geography", guardrails)
    check(guardrails["official_census_claimed_imported"] is False, "Audit does not claim official Census import", guardrails)
    check(guardrails["android_behavior_changed"] is False, "Audit keeps Android unchanged", guardrails)
    check(guardrails["runtime_lookup_enabled"] is False, "Audit keeps runtime lookup disabled", guardrails)

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT READINESS REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
