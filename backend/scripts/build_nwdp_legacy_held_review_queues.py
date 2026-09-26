#!/usr/bin/env python3
"""Build deterministic, read-only review queues for legacy held NWDP rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_checksum,
    sha256_file,
)


SCHEMA_VERSION = "nwdp_legacy_held_review_queues.v1"
EXPECTED_INPUT_SHA256 = (
    "365ff19d987e562fed6884a8506dbe7c89a575f953855e68b4c4db6fcbe8c2d7"
)
EXPECTED_ROW_COUNT = 10_052

EXPECTED_DISPOSITIONS = {
    "CANONICAL_BLOCK_MISMATCH": 2_272,
    "CURRENT_VILLAGE_SAME_STATE_OTHER_DISTRICT": 192,
    "MISSING_CANONICAL_DISTRICT": 3,
    "MISSING_CANONICAL_STATE": 12,
    "NAME_REVIEW_CURRENT_HIERARCHY": 7_540,
    "NO_CURRENT_CANONICAL_VILLAGE": 1,
    "SOURCE_SUBDISTRICT_MISSING": 32,
}

QUEUE_RULES = {
    "NAME_REVIEW_CURRENT_HIERARCHY": (
        "NAME_EQUIVALENCE_REVIEW",
        "Review source and canonical village names; approve only an evidenced equivalence.",
    ),
    "CANONICAL_BLOCK_MISMATCH": (
        "BLOCK_PARENT_REVIEW",
        "Determine whether the source subdistrict or canonical village parent is current.",
    ),
    "CURRENT_VILLAGE_SAME_STATE_OTHER_DISTRICT": (
        "DISTRICT_PARENT_REVIEW",
        "Review the current district assignment before any mapping or reparenting decision.",
    ),
    "SOURCE_SUBDISTRICT_MISSING": (
        "SOURCE_HIERARCHY_REVIEW",
        "Resolve the source subdistrict against current authoritative LGD hierarchy.",
    ),
    "MISSING_CANONICAL_STATE": (
        "CANONICAL_STATE_GAP_REVIEW",
        "Review the missing canonical state or union-territory hierarchy.",
    ),
    "MISSING_CANONICAL_DISTRICT": (
        "CANONICAL_DISTRICT_GAP_REVIEW",
        "Review the missing canonical district and its authoritative parent chain.",
    ),
    "NO_CURRENT_CANONICAL_VILLAGE": (
        "CURRENT_LGD_ABSENCE_REVIEW",
        "Confirm current LGD absence and determine whether a later additive import is valid.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "nwdp_legacy_held_current_reconciliation_rows.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"NON_OBJECT_JSONL_ROW:{line_number}")

            rows.append(value)

    return rows


def text(value: Any) -> str:
    return "" if value is None else str(value)


def sort_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        text(row.get("review_queue")),
        text(row.get("source_state")),
        text(row.get("source_district_code")),
        text(row.get("source_subdistrict_code")),
        text(row.get("source_village_code")),
        text(row.get("candidate_id")),
    )


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        raise ValueError(f"INPUT_NOT_FOUND:{input_path}")

    input_sha256 = sha256_file(input_path)
    input_rows = load_jsonl(input_path)

    dispositions = Counter(
        text(row.get("current_disposition"))
        for row in input_rows
    )

    output_rows: list[dict[str, Any]] = []
    unknown_dispositions: list[str] = []

    for row in input_rows:
        disposition = text(row.get("current_disposition"))
        rule = QUEUE_RULES.get(disposition)

        if rule is None:
            unknown_dispositions.append(disposition)
            continue

        review_queue, required_action = rule

        output_rows.append(
            {
                **row,
                "review_queue": review_queue,
                "required_action": required_action,
                "automatic_action_authorized": False,
            }
        )

    output_rows.sort(key=sort_key)

    queue_counts = Counter(
        text(row.get("review_queue"))
        for row in output_rows
    )

    state_queue_counts: dict[str, Counter[str]] = {}

    for row in output_rows:
        state = text(row.get("source_state"))
        state_queue_counts.setdefault(state, Counter())[
            text(row.get("review_queue"))
        ] += 1

    candidate_ids = [
        text(row.get("candidate_id"))
        for row in output_rows
    ]
    source_feature_ids = [
        text(row.get("source_feature_id"))
        for row in output_rows
    ]

    checks = {
        "input_sha256_pinned": (
            input_sha256 == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(input_rows) == EXPECTED_ROW_COUNT
        ),
        "input_dispositions_exact": (
            dict(sorted(dispositions.items()))
            == EXPECTED_DISPOSITIONS
        ),
        "all_rows_classified": (
            not unknown_dispositions
            and len(output_rows) == len(input_rows)
        ),
        "candidate_identity_unique": (
            len(candidate_ids) == len(set(candidate_ids))
            and all(candidate_ids)
        ),
        "source_feature_identity_unique": (
            len(source_feature_ids) == len(set(source_feature_ids))
            and all(source_feature_ids)
        ),
        "automatic_actions_disabled": all(
            row["automatic_action_authorized"] is False
            for row in output_rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
    }

    healthy = all(checks.values())

    rows_path = (
        output_dir
        / "nwdp_legacy_held_review_queue_rows.jsonl"
    )
    summary_path = (
        output_dir
        / "nwdp_legacy_held_review_queues.json"
    )

    atomic_write_jsonl(rows_path, output_rows)
    rows_sha256 = sha256_file(rows_path)

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PARTITIONED_NOT_AUTHORIZED",
        "healthy": healthy,
        "database_writes_attempted": False,
        "checks": checks,
        "policy": {
            "automatic_name_approval_authorized": False,
            "canonical_reparenting_authorized": False,
            "canonical_inserts_authorized": False,
            "runtime_staging_authorized": False,
            "runtime_activation_authorized": False,
            "project_matching_authorized": False,
        },
        "input": str(input_path),
        "input_sha256": input_sha256,
        "row_count": len(output_rows),
        "counts_by_review_queue": dict(
            sorted(queue_counts.items())
        ),
        "state_review_queue_matrix": {
            state: dict(sorted(counts.items()))
            for state, counts
            in sorted(state_queue_counts.items())
        },
        "unknown_dispositions": sorted(
            set(unknown_dispositions)
        ),
        "rows": str(rows_path),
        "rows_sha256": rows_sha256,
    }

    summary["summary_checksum"] = canonical_checksum(summary)
    atomic_write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
