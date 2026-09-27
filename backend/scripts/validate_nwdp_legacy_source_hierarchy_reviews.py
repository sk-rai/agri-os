#!/usr/bin/env python3
"""Validate source-hierarchy reviews without applying changes."""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


SCHEMA_VERSION = "nwdp_legacy_source_hierarchy_review_decisions.v1"
EXPECTED_ROWS = 2
TEMPLATE_SHA256 = (
    "d4eec1b6edcf7009b00073448c10a7fa239d10ab0819f225ca40e5b55c9894a3"
)
DECISIONS = {
    "CONFIRM_CURRENT_SOURCE_SUBDISTRICT",
    "IDENTIFY_REPLACEMENT_SOURCE_SUBDISTRICT",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
EVIDENCE_BASES = {
    "CURRENT_LGD_SUBDISTRICT_CONFIRMATION",
    "AUTHORITATIVE_STATE_HIERARCHY_SOURCE",
    "OFFICIAL_SUBDISTRICT_CHANGE_NOTIFICATION",
}
IDENTITY_FIELDS = (
    "state_code",
    "source_district_code",
    "source_subdistrict_code",
)
IMMUTABLE_FIELDS = (
    "review_priority",
    "source_state",
    "state_code",
    "source_district_name",
    "source_district_code",
    "source_subdistrict_name",
    "source_subdistrict_code",
    "village_row_count",
    "canonical_block_count",
    "canonical_block_codes",
    "canonical_block_names",
    "candidate_manifest_sha256",
    "source_feature_manifest_sha256",
)
REVIEW_FIELDS = (
    "replacement_subdistrict_code",
    "replacement_subdistrict_name",
    "review_decision",
    "review_evidence_basis",
    "review_evidence_reference",
    "reviewer",
    "review_notes",
)
REQUIRED_COLUMNS = IMMUTABLE_FIELDS + REVIEW_FIELDS


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def text(value):
    return str(value or "").strip()


def identity(row):
    return tuple(text(row.get(field)) for field in IDENTITY_FIELDS)


def checksum(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def validate(template_path, reviewed_path, output_dir):
    template_hash = sha256_file(template_path)
    templates = load_jsonl(template_path)
    template_map = {identity(row): row for row in templates}

    with reviewed_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        reviewed = list(reader)

    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(columns))
    reviewed_ids = [identity(row) for row in reviewed]
    template_ids = [identity(row) for row in templates]
    confirmed, replacements, deferred, invalid = [], [], [], []

    if not missing_columns:
        for review in reviewed:
            template = template_map.get(identity(review))
            errors = []
            output = dict(template or {})
            output.update({
                field: text(review.get(field))
                for field in REVIEW_FIELDS
            })

            if template is None:
                errors.append("UNEXPECTED_SOURCE_HIERARCHY_IDENTITY")
            else:
                for field in IMMUTABLE_FIELDS:
                    if text(review.get(field)) != text(template.get(field)):
                        errors.append(f"IMMUTABLE_FIELD_CHANGED:{field}")

            decision = text(review.get("review_decision"))
            basis = text(review.get("review_evidence_basis"))
            reference = text(review.get("review_evidence_reference"))
            replacement_code = text(
                review.get("replacement_subdistrict_code")
            )
            replacement_name = text(
                review.get("replacement_subdistrict_name")
            )

            if decision not in DECISIONS:
                errors.append(
                    f"INVALID_REVIEW_DECISION:{decision or 'BLANK'}"
                )
            if not text(review.get("reviewer")):
                errors.append("REVIEWER_REQUIRED")
            if not text(review.get("review_notes")):
                errors.append("REVIEW_NOTES_REQUIRED")

            if decision == "IDENTIFY_REPLACEMENT_SOURCE_SUBDISTRICT":
                if not replacement_code:
                    errors.append("REPLACEMENT_SUBDISTRICT_CODE_REQUIRED")
                if not replacement_name:
                    errors.append("REPLACEMENT_SUBDISTRICT_NAME_REQUIRED")
            elif replacement_code or replacement_name:
                errors.append(
                    "REPLACEMENT_FIELDS_FORBIDDEN_FOR_DECISION"
                )

            if decision != "DEFER_FOR_AUTHORITATIVE_RESEARCH":
                if basis not in EVIDENCE_BASES:
                    errors.append(
                        f"INVALID_EVIDENCE_BASIS:{basis or 'BLANK'}"
                    )
                if not reference:
                    errors.append("EVIDENCE_REFERENCE_REQUIRED")
            else:
                if basis and basis not in EVIDENCE_BASES:
                    errors.append(f"INVALID_EVIDENCE_BASIS:{basis}")
                if bool(basis) != bool(reference):
                    errors.append(
                        "EVIDENCE_BASIS_REFERENCE_PAIR_REQUIRED"
                    )

            if errors:
                output["validation_errors"] = sorted(set(errors))
                invalid.append(output)
            elif decision == "CONFIRM_CURRENT_SOURCE_SUBDISTRICT":
                confirmed.append(output)
            elif decision == "IDENTIFY_REPLACEMENT_SOURCE_SUBDISTRICT":
                replacements.append(output)
            else:
                deferred.append(output)

    sort_key = lambda row: (
        row.get("review_priority", ""),
        row.get("state_code", ""),
        row.get("source_district_code", ""),
        row.get("source_subdistrict_code", ""),
    )
    for rows in (confirmed, replacements, deferred, invalid):
        rows.sort(key=sort_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "confirmed": output_dir /
        "nwdp_legacy_source_hierarchy_confirmed_rows.jsonl",
        "replacement": output_dir /
        "nwdp_legacy_source_hierarchy_replacement_rows.jsonl",
        "deferred": output_dir /
        "nwdp_legacy_source_hierarchy_deferred_rows.jsonl",
        "invalid": output_dir /
        "nwdp_legacy_source_hierarchy_invalid_rows.jsonl",
    }
    result_sets = {
        "confirmed": confirmed,
        "replacement": replacements,
        "deferred": deferred,
        "invalid": invalid,
    }
    for name, rows in result_sets.items():
        write_jsonl(paths[name], rows)

    valid = confirmed + replacements + deferred
    checks = {
        "all_rows_valid": not invalid,
        "decision_partition_exact": len(valid) == EXPECTED_ROWS,
        "no_database_writes": True,
        "not_authorized_for_apply": True,
        "required_columns_present": not missing_columns,
        "reviewed_identity_unique":
            len(set(reviewed_ids)) == len(reviewed_ids),
        "reviewed_row_count_exact": len(reviewed) == EXPECTED_ROWS,
        "scope_exact": set(reviewed_ids) == set(template_ids),
        "template_identity_unique":
            len(set(template_ids)) == len(template_ids),
        "template_row_count_exact": len(templates) == EXPECTED_ROWS,
        "template_sha256_pinned": template_hash == TEMPLATE_SHA256,
    }
    healthy = all(checks.values())

    summary = {
        "allowed_evidence_bases": sorted(EVIDENCE_BASES),
        "allowed_review_decisions": sorted(DECISIONS),
        "checks": checks,
        "counts_by_decision": dict(sorted(Counter(
            row["review_decision"] for row in valid
        ).items())),
        "database_writes_attempted": False,
        "expected_row_count": EXPECTED_ROWS,
        "healthy": healthy,
        "invalid_row_count": len(invalid),
        "missing_columns": missing_columns,
        "policy": {
            "automatic_hierarchy_repair_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "human_review_required": True,
            "runtime_staging_authorized": False,
        },
        "reviewed_csv": str(reviewed_path),
        "reviewed_csv_sha256": sha256_file(reviewed_path),
        "row_count": len(reviewed),
        "schema_version": SCHEMA_VERSION,
        "status": (
            "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
            if healthy else "REVIEW_DECISIONS_INVALID"
        ),
        "template_rows": str(template_path),
        "template_rows_sha256": template_hash,
        "valid_row_count": len(valid),
    }
    for name, output_path in paths.items():
        summary[f"{name}_rows"] = str(output_path)
        summary[f"{name}_rows_sha256"] = sha256_file(output_path)

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
        "--template-rows",
        type=Path,
        default=campaign /
        "nwdp_legacy_source_hierarchy_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=campaign /
        "nwdp_legacy_source_hierarchy_review_batch.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=campaign)
    args = parser.parse_args()

    try:
        summary, healthy = validate(
            args.template_rows.resolve(),
            args.reviewed_csv.resolve(),
            args.output_dir.resolve(),
        )
        output = args.output_dir.resolve() / (
            "nwdp_legacy_source_hierarchy_decision_validation.json"
        )
        output.write_text(
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
