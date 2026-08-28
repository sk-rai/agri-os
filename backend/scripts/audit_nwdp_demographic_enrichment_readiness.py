#!/usr/bin/env python3
"""Read-only NWDP demographic enrichment readiness audit.

This checks demographic/amenity-like attributes bundled in NWDP village
boundary GeoJSON properties. It does not claim official Census import and
does not write DB rows.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RAW_DIR = Path("data/raw/nwdp_boundary_all_state/20260824T110250Z")
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-enrichment-readiness.json")


INTERESTING_TERMS = [
    "population",
    "household",
    "male",
    "female",
    "area",
    "forest",
    "irrig",
    "water",
    "well",
    "handpump",
    "tubewell",
    "spring",
    "river",
    "tank",
    "pond",
    "lake",
    "drainage",
    "pin",
    "town",
    "urban",
    "rural",
]


def clean_key(key: Any) -> str:
    return str(key).strip().replace("\n", "")


def numeric(value: Any) -> float:
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def audit(raw_dir: Path, output: Path, state_summary_csv: Path | None) -> dict[str, Any]:
    total = 0
    population_nonzero = 0
    households_nonzero = 0
    area_nonzero = 0
    state_counts: Counter[str] = Counter()
    state_population_nonzero: Counter[str] = Counter()
    state_households_nonzero: Counter[str] = Counter()
    field_presence: Counter[str] = Counter()
    sample_rows: list[dict[str, Any]] = []

    files = sorted(raw_dir.glob("*.geojson"))

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, feature in enumerate(data.get("features", [])):
            total += 1
            props = {clean_key(k): v for k, v in feature.get("properties", {}).items()}

            state = props.get("state_name") or props.get("state") or path.stem
            state_counts[state] += 1

            for key, value in props.items():
                if any(term in key.lower() for term in INTERESTING_TERMS):
                    if value not in (None, "", " "):
                        field_presence[key] += 1

            population = numeric(props.get("total_population_village"))
            households = numeric(props.get("total_households"))
            area = numeric(props.get("total_geographical_area")) or numeric(props.get("shape_area"))

            if population > 0:
                population_nonzero += 1
                state_population_nonzero[state] += 1
            if households > 0:
                households_nonzero += 1
                state_households_nonzero[state] += 1
            if area > 0:
                area_nonzero += 1

            if len(sample_rows) < 20 and (population > 0 or households > 0):
                sample_rows.append(
                    {
                        "file": str(path),
                        "feature_index": index,
                        "state": state,
                        "district": props.get("district"),
                        "subdistrict": props.get("subdistric"),
                        "block": props.get("block"),
                        "village": props.get("village"),
                        "vlcode": props.get("vlcode"),
                        "total_population_village": population,
                        "total_households": households,
                        "total_male_population_village": numeric(props.get("total_male_population_village")),
                        "total_female_population_village": numeric(props.get("total_female_population_village")),
                        "total_geographical_area": numeric(props.get("total_geographical_area")),
                        "shape_area": numeric(props.get("shape_area")),
                    }
                )

    state_rows = []
    for state, count in sorted(state_counts.items()):
        state_rows.append(
            {
                "state": state,
                "nwdp_features": count,
                "population_nonzero": state_population_nonzero[state],
                "population_coverage_ratio": round(state_population_nonzero[state] / count, 6) if count else 0,
                "households_nonzero": state_households_nonzero[state],
                "household_coverage_ratio": round(state_households_nonzero[state] / count, 6) if count else 0,
            }
        )

    result = {
        "schema_version": "nwdp_demographic_enrichment_readiness.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": bool(files) and total > 0 and population_nonzero > 0 and households_nonzero > 0,
        "mode": "READ_ONLY_NWDP_DEMOGRAPHIC_ENRICHMENT_READINESS",
        "source_claim_boundary": (
            "NWDP raw boundary properties include demographic/amenity-like fields. "
            "This is not an official Census 2011 PCA/DCHB import."
        ),
        "raw_dir": str(raw_dir),
        "raw_geojson_file_count": len(files),
        "total_nwdp_features": total,
        "population_nonzero": population_nonzero,
        "population_zero_or_missing": total - population_nonzero,
        "population_coverage_ratio": round(population_nonzero / total, 6) if total else 0,
        "households_nonzero": households_nonzero,
        "households_zero_or_missing": total - households_nonzero,
        "household_coverage_ratio": round(households_nonzero / total, 6) if total else 0,
        "area_nonzero": area_nonzero,
        "state_count": len(state_rows),
        "top_field_presence": field_presence.most_common(80),
        "sample_rows": sample_rows,
        "recommended_design": {
            "do_not_overwrite_lgd": True,
            "recommended_new_layer": "geography_village_demographic_profiles",
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "future_official_census_layer_should_remain_separate": True,
            "join_key_preference": [
                "safe NWDP DIRECT_VLCODE_MATCH candidate proposed_village_id",
                "confirmed LGD/vlcode equivalence",
                "manual-reviewed crosswalk for ambiguous cases",
            ],
        },
        "guardrails": {
            "db_writes_attempted": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "android_behavior_changed": False,
            "runtime_lookup_enabled": False,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")

    if state_summary_csv:
        state_summary_csv.parent.mkdir(parents=True, exist_ok=True)
        with state_summary_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "state",
                    "nwdp_features",
                    "population_nonzero",
                    "population_coverage_ratio",
                    "households_nonzero",
                    "household_coverage_ratio",
                ],
            )
            writer.writeheader()
            writer.writerows(state_rows)

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-summary-csv", type=Path, default=Path("/tmp/nwdp-demographic-enrichment-state-summary.csv"))
    args = parser.parse_args()

    result = audit(args.raw_dir, args.output, args.state_summary_csv)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "state_summary_csv": str(args.state_summary_csv),
                "healthy": result["healthy"],
                "total_nwdp_features": result["total_nwdp_features"],
                "population_nonzero": result["population_nonzero"],
                "population_coverage_ratio": result["population_coverage_ratio"],
                "households_nonzero": result["households_nonzero"],
                "household_coverage_ratio": result["household_coverage_ratio"],
                "state_count": result["state_count"],
            },
            indent=2,
        )
    )

    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
