#!/usr/bin/env python3
"""Build a current-LGD Core-layer district crosswalk review batch.

Read-only planning artifact. It reconciles the reviewed equal-area polygon
candidate plan with the current 593-district ingestion plan. It does not write
climate mappings or enable runtime behavior.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

INGESTION_PLAN = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "geography_core_layer_district_ingestion_plan.csv"
)
MANUAL_IMPORT_PLAN = ROOT / (
    "data/staged/core_stack/manual_review_import_plan/"
    "core_lgd_manual_review_import_plan.csv"
)
OUTPUT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
SUMMARY_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_crosswalk_review_batch.json"
)
ROWS_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_crosswalk_review_batch_rows.jsonl"
)
CSV_PATH = OUTPUT_DIR / (
    "geography_core_layer_district_crosswalk_review_batch.csv"
)

EXPECTED_INPUT_HASHES = {
    "district_ingestion_plan": (
        "9b200fc1a4dbb33d28e8b399a7af40b353b65bb570209e9eefdd061bfe5b8461"
    ),
    "manual_import_plan": (
        "5e2cf7b6ef1f7522d687b7a243d5f74a7a4c0d1aa18b9c8a929f85b462e2d17b"
    ),
}

REGION_SYSTEMS = (
    "CORE_STACK_AGRO_CLIMATIC_ZONE",
    "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
    "CORE_STACK_BIOGEOGRAPHIC_ZONE",
)

ALLOWED_DECISIONS = (
    "APPROVE_INACTIVE_MANUAL_REVIEW_MAPPING",
    "REJECT_DISTRICT_CROSSWALK",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    return str(value or "").strip().casefold() in {
        "true",
        "1",
        "yes",
        "y",
    }


def parse_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def checksum(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify(
    ingestion: dict[str, str],
    candidate: dict[str, str] | None,
) -> tuple[str, str]:
    if (
        ingestion["ingestion_priority"]
        == "I4_SOURCE_EVIDENCE_REQUIRED"
    ):
        return (
            "C3_AUTHORITATIVE_SOURCE_REVIEW",
            "AUTHORITATIVE_SOURCE_REVIEW_REQUIRED",
        )

    if candidate is None:
        return (
            "C5_CURRENT_DISTRICT_GEOMETRY_GAP",
            "CURRENT_DISTRICT_GEOMETRY_REQUIRED",
        )

    if (
        parse_bool(candidate["excluded"])
        or not parse_bool(candidate["would_write_db_row"])
    ):
        return (
            "C4_STALE_HIERARCHY_CONFLICT",
            "CANDIDATE_HIERARCHY_RECONCILIATION_REQUIRED",
        )

    overlap = parse_float(
        candidate["overlap_percent_of_district"]
    )
    if overlap is None or overlap < 60.0:
        return (
            "C2_LOW_OVERLAP_MANUAL_REVIEW",
            "LOW_OVERLAP_MANUAL_REVIEW_REQUIRED",
        )

    return (
        "C1_READY_FOR_MANUAL_REVIEW",
        "INACTIVE_MANUAL_REVIEW_MAPPING_CANDIDATE",
    )


def main() -> int:
    ingestion_rows = read_csv(INGESTION_PLAN)
    candidate_rows = read_csv(MANUAL_IMPORT_PLAN)

    input_hashes = {
        "district_ingestion_plan": sha256(INGESTION_PLAN),
        "manual_import_plan": sha256(MANUAL_IMPORT_PLAN),
    }

    candidate_index: dict[
        tuple[str, str],
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in candidate_rows:
        candidate_index[
            (
                row["district_lgd_code"],
                row["region_system"],
            )
        ].append(row)

    duplicate_candidate_keys = sorted(
        {
            key
            for key, values in candidate_index.items()
            if len(values) != 1
        }
    )

    review_rows: list[dict[str, Any]] = []

    for ingestion in ingestion_rows:
        district_code = ingestion["district_lgd_code"]

        for region_system in REGION_SYSTEMS:
            candidates = candidate_index.get(
                (district_code, region_system),
                [],
            )
            candidate = (
                candidates[0]
                if len(candidates) == 1
                else None
            )

            priority, route = classify(
                ingestion,
                candidate,
            )

            review_rows.append(
                {
                    "state_or_ut": ingestion["state_or_ut"],
                    "source_state_or_ut": ingestion[
                        "source_state_or_ut"
                    ],
                    "state_lgd_code": ingestion[
                        "state_lgd_code"
                    ],
                    "district": ingestion["district"],
                    "district_lgd_code": district_code,
                    "lgd_village_count": int(
                        ingestion["lgd_village_count"]
                    ),
                    "region_system": region_system,
                    "scope_level": "DISTRICT",
                    "ingestion_priority": ingestion[
                        "ingestion_priority"
                    ],
                    "ingestion_route": ingestion[
                        "ingestion_route"
                    ],
                    "crosswalk_review_priority": priority,
                    "crosswalk_review_route": route,
                    "candidate_present": candidate is not None,
                    "candidate_status": (
                        candidate.get(
                            "candidate_review_status"
                        )
                        if candidate
                        else None
                    ),
                    "candidate_confidence": (
                        candidate.get(
                            "candidate_confidence"
                        )
                        if candidate
                        else None
                    ),
                    "candidate_is_active": (
                        parse_bool(
                            candidate.get(
                                "candidate_is_active"
                            )
                        )
                        if candidate
                        else False
                    ),
                    "candidate_excluded": (
                        parse_bool(candidate.get("excluded"))
                        if candidate
                        else False
                    ),
                    "candidate_exclusion_reasons": (
                        candidate.get("exclusion_reasons")
                        if candidate
                        else ""
                    ),
                    "crosswalk_category": (
                        candidate.get("crosswalk_category")
                        if candidate
                        else ""
                    ),
                    "low_overlap_bucket": (
                        candidate.get("low_overlap_bucket")
                        if candidate
                        else ""
                    ),
                    "region_class_code": (
                        candidate.get("region_class_code")
                        if candidate
                        else None
                    ),
                    "region_class_name": (
                        candidate.get("region_class_name")
                        if candidate
                        else None
                    ),
                    "overlap_percent_of_district": (
                        parse_float(
                            candidate.get(
                                "overlap_percent_of_district"
                            )
                        )
                        if candidate
                        else None
                    ),
                    "target_region_id": (
                        candidate.get("target_region_id")
                        if candidate
                        else None
                    ),
                    "target_region_code": (
                        candidate.get("target_region_code")
                        if candidate
                        else None
                    ),
                    "source_references": (
                        candidate.get("source_references")
                        if candidate
                        else "[]"
                    ),
                    "candidate_metadata": (
                        candidate.get("metadata")
                        if candidate
                        else "{}"
                    ),
                    "would_write_inactive_manual_review_row": (
                        bool(
                            candidate
                            and priority
                            == "C1_READY_FOR_MANUAL_REVIEW"
                            and parse_bool(
                                candidate[
                                    "would_write_db_row"
                                ]
                            )
                            and not parse_bool(
                                candidate["excluded"]
                            )
                        )
                    ),
                    "review_decision": "",
                    "reviewer": "",
                    "review_notes": "",
                }
            )

    review_rows.sort(
        key=lambda row: (
            row["crosswalk_review_priority"],
            row["state_or_ut"],
            row["district_lgd_code"],
            row["region_system"],
        )
    )

    district_codes = {
        row["district_lgd_code"]
        for row in review_rows
    }
    review_keys = [
        (
            row["district_lgd_code"],
            row["region_system"],
        )
        for row in review_rows
    ]

    priority_counts = Counter(
        row["crosswalk_review_priority"]
        for row in review_rows
    )
    route_counts = Counter(
        row["crosswalk_review_route"]
        for row in review_rows
    )
    region_counts = Counter(
        row["region_system"]
        for row in review_rows
    )

    district_statuses: dict[str, set[str]] = defaultdict(set)
    for row in review_rows:
        district_statuses[
            row["district_lgd_code"]
        ].add(row["crosswalk_review_priority"])

    districts_by_route = Counter()
    for statuses in district_statuses.values():
        if "C5_CURRENT_DISTRICT_GEOMETRY_GAP" in statuses:
            districts_by_route[
                "CURRENT_DISTRICT_GEOMETRY_REQUIRED"
            ] += 1
        elif "C4_STALE_HIERARCHY_CONFLICT" in statuses:
            districts_by_route[
                "CANDIDATE_HIERARCHY_RECONCILIATION_REQUIRED"
            ] += 1
        elif "C3_AUTHORITATIVE_SOURCE_REVIEW" in statuses:
            districts_by_route[
                "AUTHORITATIVE_SOURCE_REVIEW_REQUIRED"
            ] += 1
        elif "C2_LOW_OVERLAP_MANUAL_REVIEW" in statuses:
            districts_by_route[
                "LOW_OVERLAP_MANUAL_REVIEW_REQUIRED"
            ] += 1
        else:
            districts_by_route[
                "READY_FOR_MANUAL_REVIEW"
            ] += 1

    checks = {
        "allowed_decisions_declared": (
            len(ALLOWED_DECISIONS) == 3
        ),
        "automatic_apply_disabled": True,
        "automatic_runtime_activation_disabled": True,
        "candidate_rows_inactive": all(
            not row["candidate_is_active"]
            for row in review_rows
        ),
        "district_partition_exact": (
            len(district_codes) == 593
        ),
        "input_hashes_pinned": (
            input_hashes == EXPECTED_INPUT_HASHES
        ),
        "no_database_writes": True,
        "not_authorized": True,
        "one_row_per_district_region_system": (
            len(review_keys)
            == len(set(review_keys))
        ),
        "region_partition_exact": (
            region_counts
            == Counter({
                region_system: 593
                for region_system in REGION_SYSTEMS
            })
        ),
        "review_fields_blank": all(
            not row["review_decision"]
            and not row["reviewer"]
            and not row["review_notes"]
            for row in review_rows
        ),
        "review_row_count_exact": (
            len(review_rows) == 593 * 3
        ),
        "source_candidate_keys_unique": (
            not duplicate_candidate_keys
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with ROWS_PATH.open("w", encoding="utf-8") as handle:
        for row in review_rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    fieldnames = sorted(
        {
            key
            for row in review_rows
            for key in row
        }
    )
    with CSV_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(review_rows)

    result: dict[str, Any] = {
        "schema_version": (
            "geography_core_layer_district_crosswalk_review_batch.v1"
        ),
        "status": (
            "DISTRICT_CROSSWALK_REVIEW_BATCH_BUILT_NOT_AUTHORIZED"
        ),
        "healthy": all(checks.values()),
        "checks": checks,
        "allowed_review_decisions": list(
            ALLOWED_DECISIONS
        ),
        "required_region_systems": list(REGION_SYSTEMS),
        "source_artifacts": {
            "district_ingestion_plan": {
                "path": str(INGESTION_PLAN),
                "sha256": input_hashes[
                    "district_ingestion_plan"
                ],
            },
            "manual_import_plan": {
                "path": str(MANUAL_IMPORT_PLAN),
                "sha256": input_hashes[
                    "manual_import_plan"
                ],
            },
        },
        "district_count": len(district_codes),
        "row_count": len(review_rows),
        "counts_by_review_priority": dict(
            sorted(priority_counts.items())
        ),
        "counts_by_review_route": dict(
            sorted(route_counts.items())
        ),
        "district_counts_by_route": dict(
            sorted(districts_by_route.items())
        ),
        "counts_by_region_system": dict(
            sorted(region_counts.items())
        ),
        "candidate_present_count": sum(
            row["candidate_present"]
            for row in review_rows
        ),
        "candidate_missing_count": sum(
            not row["candidate_present"]
            for row in review_rows
        ),
        "inactive_manual_review_write_candidate_count": sum(
            row[
                "would_write_inactive_manual_review_row"
            ]
            for row in review_rows
        ),
        "duplicate_candidate_keys": [
            list(key)
            for key in duplicate_candidate_keys
        ],
        "rows": str(ROWS_PATH),
        "csv": str(CSV_PATH),
        "rows_sha256": sha256(ROWS_PATH),
        "csv_sha256": sha256(CSV_PATH),
        "policy": {
            "lgd_remains_canonical": True,
            "candidate_rows_remain_inactive": True,
            "manual_review_required": True,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
        "database_writes_attempted": False,
    }

    checksum_source = dict(result)
    result["summary_checksum"] = checksum(
        checksum_source
    )

    SUMMARY_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
