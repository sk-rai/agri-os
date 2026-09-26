#!/usr/bin/env python3
"""Build a deterministic review batch for high-similarity legacy NWDP names."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
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


SCHEMA_VERSION = (
    "nwdp_legacy_high_similarity_review_batch.v1"
)
EXPECTED_INPUT_SHA256 = (
    "dd7d68ea2db24f1bb1de9243bdfb9f217a7917fad0f8dc2168d316d4e2af6d62"
)
EXPECTED_INPUT_ROWS = 7_540
EXPECTED_SELECTED_ROWS = 4_004
SELECTED_BAND = "HIGH_LEXICAL_SIMILARITY"

ALLOWED_EVIDENCE_BASES = [
    "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
    "AUTHORITATIVE_SOURCE_CONFIRMATION",
    "OTHER_DOCUMENTED_EVIDENCE",
]
ALLOWED_REVIEW_DECISIONS = [
    "APPROVE_EQUIVALENCE",
    "REJECT_EQUIVALENCE",
    "DEFER_FOR_SOURCE_RESEARCH",
]

CSV_FIELDS = [
    "sequence",
    "review_priority",
    "review_focus",
    "candidate_id",
    "source_feature_id",
    "source_state",
    "source_district_code",
    "source_district_name",
    "source_subdistrict_code",
    "source_subdistrict_name",
    "source_village_code",
    "source_village_name",
    "canonical_village_id",
    "canonical_village_code",
    "canonical_village_name",
    "canonical_district_code",
    "canonical_district_name",
    "canonical_block_code",
    "canonical_block_name",
    "source_name_normalized",
    "canonical_name_normalized",
    "source_name_core",
    "canonical_name_core",
    "levenshtein_distance",
    "sequence_similarity",
    "token_jaccard",
    "evidence_band",
    "evidence_basis",
    "evidence_reference",
    "review_decision",
    "reviewer",
    "review_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "nwdp_legacy_name_review_evidence_rows.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def text(value: Any) -> str:
    return "" if value is None else str(value)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"NON_OBJECT_JSONL_ROW:{line_number}"
                )

            rows.append(value)

    return rows


def review_priority(row: dict[str, Any]) -> str:
    similarity = float(row["sequence_similarity"])
    distance = int(row["levenshtein_distance"])

    if similarity >= 0.95:
        return "P1_NEAR_IDENTICAL"

    if similarity >= 0.90:
        return "P2_STRONG_SIMILARITY"

    if distance == 1:
        return "P3_SINGLE_EDIT_TRANSLITERATION_REVIEW"

    return "P4_OTHER_HIGH_SIMILARITY"


def review_focus(row: dict[str, Any]) -> str:
    priority = review_priority(row)

    if priority == "P3_SINGLE_EDIT_TRANSLITERATION_REVIEW":
        return "VERIFY_VERNACULAR_TRANSLITERATION"

    if priority == "P4_OTHER_HIGH_SIMILARITY":
        return "VERIFY_TRANSLITERATION_OR_SOURCE_VARIANT"

    return "VERIFY_EQUIVALENCE_WITH_AUTHORITATIVE_SOURCE"


def sort_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        text(row.get("review_priority")),
        text(row.get("source_state")),
        text(row.get("source_district_code")),
        text(row.get("source_subdistrict_code")),
        text(row.get("source_village_code")),
        text(row.get("candidate_id")),
    )


def atomic_write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()

        for row in rows:
            writer.writerow({
                field: row.get(field, "")
                for field in CSV_FIELDS
            })

        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary_path, path)


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        raise ValueError(f"INPUT_NOT_FOUND:{input_path}")

    input_sha256 = sha256_file(input_path)
    input_rows = load_jsonl(input_path)

    selected = [
        row
        for row in input_rows
        if row.get("evidence_band") == SELECTED_BAND
    ]

    prepared_rows: list[dict[str, Any]] = []

    for row in selected:
        prepared_rows.append({
            **row,
            "review_priority": review_priority(row),
            "review_focus": review_focus(row),
            "evidence_basis": "",
            "evidence_reference": "",
            "review_decision": "",
            "reviewer": "",
            "review_notes": "",
            "allowed_evidence_bases":
                ALLOWED_EVIDENCE_BASES,
            "allowed_review_decisions":
                ALLOWED_REVIEW_DECISIONS,
            "automatic_equivalence_authorized": False,
            "automatic_runtime_staging_authorized": False,
        })

    prepared_rows.sort(key=sort_key)

    batch_rows = [
        {
            **row,
            "sequence": sequence,
        }
        for sequence, row in enumerate(prepared_rows, 1)
    ]

    priority_counts = Counter(
        text(row.get("review_priority"))
        for row in batch_rows
    )
    state_counts = Counter(
        text(row.get("source_state"))
        for row in batch_rows
    )
    state_priority_counts: dict[str, Counter[str]] = {}

    for row in batch_rows:
        state = text(row.get("source_state"))
        priority = text(row.get("review_priority"))
        state_priority_counts.setdefault(
            state,
            Counter(),
        )[priority] += 1

    candidate_ids = [
        text(row.get("candidate_id"))
        for row in batch_rows
    ]
    source_feature_ids = [
        text(row.get("source_feature_id"))
        for row in batch_rows
    ]

    checks = {
        "input_sha256_pinned": (
            input_sha256 == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(input_rows) == EXPECTED_INPUT_ROWS
        ),
        "selected_row_count_exact": (
            len(batch_rows) == EXPECTED_SELECTED_ROWS
        ),
        "selected_band_exact": all(
            row.get("evidence_band") == SELECTED_BAND
            for row in batch_rows
        ),
        "candidate_identity_unique": (
            len(candidate_ids) == len(set(candidate_ids))
            and all(candidate_ids)
        ),
        "source_feature_identity_unique": (
            len(source_feature_ids)
            == len(set(source_feature_ids))
            and all(source_feature_ids)
        ),
        "review_priorities_present": all(
            text(row.get("review_priority"))
            for row in batch_rows
        ),
        "review_fields_blank": all(
            not text(row.get(field))
            for row in batch_rows
            for field in (
                "evidence_basis",
                "evidence_reference",
                "review_decision",
                "reviewer",
                "review_notes",
            )
        ),
        "automatic_equivalence_disabled": all(
            row["automatic_equivalence_authorized"] is False
            for row in batch_rows
        ),
        "automatic_runtime_staging_disabled": all(
            row["automatic_runtime_staging_authorized"]
            is False
            for row in batch_rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
    }

    healthy = all(checks.values())

    rows_path = (
        output_dir
        / "nwdp_legacy_high_similarity_review_batch_rows.jsonl"
    )
    csv_path = (
        output_dir
        / "nwdp_legacy_high_similarity_review_batch.csv"
    )
    summary_path = (
        output_dir
        / "nwdp_legacy_high_similarity_review_batch.json"
    )

    atomic_write_jsonl(rows_path, batch_rows)
    atomic_write_csv(csv_path, batch_rows)

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "REVIEW_BATCH_BUILT_NOT_AUTHORIZED",
        "healthy": healthy,
        "database_writes_attempted": False,
        "checks": checks,
        "policy": {
            "human_review_required": True,
            "automatic_equivalence_authorized": False,
            "candidate_updates_authorized": False,
            "runtime_staging_authorized": False,
            "runtime_activation_authorized": False,
            "project_matching_authorized": False,
            "canonical_changes_authorized": False,
        },
        "input": str(input_path),
        "input_sha256": input_sha256,
        "input_row_count": len(input_rows),
        "selected_evidence_band": SELECTED_BAND,
        "row_count": len(batch_rows),
        "counts_by_review_priority": dict(
            sorted(priority_counts.items())
        ),
        "counts_by_state": dict(
            sorted(state_counts.items())
        ),
        "state_review_priority_matrix": {
            state: dict(sorted(counts.items()))
            for state, counts
            in sorted(state_priority_counts.items())
        },
        "allowed_evidence_bases":
            ALLOWED_EVIDENCE_BASES,
        "allowed_review_decisions":
            ALLOWED_REVIEW_DECISIONS,
        "rows": str(rows_path),
        "rows_sha256": sha256_file(rows_path),
        "csv": str(csv_path),
        "csv_sha256": sha256_file(csv_path),
    }

    summary["summary_checksum"] = canonical_checksum(summary)
    atomic_write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
