#!/usr/bin/env python3
"""Collapse legacy NWDP block-parent evidence into pair-level reviews."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_legacy_block_parent_pair_review_batch.v1"
EXPECTED_INPUT_ROWS = 2_272
EXPECTED_PAIR_COUNT = 247
EXPECTED_SOURCE_PARENT_COUNT = 179
EXPECTED_MULTI_BLOCK_SOURCE_PARENTS = 54
INPUT_ROWS_SHA256 = (
    "5684a8377341e114c023ab658aaf5f5c3b01fd931a7295a8b13887bfe180eb82"
)

ALLOWED_DECISIONS = (
    "CONFIRM_PAIR_AS_CURRENT_RELATIONSHIP",
    "REJECT_PAIR_AS_CURRENT_RELATIONSHIP",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
)

ALLOWED_EVIDENCE_BASES = (
    "CURRENT_LGD_HIERARCHY_CONFIRMATION",
    "AUTHORITATIVE_STATE_SOURCE_CONFIRMATION",
    "DOCUMENTED_CROSS_LEVEL_ADMINISTRATIVE_RELATIONSHIP",
)

CSV_FIELDS = (
    "review_priority",
    "source_state",
    "source_state_code",
    "source_district_name",
    "source_district_code",
    "source_subdistrict_name",
    "source_subdistrict_code",
    "canonical_block_name",
    "canonical_block_code",
    "pair_row_count",
    "source_parent_block_count",
    "canonical_block_source_parent_count",
    "evidence_band",
    "identifier_comparison",
    "candidate_manifest_sha256",
    "source_feature_manifest_sha256",
    "first_source_feature_index",
    "last_source_feature_index",
    "review_decision",
    "review_evidence_basis",
    "review_evidence_reference",
    "reviewer",
    "review_notes",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_values(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def stable_checksum(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{line_number}"
                )
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def required(row: dict[str, Any], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"MISSING_{field.upper()}")
    return value


def pair_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        required(row, "source_state_code"),
        required(row, "source_district_code"),
        required(row, "source_subdistrict_code"),
        required(row, "canonical_block_code"),
    )


def source_parent_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        required(row, "source_state_code"),
        required(row, "source_district_code"),
        required(row, "source_subdistrict_code"),
    )


def canonical_block_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        required(row, "source_state_code"),
        required(row, "source_district_code"),
        required(row, "canonical_block_code"),
    )


def priority(
    pair_row_count: int,
    source_parent_block_count: int,
    canonical_block_source_parent_count: int,
) -> str:
    if (
        source_parent_block_count > 1
        or canonical_block_source_parent_count > 1
    ):
        return "P1_MANY_TO_MANY_PARENT_REVIEW"
    if pair_row_count >= 20:
        return "P2_HIGH_IMPACT_PAIR"
    if pair_row_count >= 5:
        return "P3_RECURRENT_PAIR"
    return "P4_LOW_FREQUENCY_PAIR"


def build(
    input_path: Path,
    output_rows: Path,
    output_csv: Path,
) -> tuple[dict[str, Any], bool]:
    input_sha256 = sha256_file(input_path)
    input_rows = load_jsonl(input_path)

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    source_parent_blocks: dict[
        tuple[str, ...], set[str]
    ] = defaultdict(set)
    block_source_parents: dict[
        tuple[str, ...], set[str]
    ] = defaultdict(set)

    for row in input_rows:
        grouped[pair_key(row)].append(row)
        source_parent_blocks[source_parent_key(row)].add(
            required(row, "canonical_block_code")
        )
        block_source_parents[canonical_block_key(row)].add(
            required(row, "source_subdistrict_code")
        )

    output = []
    for key, members in grouped.items():
        ordered_members = sorted(
            members,
            key=lambda row: (
                int(row["source_feature_index"]),
                row["candidate_id"],
            ),
        )
        first = ordered_members[0]

        candidate_ids = [
            required(row, "candidate_id")
            for row in ordered_members
        ]
        source_feature_ids = [
            required(row, "source_feature_id")
            for row in ordered_members
        ]
        village_codes = sorted({
            required(row, "source_village_code")
            for row in ordered_members
        })

        parent_block_count = len(
            source_parent_blocks[source_parent_key(first)]
        )
        block_parent_count = len(
            block_source_parents[canonical_block_key(first)]
        )
        pair_count = len(ordered_members)

        evidence_bands = sorted({
            required(row, "evidence_band")
            for row in ordered_members
        })

        output.append({
            "automatic_action_authorized": False,
            "candidate_ids": candidate_ids,
            "candidate_manifest_sha256":
                sha256_values(candidate_ids),
            "canonical_block_name":
                required(first, "canonical_block_name"),
            "canonical_block_code":
                required(first, "canonical_block_code"),
            "canonical_block_source_parent_count":
                block_parent_count,
            "canonical_district_name":
                required(first, "canonical_district_name"),
            "canonical_district_code":
                required(first, "canonical_district_code"),
            "evidence_band": ",".join(evidence_bands),
            "first_source_feature_index":
                ordered_members[0]["source_feature_index"],
            "identifier_comparison":
                "NOT_COMPARABLE_CROSS_LEVEL",
            "last_source_feature_index":
                ordered_members[-1]["source_feature_index"],
            "pair_row_count": pair_count,
            "review_decision": "",
            "review_evidence_basis": "",
            "review_evidence_reference": "",
            "review_notes": "",
            "review_priority": priority(
                pair_count,
                parent_block_count,
                block_parent_count,
            ),
            "reviewer": "",
            "source_district_name":
                required(first, "source_district_name"),
            "source_district_code":
                required(first, "source_district_code"),
            "source_feature_ids": source_feature_ids,
            "source_feature_manifest_sha256":
                sha256_values(source_feature_ids),
            "source_parent_block_count": parent_block_count,
            "source_state": required(first, "source_state"),
            "source_state_code":
                required(first, "source_state_code"),
            "source_subdistrict_name":
                required(first, "source_subdistrict_name"),
            "source_subdistrict_code":
                required(first, "source_subdistrict_code"),
            "source_village_code_count": len(village_codes),
        })

    output.sort(
        key=lambda row: (
            row["review_priority"],
            row["source_state"],
            row["source_district_code"],
            row["source_subdistrict_code"],
            row["canonical_block_code"],
        )
    )

    write_jsonl(output_rows, output)

    with output_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in output:
            writer.writerow({
                field: row[field]
                for field in CSV_FIELDS
            })

    rows_sha256 = sha256_file(output_rows)
    csv_sha256 = sha256_file(output_csv)

    all_candidate_ids = [
        candidate_id
        for row in output
        for candidate_id in row["candidate_ids"]
    ]
    all_source_feature_ids = [
        source_feature_id
        for row in output
        for source_feature_id in row["source_feature_ids"]
    ]
    input_candidate_ids = [
        required(row, "candidate_id")
        for row in input_rows
    ]
    input_source_feature_ids = [
        required(row, "source_feature_id")
        for row in input_rows
    ]

    multi_block_count = sum(
        len(blocks) > 1
        for blocks in source_parent_blocks.values()
    )

    priority_counts = dict(sorted(
        Counter(row["review_priority"] for row in output).items()
    ))
    state_priority_matrix: dict[str, dict[str, int]] = {}
    for row in output:
        state_priority_matrix.setdefault(row["source_state"], {})
        review_priority = row["review_priority"]
        state_priority_matrix[row["source_state"]][review_priority] = (
            state_priority_matrix[row["source_state"]].get(
                review_priority,
                0,
            )
            + 1
        )
    state_priority_matrix = {
        state: dict(sorted(counts.items()))
        for state, counts in sorted(state_priority_matrix.items())
    }

    checks = {
        "all_input_rows_partitioned":
            len(all_candidate_ids) == EXPECTED_INPUT_ROWS,
        "automatic_actions_disabled": all(
            row["automatic_action_authorized"] is False
            for row in output
        ),
        "candidate_identity_partition_exact":
            set(all_candidate_ids) == set(input_candidate_ids),
        "candidate_identity_unique":
            len(set(all_candidate_ids)) == len(all_candidate_ids),
        "cross_level_identifiers_not_compared": all(
            row["identifier_comparison"]
            == "NOT_COMPARABLE_CROSS_LEVEL"
            for row in output
        ),
        "input_row_count_exact":
            len(input_rows) == EXPECTED_INPUT_ROWS,
        "input_sha256_pinned":
            input_sha256 == INPUT_ROWS_SHA256,
        "multi_block_source_parent_count_exact":
            multi_block_count
            == EXPECTED_MULTI_BLOCK_SOURCE_PARENTS,
        "no_database_writes": True,
        "not_authorized": True,
        "pair_count_exact":
            len(output) == EXPECTED_PAIR_COUNT,
        "review_fields_blank": all(
            row["review_decision"] == ""
            and row["review_evidence_basis"] == ""
            and row["review_evidence_reference"] == ""
            and row["reviewer"] == ""
            for row in output
        ),
        "source_feature_identity_partition_exact":
            set(all_source_feature_ids)
            == set(input_source_feature_ids),
        "source_feature_identity_unique":
            len(set(all_source_feature_ids))
            == len(all_source_feature_ids),
        "source_parent_count_exact":
            len(source_parent_blocks)
            == EXPECTED_SOURCE_PARENT_COUNT,
    }
    healthy = all(checks.values())

    summary = {
        "allowed_evidence_bases":
            list(ALLOWED_EVIDENCE_BASES),
        "allowed_review_decisions":
            list(ALLOWED_DECISIONS),
        "checks": checks,
        "counts_by_review_priority": priority_counts,
        "csv": str(output_csv),
        "csv_sha256": csv_sha256,
        "database_writes_attempted": False,
        "healthy": healthy,
        "input": str(input_path),
        "input_row_count": len(input_rows),
        "input_sha256": input_sha256,
        "multi_block_source_parent_count":
            multi_block_count,
        "pair_count": len(output),
        "policy": {
            "automatic_reparenting_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "human_review_required": True,
            "project_matching_authorized": False,
            "runtime_activation_authorized": False,
            "runtime_staging_authorized": False,
        },
        "row_count": len(output),
        "rows": str(output_rows),
        "rows_sha256": rows_sha256,
        "schema_version": SCHEMA_VERSION,
        "source_parent_count": len(source_parent_blocks),
        "state_review_priority_matrix":
            state_priority_matrix,
        "status": (
            "PAIR_REVIEW_BATCH_BUILT_NOT_AUTHORIZED"
            if healthy
            else "PAIR_REVIEW_BATCH_BUILD_FAILED"
        ),
    }
    summary["summary_checksum"] = stable_checksum(summary)
    return summary, healthy


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[2]
    campaign = repository / (
        "data/staged/core_stack/promotion_review/"
        "20260925-lgd-priority-state-reconciliation-v1"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_review_evidence_rows.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_pair_review_batch.json",
    )
    parser.add_argument(
        "--output-rows",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_pair_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_pair_review_batch.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.output_summary.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        summary, healthy = build(
            args.input.resolve(),
            args.output_rows.resolve(),
            args.output_csv.resolve(),
        )
        args.output_summary.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
        return 0 if healthy else 1
    except Exception as exc:
        error = {
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
            "fail_closed": True,
            "healthy": False,
            "schema_version": SCHEMA_VERSION,
        }
        print(
            json.dumps(error, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
