#!/usr/bin/env python3
"""Build a read-only Core-layer ingestion plan for uncovered LGD districts."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

READINESS_REPORT = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "climate_agro_ecology_readiness_report.json"
)
CROSS_LAYER_BASELINE = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "geography_cross_layer_readiness_baseline.json"
)
OUTPUT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
SUMMARY_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_ingestion_plan.json"
)
ROWS_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_ingestion_plan_rows.jsonl"
)
CSV_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_ingestion_plan.csv"
)

EXPECTED_INPUT_HASHES = {
    "climate_readiness_report": (
        "daf108a90d95d6ec4af1f467f73315b7506b9426868004251b5b81d0b62b6f41"
    ),
    "cross_layer_baseline": (
        "061c3da1dfab80d8927fb0e4517f2ced15ea05049b6e79523200e1b3f35297ae"
    ),
}

CORE_LAYERS = (
    "AGRO_CLIMATIC_ZONE",
    "AGRO_ECOLOGICAL_ZONE",
    "BIOGEOGRAPHIC_ZONE",
)

CSV_FIELDS = (
    "state_or_ut",
    "source_state_or_ut",
    "state_lgd_code",
    "district",
    "district_lgd_code",
    "lgd_village_count",
    "nwdp_state_overlay_eligible_candidate_count",
    "nwdp_state_overlay_available",
    "nwdp_state_zero_eligible_exclusion",
    "ingestion_priority",
    "ingestion_route",
    "required_layers",
    "current_climate_mapping_count",
    "current_crop_climate_rule_count",
    "review_decision",
    "reviewer",
    "review_notes",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def summary_checksum(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalized_state(value: str) -> str:
    aliases = {
        "andaman and nicobar islands": (
            "Andaman And Nicobar Islands"
        ),
        "dadra and nagar haveli and daman diu": (
            "Dadra And Nagar Haveli And Daman And Diu"
        ),
        "jammu and kashmir": "Jammu & Kashmir",
        "jammu kashmir": "Jammu & Kashmir",
        "nct of delhi": "Delhi",
        "orissa": "Odisha",
        "pondicherry": "Puducherry",
        "the dadra and nagar haveli and daman and diu": (
            "Dadra And Nagar Haveli And Daman And Diu"
        ),
    }
    normalized = " ".join(value.strip().split())
    return aliases.get(normalized.casefold(), normalized)


def state_overlay_index(
    baseline: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        row["state_or_ut"]: row
        for row in baseline["state_rows"]
    }


def route_district(
    district: dict[str, Any],
    state_overlay: dict[str, Any] | None,
) -> tuple[str, str]:
    village_count = int(district["lgd_village_count"])

    if (
        state_overlay
        and state_overlay["nwdp_overlay_zero_eligible_exclusion"]
    ):
        return (
            "I4_SOURCE_EVIDENCE_REQUIRED",
            "AUTHORITATIVE_SOURCE_OR_NEW_GEOMETRY_REQUIRED",
        )

    if not state_overlay or not state_overlay["nwdp_overlay_healthy"]:
        return (
            "I3_OVERLAY_EVIDENCE_GAP",
            "OVERLAY_EVIDENCE_RECONCILIATION_REQUIRED",
        )

    if village_count >= 1_000:
        return (
            "I1_HIGH_IMPACT_OVERLAY_INGESTION",
            "DISTRICT_CROSSWALK_FROM_VERIFIED_NWDP_OVERLAY",
        )

    return (
        "I2_STANDARD_OVERLAY_INGESTION",
        "DISTRICT_CROSSWALK_FROM_VERIFIED_NWDP_OVERLAY",
    )


def main() -> int:
    readiness = load_json(READINESS_REPORT)
    baseline = load_json(CROSS_LAYER_BASELINE)

    input_hashes = {
        "climate_readiness_report": sha256(READINESS_REPORT),
        "cross_layer_baseline": sha256(CROSS_LAYER_BASELINE),
    }

    overlay_by_state = state_overlay_index(baseline)

    uncovered = [
        row
        for row in readiness["district_rows"]
        if row["needs_climate_mapping"] is True
    ]

    plan_rows: list[dict[str, Any]] = []

    for district in uncovered:
        source_state = district["state_or_ut"]
        state = normalized_state(source_state)
        overlay = overlay_by_state.get(state)
        priority, route = route_district(district, overlay)

        plan_rows.append(
            {
                "state_or_ut": state,
                "source_state_or_ut": source_state,
                "state_lgd_code": str(district["state_lgd_code"]),
                "district": district["district"],
                "district_lgd_code": str(
                    district["district_lgd_code"]
                ),
                "lgd_village_count": int(
                    district["lgd_village_count"]
                ),
                "nwdp_state_overlay_eligible_candidate_count": (
                    int(
                        overlay[
                            "nwdp_overlay_eligible_candidate_count"
                        ]
                    )
                    if overlay
                    else 0
                ),
                "nwdp_state_overlay_available": bool(
                    overlay and overlay["nwdp_overlay_healthy"]
                ),
                "nwdp_state_zero_eligible_exclusion": bool(
                    overlay
                    and overlay[
                        "nwdp_overlay_zero_eligible_exclusion"
                    ]
                ),
                "ingestion_priority": priority,
                "ingestion_route": route,
                "required_layers": list(CORE_LAYERS),
                "current_climate_mapping_count": int(
                    district["climate_mapping_count"]
                ),
                "current_crop_climate_rule_count": int(
                    district["crop_climate_rule_count"]
                ),
                "review_decision": "",
                "reviewer": "",
                "review_notes": "",
            }
        )

    plan_rows.sort(
        key=lambda row: (
            row["ingestion_priority"],
            -row["lgd_village_count"],
            row["state_or_ut"],
            row["district_lgd_code"],
        )
    )

    priority_counts = Counter(
        row["ingestion_priority"]
        for row in plan_rows
    )
    route_counts = Counter(
        row["ingestion_route"]
        for row in plan_rows
    )

    state_accumulator: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "district_count": 0,
            "lgd_village_count": 0,
            "priority_counts": Counter(),
        }
    )

    for row in plan_rows:
        state = state_accumulator[row["state_or_ut"]]
        state["district_count"] += 1
        state["lgd_village_count"] += row["lgd_village_count"]
        state["priority_counts"][row["ingestion_priority"]] += 1

    state_plan = []
    for state_name in sorted(state_accumulator):
        state = state_accumulator[state_name]
        state_plan.append(
            {
                "state_or_ut": state_name,
                "uncovered_district_count": state["district_count"],
                "uncovered_lgd_village_count": (
                    state["lgd_village_count"]
                ),
                "counts_by_ingestion_priority": dict(
                    sorted(state["priority_counts"].items())
                ),
            }
        )

    district_identities = [
        (
            row["state_lgd_code"],
            row["district_lgd_code"],
        )
        for row in plan_rows
    ]

    overlay_routed_count = sum(
        1
        for row in plan_rows
        if row["ingestion_route"]
        == "DISTRICT_CROSSWALK_FROM_VERIFIED_NWDP_OVERLAY"
    )
    source_research_count = sum(
        1
        for row in plan_rows
        if row["ingestion_route"]
        == "AUTHORITATIVE_SOURCE_OR_NEW_GEOMETRY_REQUIRED"
    )
    evidence_gap_count = sum(
        1
        for row in plan_rows
        if row["ingestion_route"]
        == "OVERLAY_EVIDENCE_RECONCILIATION_REQUIRED"
    )

    checks = {
        "automatic_ingestion_disabled": True,
        "automatic_runtime_activation_disabled": True,
        "cross_layer_baseline_healthy": (
            baseline.get("healthy") is True
        ),
        "district_identity_unique": (
            len(district_identities)
            == len(set(district_identities))
        ),
        "input_hashes_pinned": (
            input_hashes == EXPECTED_INPUT_HASHES
        ),
        "no_database_writes": True,
        "not_authorized": True,
        "plan_row_count_exact": len(plan_rows) == 593,
        "readiness_report_healthy": (
            readiness.get("healthy") is True
        ),
        "review_fields_blank": all(
            not row["review_decision"]
            and not row["reviewer"]
            and not row["review_notes"]
            for row in plan_rows
        ),
        "source_district_partition_exact": (
            len(plan_rows)
            == int(
                readiness["summary"][
                    "districts_without_climate_mapping"
                ]
            )
        ),
        "three_core_layers_required": all(
            tuple(row["required_layers"]) == CORE_LAYERS
            for row in plan_rows
        ),
        "unmapped_districts_only": all(
            row["current_climate_mapping_count"] == 0
            for row in plan_rows
        ),
    }

    result: dict[str, Any] = {
        "schema_version": (
            "geography_core_layer_district_ingestion_plan.v1"
        ),
        "status": "INGESTION_PLAN_BUILT_NOT_AUTHORIZED",
        "healthy": all(checks.values()),
        "checks": checks,
        "source_artifacts": {
            "climate_readiness_report": {
                "path": str(READINESS_REPORT),
                "sha256": input_hashes[
                    "climate_readiness_report"
                ],
                "schema_version": readiness["schema_version"],
            },
            "cross_layer_baseline": {
                "path": str(CROSS_LAYER_BASELINE),
                "sha256": input_hashes[
                    "cross_layer_baseline"
                ],
                "schema_version": baseline["schema_version"],
            },
        },
        "required_layers": list(CORE_LAYERS),
        "row_count": len(plan_rows),
        "covered_district_count": int(
            readiness["summary"][
                "districts_with_climate_mapping"
            ]
        ),
        "uncovered_district_count": len(plan_rows),
        "total_district_count": int(
            readiness["summary"]["state_district_row_count"]
        ),
        "uncovered_lgd_village_count": sum(
            row["lgd_village_count"]
            for row in plan_rows
        ),
        "overlay_routed_district_count": overlay_routed_count,
        "source_research_district_count": source_research_count,
        "overlay_evidence_gap_district_count": (
            evidence_gap_count
        ),
        "counts_by_ingestion_priority": dict(
            sorted(priority_counts.items())
        ),
        "counts_by_ingestion_route": dict(
            sorted(route_counts.items())
        ),
        "state_plan": state_plan,
        "rows": str(ROWS_PATH),
        "csv": str(CSV_PATH),
        "policy": {
            "lgd_remains_canonical_geography": True,
            "core_layers_are_reference_intelligence": True,
            "district_crosswalk_requires_review": True,
            "automatic_ingestion_authorized": False,
            "canonical_geography_changes_authorized": False,
            "climate_mapping_writes_authorized": False,
            "runtime_climate_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
        "database_writes_attempted": False,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with ROWS_PATH.open("w", encoding="utf-8") as handle:
        for row in plan_rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    with CSV_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for row in plan_rows:
            csv_row = dict(row)
            csv_row["required_layers"] = "|".join(
                row["required_layers"]
            )
            writer.writerow(csv_row)

    result["rows_sha256"] = sha256(ROWS_PATH)
    result["csv_sha256"] = sha256(CSV_PATH)

    checksum_source = dict(result)
    result["summary_checksum"] = summary_checksum(
        checksum_source
    )

    SUMMARY_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
