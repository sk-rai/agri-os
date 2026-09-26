#!/usr/bin/env python3
"""Build a deterministic human-review batch for strong legacy name evidence."""

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


SCHEMA_VERSION = "nwdp_legacy_strong_name_review_batch.v1"
EXPECTED_INPUT_SHA256 = (
    "dd7d68ea2db24f1bb1de9243bdfb9f217a7917fad0f8dc2168d316d4e2af6d62"
)
EXPECTED_INPUT_ROWS = 7_540
EXPECTED_SELECTED_ROWS = 217
EXPECTED_BAND_COUNTS = {
    "ADMINISTRATIVE_QUALIFIER_ONLY": 201,
    "TOKEN_ORDER_ONLY": 16,
}
SELECTED_BANDS = frozenset(EXPECTED_BAND_COUNTS)

CSV_FIELDS = [
    "sequence",
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
    "source_name_core",
    "canonical_name_core",
    "evidence_band",
    "levenshtein_distance",
    "sequence_similarity",
    "token_jaccard",
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
                raise ValueError(f"NON_OBJECT_JSONL_ROW:{line_number}")

            rows.append(value)

    return rows


def sort_key(row: dict[str, Any]) -> tuple[str, ...]:
    band_order = {
        "ADMINISTRATIVE_QUALIFIER_ONLY": "01",
        "TOKEN_ORDER_ONLY": "02",
    }

    return (
        band_order.get(text(row.get("evidence_band")), "99"),
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
        if row.get("evidence_band") in SELECTED_BANDS
    ]
    selected.sort(key=sort_key)

    batch_rows: list[dict[str, Any]] = []

    for sequence, row in enumerate(selected, 1):
        batch_rows.append({
            **row,
            "sequence": sequence,
            "review_decision": "",
            "reviewer": "",
            "review_notes": "",
            "allowed_review_decisions": [
                "APPROVE_EQUIVALENCE",
                "REJECT_EQUIVALENCE",
                "DEFER_FOR_SOURCE_RESEARCH",
            ],
            "automatic_equivalence_authorized": False,
            "automatic_runtime_staging_authorized": False,
        })

    band_counts = Counter(
        text(row.get("evidence_band"))
        for row in batch_rows
    )
    state_counts = Counter(
        text(row.get("source_state"))
        for row in batch_rows
    )

    candidate_ids = [
        text(row.get("candidate_id"))
        for row in batch_rows
    ]
    source_feature_ids = [
        text(row.get("source_feature_id"))
        for row in batch_rows
    ]
    canonical_village_ids = [
        text(row.get("canonical_village_id"))
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
        "selected_band_counts_exact": (
            dict(sorted(band_counts.items()))
            == EXPECTED_BAND_COUNTS
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
        "canonical_village_identity_present": all(
            canonical_village_ids
        ),
        "review_decisions_blank": all(
            row["review_decision"] == ""
            for row in batch_rows
        ),
        "reviewers_blank": all(
            row["reviewer"] == ""
            for row in batch_rows
        ),
        "automatic_equivalence_disabled": all(
            row["automatic_equivalence_authorized"] is False
            for row in batch_rows
        ),
        "automatic_runtime_staging_disabled": all(
            row["automatic_runtime_staging_authorized"] is False
            for row in batch_rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
    }

    healthy = all(checks.values())

    rows_path = (
        output_dir
        / "nwdp_legacy_strong_name_review_batch_rows.jsonl"
    )
    csv_path = (
        output_dir
        / "nwdp_legacy_strong_name_review_batch.csv"
    )
    summary_path = (
        output_dir
        / "nwdp_legacy_strong_name_review_batch.json"
    )

    atomic_write_jsonl(rows_path, batch_rows)
    atomic_write_csv(csv_path, batch_rows)

    rows_sha256 = sha256_file(rows_path)
    csv_sha256 = sha256_file(csv_path)

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
        "selected_evidence_bands": sorted(SELECTED_BANDS),
        "row_count": len(batch_rows),
        "counts_by_evidence_band": dict(
            sorted(band_counts.items())
        ),
        "counts_by_state": dict(sorted(state_counts.items())),
        "allowed_review_decisions": [
            "APPROVE_EQUIVALENCE",
            "REJECT_EQUIVALENCE",
            "DEFER_FOR_SOURCE_RESEARCH",
        ],
        "rows": str(rows_path),
        "rows_sha256": rows_sha256,
        "csv": str(csv_path),
        "csv_sha256": csv_sha256,
    }

    summary["summary_checksum"] = canonical_checksum(summary)
    atomic_write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
