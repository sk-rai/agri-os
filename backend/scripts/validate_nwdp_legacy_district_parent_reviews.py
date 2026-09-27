#!/usr/bin/env python3
"""Validate reviewed NWDP district-transition decisions without applying them."""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


SCHEMA_VERSION = "nwdp_legacy_district_parent_review_decisions.v1"
EXPECTED_ROWS = 17
TEMPLATE_SHA256 = (
    "26bee968cea0da71b44b10ad28dc0666c8c8e8b8e7f28386db82bbc6f6523dea"
)
DECISIONS = {
    "CONFIRM_CURRENT_DISTRICT_TRANSITION",
    "REJECT_CURRENT_DISTRICT_TRANSITION",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
EVIDENCE_BASES = {
    "CURRENT_LGD_HIERARCHY_CONFIRMATION",
    "AUTHORITATIVE_STATE_REORGANIZATION_SOURCE",
    "OFFICIAL_DISTRICT_CREATION_NOTIFICATION",
}
IDENTITY_FIELDS = (
    "state_code",
    "source_district_code",
    "current_district_code",
)
IMMUTABLE_FIELDS = (
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
)
REVIEW_FIELDS = (
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

    confirmed, rejected, deferred, invalid = [], [], [], []

    if not missing_columns:
        for review in reviewed:
            key = identity(review)
            template = template_map.get(key)
            errors = []

            if template is None:
                errors.append("UNEXPECTED_PAIR_IDENTITY")
                output = {"reviewed_row": review}
            else:
                output = dict(template)
                output.update({
                    field: text(review.get(field))
                    for field in REVIEW_FIELDS
                })
                for field in IMMUTABLE_FIELDS:
                    if text(review.get(field)) != text(template.get(field)):
                        errors.append(f"IMMUTABLE_FIELD_CHANGED:{field}")

            decision = text(review.get("review_decision"))
            basis = text(review.get("review_evidence_basis"))
            reference = text(review.get("review_evidence_reference"))
            reviewer = text(review.get("reviewer"))
            notes = text(review.get("review_notes"))

            if decision not in DECISIONS:
                errors.append(
                    f"INVALID_REVIEW_DECISION:{decision or 'BLANK'}"
                )
            if not reviewer:
                errors.append("REVIEWER_REQUIRED")
            if not notes:
                errors.append("REVIEW_NOTES_REQUIRED")

            if decision in {
                "CONFIRM_CURRENT_DISTRICT_TRANSITION",
                "REJECT_CURRENT_DISTRICT_TRANSITION",
            }:
                if basis not in EVIDENCE_BASES:
                    errors.append(
                        f"INVALID_EVIDENCE_BASIS:{basis or 'BLANK'}"
                    )
                if not reference:
                    errors.append("EVIDENCE_REFERENCE_REQUIRED")
            elif decision == "DEFER_FOR_AUTHORITATIVE_RESEARCH":
                if basis and basis not in EVIDENCE_BASES:
                    errors.append(f"INVALID_EVIDENCE_BASIS:{basis}")
                if bool(basis) != bool(reference):
                    errors.append("EVIDENCE_BASIS_REFERENCE_PAIR_REQUIRED")

            if errors:
                output["validation_errors"] = sorted(set(errors))
                invalid.append(output)
            elif decision == "CONFIRM_CURRENT_DISTRICT_TRANSITION":
                confirmed.append(output)
            elif decision == "REJECT_CURRENT_DISTRICT_TRANSITION":
                rejected.append(output)
            else:
                deferred.append(output)

    sort_key = lambda row: (
        row.get("review_priority", ""),
        row.get("state_code", ""),
        row.get("source_district_code", ""),
        row.get("current_district_code", ""),
    )
    for rows in (confirmed, rejected, deferred, invalid):
        rows.sort(key=sort_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "confirmed": output_dir / "nwdp_legacy_district_parent_confirmed_rows.jsonl",
        "rejected": output_dir / "nwdp_legacy_district_parent_rejected_rows.jsonl",
        "deferred": output_dir / "nwdp_legacy_district_parent_deferred_rows.jsonl",
        "invalid": output_dir / "nwdp_legacy_district_parent_invalid_rows.jsonl",
    }
    for name, rows in (
        ("confirmed", confirmed),
        ("rejected", rejected),
        ("deferred", deferred),
        ("invalid", invalid),
    ):
        write_jsonl(paths[name], rows)

    valid = confirmed + rejected + deferred
    missing_ids = sorted(set(template_ids) - set(reviewed_ids))
    unexpected_ids = sorted(set(reviewed_ids) - set(template_ids))

    checks = {
        "all_rows_valid": not invalid,
        "decision_partition_exact": len(valid) == EXPECTED_ROWS,
        "no_database_writes": True,
        "not_authorized_for_apply": True,
        "pair_identity_scope_exact":
            not missing_ids and not unexpected_ids,
        "required_columns_present": not missing_columns,
        "reviewed_pair_identity_unique":
            len(set(reviewed_ids)) == len(reviewed_ids),
        "reviewed_row_count_exact": len(reviewed) == EXPECTED_ROWS,
        "template_pair_identity_unique":
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
        "counts_by_evidence_basis": dict(sorted(Counter(
            row["review_evidence_basis"]
            for row in valid
            if row["review_evidence_basis"]
        ).items())),
        "database_writes_attempted": False,
        "expected_row_count": EXPECTED_ROWS,
        "healthy": healthy,
        "invalid_row_count": len(invalid),
        "missing_columns": missing_columns,
        "missing_pair_identities": [list(value) for value in missing_ids],
        "policy": {
            "automatic_reparenting_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "human_review_required": True,
            "runtime_activation_authorized": False,
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
        "unexpected_pair_identities":
            [list(value) for value in unexpected_ids],
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
        "nwdp_legacy_district_parent_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=campaign /
        "nwdp_legacy_district_parent_review_batch.csv",
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
            "nwdp_legacy_district_parent_decision_validation.json"
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
