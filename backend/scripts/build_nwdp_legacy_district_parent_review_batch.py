#!/usr/bin/env python3
"""Build district-transition reviews for legacy NWDP held rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_legacy_district_parent_review_batch.v1"
INPUT_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
EXPECTED_INPUT_ROWS = 10_052
EXPECTED_SELECTED_ROWS = 192
EXPECTED_PAIR_COUNT = 17

CSV_FIELDS = (
    "review_priority",
    "source_state",
    "state_code",
    "source_district_name",
    "source_district_code",
    "current_district_name",
    "current_district_code",
    "pair_row_count",
    "target_source_district_count",
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
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL_OBJECT_REQUIRED:{path}:{number}")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n")


def required(row: dict[str, Any], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"MISSING_{field.upper()}")
    return value


def checksum(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def pair_key(row: dict[str, Any]) -> tuple[str, ...]:
    current = row["canonical_matches"][0]
    return (
        required(row, "expected_state_code"),
        required(row, "normalized_source_district_code"),
        required(current, "district_code"),
    )


def priority(row_count: int, source_count: int) -> str:
    if source_count > 1:
        return "D1_MULTI_SOURCE_TARGET_DISTRICT"
    if row_count >= 20:
        return "D2_HIGH_IMPACT_TRANSITION"
    if row_count >= 5:
        return "D3_RECURRENT_TRANSITION"
    return "D4_LOW_FREQUENCY_TRANSITION"


def build(
    input_path: Path,
    rows_path: Path,
    csv_path: Path,
) -> tuple[dict[str, Any], bool]:
    input_hash = sha256_file(input_path)
    input_rows = load_jsonl(input_path)
    selected = [
        row for row in input_rows
        if row.get("review_queue") == "DISTRICT_PARENT_REVIEW"
    ]

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    target_sources: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in selected:
        matches = row.get("canonical_matches")
        if not isinstance(matches, list) or len(matches) != 1:
            raise ValueError(
                "EXPECTED_ONE_CANONICAL_MATCH:"
                + required(row, "candidate_id")
            )
        current = matches[0]
        grouped[pair_key(row)].append(row)
        target_sources[
            (
                required(row, "expected_state_code"),
                required(current, "district_code"),
            )
        ].add(required(row, "normalized_source_district_code"))

    output = []
    for members in grouped.values():
        members.sort(key=lambda row: (
            int(row["source_feature_index"]),
            row["candidate_id"],
        ))
        first = members[0]
        current = first["canonical_matches"][0]
        candidate_ids = [
            required(row, "candidate_id") for row in members
        ]
        source_ids = [
            required(row, "source_feature_id") for row in members
        ]
        target_key = (
            required(first, "expected_state_code"),
            required(current, "district_code"),
        )
        source_count = len(target_sources[target_key])

        output.append({
            "automatic_action_authorized": False,
            "candidate_ids": candidate_ids,
            "candidate_manifest_sha256":
                sha256_values(candidate_ids),
            "current_district_active":
                current.get("district_active") is True,
            "current_district_code":
                required(current, "district_code"),
            "current_district_name":
                required(current, "district_name"),
            "first_source_feature_index":
                members[0]["source_feature_index"],
            "last_source_feature_index":
                members[-1]["source_feature_index"],
            "pair_row_count": len(members),
            "review_decision": "",
            "review_evidence_basis": "",
            "review_evidence_reference": "",
            "review_notes": "",
            "review_priority":
                priority(len(members), source_count),
            "reviewer": "",
            "source_district_code":
                required(first, "normalized_source_district_code"),
            "source_district_name":
                required(first, "source_district_name"),
            "source_feature_ids": source_ids,
            "source_feature_manifest_sha256":
                sha256_values(source_ids),
            "source_state": required(first, "source_state"),
            "state_code": required(first, "expected_state_code"),
            "target_source_district_count": source_count,
        })

    output.sort(key=lambda row: (
        row["review_priority"],
        row["state_code"],
        row["source_district_code"],
        row["current_district_code"],
    ))
    write_jsonl(rows_path, output)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in output:
            writer.writerow({field: row[field] for field in CSV_FIELDS})

    all_candidates = [
        value for row in output for value in row["candidate_ids"]
    ]
    all_sources = [
        value for row in output for value in row["source_feature_ids"]
    ]
    input_candidates = [
        required(row, "candidate_id") for row in selected
    ]
    input_sources = [
        required(row, "source_feature_id") for row in selected
    ]

    checks = {
        "automatic_actions_disabled": all(
            not row["automatic_action_authorized"] for row in output
        ),
        "candidate_partition_exact":
            set(all_candidates) == set(input_candidates),
        "candidate_identity_unique":
            len(set(all_candidates)) == len(all_candidates),
        "current_district_active": all(
            row["current_district_active"] for row in output
        ),
        "district_codes_differ": all(
            row["source_district_code"]
            != row["current_district_code"]
            for row in output
        ),
        "input_disposition_exact": all(
            row.get("current_disposition")
            == "CURRENT_VILLAGE_SAME_STATE_OTHER_DISTRICT"
            for row in selected
        ),
        "input_row_count_exact":
            len(input_rows) == EXPECTED_INPUT_ROWS,
        "input_sha256_pinned": input_hash == INPUT_SHA256,
        "no_database_writes": True,
        "not_authorized": True,
        "pair_count_exact": len(output) == EXPECTED_PAIR_COUNT,
        "review_fields_blank": all(
            not row["review_decision"]
            and not row["reviewer"]
            and not row["review_evidence_basis"]
            and not row["review_evidence_reference"]
            for row in output
        ),
        "selected_row_count_exact":
            len(selected) == EXPECTED_SELECTED_ROWS,
        "source_feature_partition_exact":
            set(all_sources) == set(input_sources),
        "source_feature_identity_unique":
            len(set(all_sources)) == len(all_sources),
        "state_context_exact": all(
            str(row["expected_state_code"])
            == str(row["canonical_matches"][0]["state_code"])
            for row in selected
        ),
    }
    healthy = all(checks.values())

    priority_counts = dict(sorted(Counter(
        row["review_priority"] for row in output
    ).items()))
    state_counts = dict(sorted(Counter(
        row["source_state"] for row in output
    ).items()))

    summary = {
        "allowed_evidence_bases": [
            "CURRENT_LGD_HIERARCHY_CONFIRMATION",
            "AUTHORITATIVE_STATE_REORGANIZATION_SOURCE",
            "OFFICIAL_DISTRICT_CREATION_NOTIFICATION",
        ],
        "allowed_review_decisions": [
            "CONFIRM_CURRENT_DISTRICT_TRANSITION",
            "REJECT_CURRENT_DISTRICT_TRANSITION",
            "DEFER_FOR_AUTHORITATIVE_RESEARCH",
        ],
        "checks": checks,
        "counts_by_review_priority": priority_counts,
        "counts_by_state": state_counts,
        "csv": str(csv_path),
        "csv_sha256": sha256_file(csv_path),
        "database_writes_attempted": False,
        "healthy": healthy,
        "input": str(input_path),
        "input_row_count": len(input_rows),
        "input_sha256": input_hash,
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
        "rows": str(rows_path),
        "rows_sha256": sha256_file(rows_path),
        "schema_version": SCHEMA_VERSION,
        "selected_village_row_count": len(selected),
        "status": (
            "DISTRICT_TRANSITION_REVIEW_BUILT_NOT_AUTHORIZED"
            if healthy
            else "DISTRICT_TRANSITION_REVIEW_BUILD_FAILED"
        ),
    }
    summary["summary_checksum"] = checksum(summary)
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
        / "nwdp_legacy_held_review_queue_rows.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=campaign
        / "nwdp_legacy_district_parent_review_batch.json",
    )
    parser.add_argument(
        "--output-rows",
        type=Path,
        default=campaign
        / "nwdp_legacy_district_parent_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=campaign
        / "nwdp_legacy_district_parent_review_batch.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
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
            ) + "\n",
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
        print(json.dumps({
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
            "fail_closed": True,
            "healthy": False,
            "schema_version": SCHEMA_VERSION,
        }, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
