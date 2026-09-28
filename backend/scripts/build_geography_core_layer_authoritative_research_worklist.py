#!/usr/bin/env python3
"""Build the Core-layer authoritative research worklist.

Read-only. Selects C3 authoritative-source, C4 stale-hierarchy, and C5
current-district-geometry gaps from the pinned district crosswalk template.
It writes local review artifacts only and authorizes no database or runtime
changes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
DEFAULT_INPUT = DEFAULT_DIR / (
    "geography_core_layer_district_crosswalk_review_batch_rows.jsonl"
)

EXPECTED_INPUT_SHA256 = (
    "d6b1d185216b67d144d58336e66df2ccb2880c8bac71fa0d1296318eacc86d4e"
)
EXPECTED_INPUT_ROW_COUNT = 1779

PRIORITY_ROUTES = {
    "C3_AUTHORITATIVE_SOURCE_REVIEW": (
        "AUTHORITATIVE_AGRO_CLIMATE_SOURCE_REQUIRED"
    ),
    "C4_STALE_HIERARCHY_CONFLICT": (
        "AUTHORITATIVE_HIERARCHY_RECONCILIATION_REQUIRED"
    ),
    "C5_CURRENT_DISTRICT_GEOMETRY_GAP": (
        "AUTHORITATIVE_CURRENT_DISTRICT_GEOMETRY_REQUIRED"
    ),
}

EXPECTED_COUNTS_BY_PRIORITY = {
    "C3_AUTHORITATIVE_SOURCE_REVIEW": 69,
    "C4_STALE_HIERARCHY_CONFLICT": 6,
    "C5_CURRENT_DISTRICT_GEOMETRY_GAP": 33,
}
EXPECTED_DISTRICTS_BY_PRIORITY = {
    "C3_AUTHORITATIVE_SOURCE_REVIEW": 23,
    "C4_STALE_HIERARCHY_CONFLICT": 2,
    "C5_CURRENT_DISTRICT_GEOMETRY_GAP": 11,
}

RESEARCH_FIELDS = {
    "research_status": "",
    "authoritative_source_type": "",
    "authoritative_source_title": "",
    "authoritative_source_url": "",
    "authoritative_source_date": "",
    "authoritative_notification_number": "",
    "verified_state_lgd_code": "",
    "verified_district_lgd_code": "",
    "verified_district_name": "",
    "verified_geometry_source": "",
    "researcher": "",
    "research_notes": "",
}

SCHEMA_VERSION = (
    "geography_core_layer_authoritative_research_worklist.v1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-rows",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DIR,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def district_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("state_lgd_code") or ""),
        str(row.get("district_lgd_code") or ""),
    )


def row_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        *district_identity(row),
        str(row.get("region_system") or ""),
    )


def research_scope(priority: str) -> str:
    if priority == "C3_AUTHORITATIVE_SOURCE_REVIEW":
        return (
            "Verify an authoritative agro-climatic, agro-ecological, "
            "or biogeographic district assignment."
        )
    if priority == "C4_STALE_HIERARCHY_CONFLICT":
        return (
            "Reconcile the source district hierarchy against current LGD "
            "before evaluating any layer mapping."
        )
    return (
        "Obtain authoritative current-district geometry before calculating "
        "or approving any Core-layer overlap."
    )


def required_evidence(priority: str) -> list[str]:
    if priority == "C3_AUTHORITATIVE_SOURCE_REVIEW":
        return [
            "AUTHORITATIVE_AGRO_CLIMATE_SOURCE",
            "SOURCE_PUBLICATION_DATE_OR_VERSION",
            "DISTRICT_AND_REGION_ASSIGNMENT",
        ]
    if priority == "C4_STALE_HIERARCHY_CONFLICT":
        return [
            "CURRENT_LGD_HIERARCHY_CONFIRMATION",
            "OFFICIAL_DISTRICT_CREATION_OR_REORGANIZATION_SOURCE",
            "CURRENT_PARENT_STATE_CONFIRMATION",
        ]
    return [
        "CURRENT_LGD_HIERARCHY_CONFIRMATION",
        "AUTHORITATIVE_CURRENT_DISTRICT_GEOMETRY",
        "GEOMETRY_SOURCE_DATE_OR_VERSION",
    ]


def main() -> int:
    args = parse_args()
    input_hash = sha256(args.input_rows)
    input_rows = read_jsonl(args.input_rows)

    selected = []
    for source in input_rows:
        priority = str(source["crosswalk_review_priority"])
        if priority not in PRIORITY_ROUTES:
            continue

        row = {
            "state_or_ut": source.get("state_or_ut"),
            "source_state_or_ut": source.get(
                "source_state_or_ut"
            ),
            "state_lgd_code": source.get("state_lgd_code"),
            "district": source.get("district"),
            "district_lgd_code": source.get(
                "district_lgd_code"
            ),
            "lgd_village_count": source.get(
                "lgd_village_count"
            ),
            "region_system": source.get("region_system"),
            "region_class_code": source.get(
                "region_class_code"
            ),
            "region_class_name": source.get(
                "region_class_name"
            ),
            "target_region_id": source.get(
                "target_region_id"
            ),
            "target_region_code": source.get(
                "target_region_code"
            ),
            "candidate_present": source.get(
                "candidate_present"
            ),
            "candidate_excluded": source.get(
                "candidate_excluded"
            ),
            "candidate_exclusion_reasons": source.get(
                "candidate_exclusion_reasons"
            ),
            "crosswalk_category": source.get(
                "crosswalk_category"
            ),
            "low_overlap_bucket": source.get(
                "low_overlap_bucket"
            ),
            "overlap_percent_of_district": source.get(
                "overlap_percent_of_district"
            ),
            "crosswalk_review_priority": priority,
            "research_route": PRIORITY_ROUTES[priority],
            "research_scope": research_scope(priority),
            "required_evidence": required_evidence(priority),
            "lgd_remains_canonical": True,
            "mapping_approval_authorized": False,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            **RESEARCH_FIELDS,
        }
        selected.append(row)

    selected.sort(
        key=lambda row: (
            str(row["state_or_ut"]),
            str(row["district_lgd_code"]),
            str(row["region_system"]),
        )
    )

    counts_by_priority = Counter(
        row["crosswalk_review_priority"]
        for row in selected
    )
    counts_by_route = Counter(
        row["research_route"] for row in selected
    )

    districts_by_priority: dict[str, set[tuple[str, str]]] = (
        defaultdict(set)
    )
    for row in selected:
        districts_by_priority[
            row["crosswalk_review_priority"]
        ].add(district_identity(row))

    district_counts_by_priority = {
        priority: len(districts_by_priority[priority])
        for priority in sorted(PRIORITY_ROUTES)
    }

    state_accumulator: dict[str, dict[str, Any]] = {}
    for row in selected:
        state = str(row["state_or_ut"])
        state_entry = state_accumulator.setdefault(
            state,
            {
                "state_or_ut": state,
                "districts": set(),
                "row_count": 0,
                "priorities": Counter(),
            },
        )
        state_entry["districts"].add(
            district_identity(row)
        )
        state_entry["row_count"] += 1
        state_entry["priorities"][
            row["crosswalk_review_priority"]
        ] += 1

    state_workload = []
    for state in sorted(state_accumulator):
        entry = state_accumulator[state]
        state_workload.append(
            {
                "state_or_ut": state,
                "district_count": len(entry["districts"]),
                "row_count": entry["row_count"],
                "counts_by_priority": dict(
                    sorted(entry["priorities"].items())
                ),
            }
        )

    identities = [row_identity(row) for row in selected]
    district_identities = {
        district_identity(row) for row in selected
    }

    checks = {
        "input_sha256_pinned": (
            input_hash == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(input_rows) == EXPECTED_INPUT_ROW_COUNT
        ),
        "research_row_count_exact": (
            len(selected)
            == sum(EXPECTED_COUNTS_BY_PRIORITY.values())
        ),
        "research_district_count_exact": (
            len(district_identities)
            == sum(
                EXPECTED_DISTRICTS_BY_PRIORITY.values()
            )
        ),
        "priority_counts_exact": (
            dict(sorted(counts_by_priority.items()))
            == EXPECTED_COUNTS_BY_PRIORITY
        ),
        "district_priority_counts_exact": (
            district_counts_by_priority
            == EXPECTED_DISTRICTS_BY_PRIORITY
        ),
        "row_identity_unique": (
            len(identities) == len(set(identities))
        ),
        "three_core_layers_per_district": all(
            sum(
                1
                for row in selected
                if district_identity(row) == identity
            )
            == 3
            for identity in district_identities
        ),
        "research_fields_blank": all(
            all(row[field] == "" for field in RESEARCH_FIELDS)
            for row in selected
        ),
        "no_database_writes": True,
        "not_authorized": True,
        "automatic_actions_disabled": True,
    }
    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / (
        "geography_core_layer_authoritative_research_worklist_rows.jsonl"
    )
    csv_path = args.output_dir / (
        "geography_core_layer_authoritative_research_worklist.csv"
    )
    summary_path = args.output_dir / (
        "geography_core_layer_authoritative_research_worklist.json"
    )

    with rows_path.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    flat_rows = []
    for row in selected:
        flat = dict(row)
        flat["required_evidence"] = json.dumps(
            row["required_evidence"],
            ensure_ascii=False,
            sort_keys=True,
        )
        flat_rows.append(flat)

    fieldnames = sorted(
        {field for row in flat_rows for field in row}
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(flat_rows)

    core_summary = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "AUTHORITATIVE_RESEARCH_WORKLIST_BUILT_NOT_AUTHORIZED"
            if healthy
            else "AUTHORITATIVE_RESEARCH_WORKLIST_INVALID"
        ),
        "healthy": healthy,
        "database_writes_attempted": False,
        "input": str(args.input_rows.resolve()),
        "input_sha256": input_hash,
        "input_row_count": len(input_rows),
        "row_count": len(selected),
        "district_count": len(district_identities),
        "counts_by_priority": dict(
            sorted(counts_by_priority.items())
        ),
        "counts_by_research_route": dict(
            sorted(counts_by_route.items())
        ),
        "district_counts_by_priority": (
            district_counts_by_priority
        ),
        "state_workload": state_workload,
        "checks": checks,
        "policy": {
            "lgd_remains_canonical": True,
            "human_research_required": True,
            "candidate_mapping_changes_authorized": False,
            "canonical_geography_changes_authorized": False,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
    }

    summary = {
        **core_summary,
        "rows": str(rows_path.resolve()),
        "rows_sha256": sha256(rows_path),
        "csv": str(csv_path.resolve()),
        "csv_sha256": sha256(csv_path),
        "summary_checksum": canonical_sha256(core_summary),
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
