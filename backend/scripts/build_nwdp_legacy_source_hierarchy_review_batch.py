#!/usr/bin/env python3
"""Build deterministic reviews for missing source subdistricts."""

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = "nwdp_legacy_source_hierarchy_review_batch.v2"
INPUT_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
EXPECTED_INPUT_ROWS = 10_052
EXPECTED_SELECTED_ROWS = 32
EXPECTED_REVIEW_ROWS = 2

CSV_FIELDS = (
    "review_priority",
    "source_state",
    "state_code",
    "source_district_name",
    "source_district_code",
    "source_subdistrict_name",
    "source_subdistrict_code",
    "replacement_subdistrict_code",
    "replacement_subdistrict_name",
    "village_row_count",
    "canonical_block_count",
    "canonical_block_codes",
    "canonical_block_names",
    "candidate_manifest_sha256",
    "source_feature_manifest_sha256",
    "review_decision",
    "review_evidence_basis",
    "review_evidence_reference",
    "reviewer",
    "review_notes",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_values(values):
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def required(row, field):
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"MISSING_{field.upper()}")
    return value


def load_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n")


def checksum(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def build(input_path, rows_path, csv_path):
    input_hash = sha256_file(input_path)
    input_rows = load_jsonl(input_path)
    selected = [
        row for row in input_rows
        if row.get("review_queue") == "SOURCE_HIERARCHY_REVIEW"
    ]

    grouped = defaultdict(list)
    for row in selected:
        key = (
            required(row, "expected_state_code"),
            required(row, "normalized_source_district_code"),
            required(row, "normalized_source_subdistrict_code"),
        )
        grouped[key].append(row)

    output = []
    for members in grouped.values():
        members.sort(key=lambda row: (
            int(row["source_feature_index"]),
            row["candidate_id"],
        ))
        first = members[0]
        candidates = [required(row, "candidate_id") for row in members]
        sources = [required(row, "source_feature_id") for row in members]
        blocks = {
            (
                required(row["canonical_matches"][0], "block_code"),
                required(row["canonical_matches"][0], "block_name"),
            )
            for row in members
        }

        output.append({
            "automatic_action_authorized": False,
            "candidate_ids": candidates,
            "candidate_manifest_sha256": sha256_values(candidates),
            "canonical_block_codes":
                "|".join(code for code, _ in sorted(blocks)),
            "canonical_block_count": len(blocks),
            "canonical_block_names":
                "|".join(name for _, name in sorted(blocks)),
            "replacement_subdistrict_code": "",
            "replacement_subdistrict_name": "",
            "review_decision": "",
            "review_evidence_basis": "",
            "review_evidence_reference": "",
            "review_notes": "",
            "review_priority": (
                "S1_HIGH_IMPACT_MISSING_SUBDISTRICT"
                if len(members) >= 10
                else "S2_SINGLETON_MISSING_SUBDISTRICT"
            ),
            "reviewer": "",
            "source_district_code":
                required(first, "normalized_source_district_code"),
            "source_district_name":
                required(first, "source_district_name"),
            "source_feature_ids": sources,
            "source_feature_manifest_sha256": sha256_values(sources),
            "source_state": required(first, "source_state"),
            "source_subdistrict_code":
                required(first, "normalized_source_subdistrict_code"),
            "source_subdistrict_name":
                required(first, "source_subdistrict_name"),
            "state_code": required(first, "expected_state_code"),
            "village_row_count": len(members),
        })

    output.sort(key=lambda row: (
        row["review_priority"],
        row["state_code"],
        row["source_district_code"],
        row["source_subdistrict_code"],
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

    candidates = [
        value for row in output for value in row["candidate_ids"]
    ]
    sources = [
        value for row in output for value in row["source_feature_ids"]
    ]

    checks = {
        "automatic_actions_disabled": all(
            not row["automatic_action_authorized"] for row in output
        ),
        "candidate_identity_unique":
            len(set(candidates)) == len(candidates),
        "candidate_partition_exact":
            set(candidates)
            == {required(row, "candidate_id") for row in selected},
        "input_disposition_exact": all(
            row.get("current_disposition")
            == "SOURCE_SUBDISTRICT_MISSING"
            for row in selected
        ),
        "input_row_count_exact":
            len(input_rows) == EXPECTED_INPUT_ROWS,
        "input_sha256_pinned": input_hash == INPUT_SHA256,
        "no_database_writes": True,
        "not_authorized": True,
        "review_fields_blank": all(
            not row["review_decision"]
            and not row["reviewer"]
            and not row["review_evidence_basis"]
            and not row["review_evidence_reference"]
            and not row["replacement_subdistrict_code"]
            and not row["replacement_subdistrict_name"]
            for row in output
        ),
        "review_row_count_exact":
            len(output) == EXPECTED_REVIEW_ROWS,
        "selected_row_count_exact":
            len(selected) == EXPECTED_SELECTED_ROWS,
        "source_feature_identity_unique":
            len(set(sources)) == len(sources),
        "source_feature_partition_exact":
            set(sources)
            == {required(row, "source_feature_id") for row in selected},
    }
    healthy = all(checks.values())

    summary = {
        "allowed_evidence_bases": [
            "CURRENT_LGD_SUBDISTRICT_CONFIRMATION",
            "AUTHORITATIVE_STATE_HIERARCHY_SOURCE",
            "OFFICIAL_SUBDISTRICT_CHANGE_NOTIFICATION",
        ],
        "allowed_review_decisions": [
            "CONFIRM_CURRENT_SOURCE_SUBDISTRICT",
            "IDENTIFY_REPLACEMENT_SOURCE_SUBDISTRICT",
            "DEFER_FOR_AUTHORITATIVE_RESEARCH",
        ],
        "checks": checks,
        "csv": str(csv_path),
        "csv_sha256": sha256_file(csv_path),
        "database_writes_attempted": False,
        "healthy": healthy,
        "input": str(input_path),
        "input_row_count": len(input_rows),
        "input_sha256": input_hash,
        "policy": {
            "automatic_hierarchy_repair_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "human_review_required": True,
            "runtime_staging_authorized": False,
        },
        "review_row_count": len(output),
        "rows": str(rows_path),
        "rows_sha256": sha256_file(rows_path),
        "schema_version": SCHEMA_VERSION,
        "selected_village_row_count": len(selected),
        "status": (
            "SOURCE_HIERARCHY_REVIEW_BUILT_NOT_AUTHORIZED"
            if healthy else "SOURCE_HIERARCHY_REVIEW_BUILD_FAILED"
        ),
    }
    summary["summary_checksum"] = checksum(summary)
    return summary, healthy


def main():
    repository = Path(__file__).resolve().parents[2]
    campaign = repository / (
        "data/staged/core_stack/promotion_review/"
        "20260925-lgd-priority-state-reconciliation-v1"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=campaign / "nwdp_legacy_held_review_queue_rows.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=campaign / "nwdp_legacy_source_hierarchy_review_batch.json",
    )
    parser.add_argument(
        "--output-rows",
        type=Path,
        default=campaign /
        "nwdp_legacy_source_hierarchy_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=campaign / "nwdp_legacy_source_hierarchy_review_batch.csv",
    )
    args = parser.parse_args()

    try:
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
        summary, healthy = build(
            args.input.resolve(),
            args.output_rows.resolve(),
            args.output_csv.resolve(),
        )
        args.output_summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
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
