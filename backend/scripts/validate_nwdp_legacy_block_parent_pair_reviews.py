#!/usr/bin/env python3
"""Validate human decisions for NWDP block-parent pair reviews."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_legacy_block_parent_pair_review_decisions.v1"
EXPECTED_ROWS = 247
TEMPLATE_ROWS_SHA256 = (
    "47727937fe4d66f0d0602d249a8b0ba816d104e66abc437216b3c86a44dcb7e2"
)

ALLOWED_DECISIONS = {
    "CONFIRM_PAIR_AS_CURRENT_RELATIONSHIP",
    "REJECT_PAIR_AS_CURRENT_RELATIONSHIP",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
ALLOWED_EVIDENCE_BASES = {
    "CURRENT_LGD_HIERARCHY_CONFIRMATION",
    "AUTHORITATIVE_STATE_SOURCE_CONFIRMATION",
    "DOCUMENTED_CROSS_LEVEL_ADMINISTRATIVE_RELATIONSHIP",
}

IDENTITY_FIELDS = (
    "source_state_code",
    "source_district_code",
    "source_subdistrict_code",
    "canonical_block_code",
)

IMMUTABLE_FIELDS = (
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
)

REQUIRED_COLUMNS = IMMUTABLE_FIELDS + (
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


def normalized(value: Any) -> str:
    return str(value or "").strip()


def identity(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(normalized(row.get(field)) for field in IDENTITY_FIELDS)


def csv_projection(template: dict[str, Any]) -> dict[str, str]:
    return {
        field: normalized(template.get(field))
        for field in IMMUTABLE_FIELDS
    }


def validate_row(
    reviewed: dict[str, str],
    template: dict[str, Any],
) -> list[str]:
    errors = []

    expected = csv_projection(template)
    for field in IMMUTABLE_FIELDS:
        if normalized(reviewed.get(field)) != expected[field]:
            errors.append(f"IMMUTABLE_FIELD_CHANGED:{field}")

    decision = normalized(reviewed.get("review_decision"))
    basis = normalized(reviewed.get("review_evidence_basis"))
    reference = normalized(reviewed.get("review_evidence_reference"))
    reviewer = normalized(reviewed.get("reviewer"))
    notes = normalized(reviewed.get("review_notes"))

    if decision not in ALLOWED_DECISIONS:
        errors.append(f"INVALID_REVIEW_DECISION:{decision or 'BLANK'}")

    if not reviewer:
        errors.append("REVIEWER_REQUIRED")
    if not notes:
        errors.append("REVIEW_NOTES_REQUIRED")

    if decision in {
        "CONFIRM_PAIR_AS_CURRENT_RELATIONSHIP",
        "REJECT_PAIR_AS_CURRENT_RELATIONSHIP",
    }:
        if basis not in ALLOWED_EVIDENCE_BASES:
            errors.append(
                f"INVALID_EVIDENCE_BASIS:{basis or 'BLANK'}"
            )
        if not reference:
            errors.append("EVIDENCE_REFERENCE_REQUIRED")

    if decision == "DEFER_FOR_AUTHORITATIVE_RESEARCH":
        if basis and basis not in ALLOWED_EVIDENCE_BASES:
            errors.append(f"INVALID_EVIDENCE_BASIS:{basis}")
        if basis and not reference:
            errors.append("EVIDENCE_REFERENCE_REQUIRED_WITH_BASIS")
        if reference and not basis:
            errors.append("EVIDENCE_BASIS_REQUIRED_WITH_REFERENCE")

    return sorted(set(errors))


def validate(
    template_path: Path,
    reviewed_csv: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], bool]:
    template_sha256 = sha256_file(template_path)
    templates = load_jsonl(template_path)

    with reviewed_csv.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        reviewed_rows = list(reader)

    missing_columns = sorted(
        set(REQUIRED_COLUMNS) - set(fieldnames)
    )

    template_by_identity = {
        identity(row): row
        for row in templates
    }
    reviewed_identities = [
        identity(row)
        for row in reviewed_rows
    ]
    template_identities = [
        identity(row)
        for row in templates
    ]

    reviewed_counts = Counter(reviewed_identities)
    template_counts = Counter(template_identities)

    duplicate_reviewed = sorted(
        list(key)
        for key, count in reviewed_counts.items()
        if count != 1
    )
    duplicate_templates = sorted(
        list(key)
        for key, count in template_counts.items()
        if count != 1
    )

    missing_identities = sorted(
        [list(key) for key in set(template_identities)
         - set(reviewed_identities)]
    )
    unexpected_identities = sorted(
        [list(key) for key in set(reviewed_identities)
         - set(template_identities)]
    )

    approved = []
    rejected = []
    deferred = []
    invalid = []

    if not missing_columns:
        for reviewed in reviewed_rows:
            key = identity(reviewed)
            template = template_by_identity.get(key)

            if template is None:
                invalid.append({
                    "reviewed_row": reviewed,
                    "validation_errors":
                        ["UNEXPECTED_PAIR_IDENTITY"],
                })
                continue

            errors = validate_row(reviewed, template)
            output = dict(template)
            output.update({
                "review_decision":
                    normalized(reviewed["review_decision"]),
                "review_evidence_basis":
                    normalized(reviewed["review_evidence_basis"]),
                "review_evidence_reference":
                    normalized(
                        reviewed["review_evidence_reference"]
                    ),
                "review_notes":
                    normalized(reviewed["review_notes"]),
                "reviewer":
                    normalized(reviewed["reviewer"]),
            })

            if errors:
                output["validation_errors"] = errors
                invalid.append(output)
            elif output["review_decision"] == (
                "CONFIRM_PAIR_AS_CURRENT_RELATIONSHIP"
            ):
                approved.append(output)
            elif output["review_decision"] == (
                "REJECT_PAIR_AS_CURRENT_RELATIONSHIP"
            ):
                rejected.append(output)
            else:
                deferred.append(output)

    sort_key = lambda row: (
        row.get("review_priority", ""),
        row.get("source_state", ""),
        row.get("source_district_code", ""),
        row.get("source_subdistrict_code", ""),
        row.get("canonical_block_code", ""),
    )
    approved.sort(key=sort_key)
    rejected.sort(key=sort_key)
    deferred.sort(key=sort_key)
    invalid.sort(key=sort_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "confirmed": output_dir
        / "nwdp_legacy_block_parent_pair_confirmed_rows.jsonl",
        "rejected": output_dir
        / "nwdp_legacy_block_parent_pair_rejected_rows.jsonl",
        "deferred": output_dir
        / "nwdp_legacy_block_parent_pair_deferred_rows.jsonl",
        "invalid": output_dir
        / "nwdp_legacy_block_parent_pair_invalid_rows.jsonl",
    }

    write_jsonl(paths["confirmed"], approved)
    write_jsonl(paths["rejected"], rejected)
    write_jsonl(paths["deferred"], deferred)
    write_jsonl(paths["invalid"], invalid)

    valid_count = len(approved) + len(rejected) + len(deferred)
    decision_counts = dict(sorted(Counter(
        row["review_decision"]
        for row in approved + rejected + deferred
    ).items()))
    evidence_counts = dict(sorted(Counter(
        row["review_evidence_basis"]
        for row in approved + rejected + deferred
        if row["review_evidence_basis"]
    ).items()))

    checks = {
        "all_rows_valid": len(invalid) == 0,
        "decision_partition_exact":
            valid_count == EXPECTED_ROWS,
        "immutable_fields_unchanged":
            len(invalid) == 0,
        "no_database_writes": True,
        "not_authorized_for_apply": True,
        "pair_identity_scope_exact":
            not missing_identities
            and not unexpected_identities,
        "required_columns_present":
            not missing_columns,
        "reviewed_pair_identity_unique":
            not duplicate_reviewed,
        "reviewed_row_count_exact":
            len(reviewed_rows) == EXPECTED_ROWS,
        "template_pair_identity_unique":
            not duplicate_templates,
        "template_row_count_exact":
            len(templates) == EXPECTED_ROWS,
        "template_sha256_pinned":
            template_sha256 == TEMPLATE_ROWS_SHA256,
    }
    healthy = all(checks.values())

    summary = {
        "allowed_evidence_bases":
            sorted(ALLOWED_EVIDENCE_BASES),
        "allowed_review_decisions":
            sorted(ALLOWED_DECISIONS),
        "checks": checks,
        "counts_by_decision": decision_counts,
        "counts_by_evidence_basis": evidence_counts,
        "database_writes_attempted": False,
        "deferred_rows": str(paths["deferred"]),
        "deferred_rows_sha256":
            sha256_file(paths["deferred"]),
        "expected_row_count": EXPECTED_ROWS,
        "healthy": healthy,
        "invalid_row_count": len(invalid),
        "invalid_rows": str(paths["invalid"]),
        "invalid_rows_sha256":
            sha256_file(paths["invalid"]),
        "missing_columns": missing_columns,
        "missing_pair_identities": missing_identities,
        "policy": {
            "automatic_reparenting_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "human_review_required": True,
            "project_matching_authorized": False,
            "runtime_activation_authorized": False,
            "runtime_staging_authorized": False,
        },
        "confirmed_rows": str(paths["confirmed"]),
        "confirmed_rows_sha256":
            sha256_file(paths["confirmed"]),
        "rejected_rows": str(paths["rejected"]),
        "rejected_rows_sha256":
            sha256_file(paths["rejected"]),
        "reviewed_csv": str(reviewed_csv),
        "reviewed_csv_sha256":
            sha256_file(reviewed_csv),
        "row_count": len(reviewed_rows),
        "schema_version": SCHEMA_VERSION,
        "status": (
            "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
            if healthy
            else "REVIEW_DECISIONS_INVALID"
        ),
        "template_rows": str(template_path),
        "template_rows_sha256": template_sha256,
        "unexpected_pair_identities":
            unexpected_identities,
        "valid_row_count": valid_count,
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
        "--template-rows",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_pair_review_batch_rows.jsonl",
    )
    parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_pair_review_batch.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=campaign,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary, healthy = validate(
            args.template_rows.resolve(),
            args.reviewed_csv.resolve(),
            args.output_dir.resolve(),
        )
        summary_path = (
            args.output_dir.resolve()
            / "nwdp_legacy_block_parent_pair_decision_validation.json"
        )
        summary_path.write_text(
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
