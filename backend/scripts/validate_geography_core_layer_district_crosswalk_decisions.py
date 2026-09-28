#!/usr/bin/env python3
"""Validate Core-layer district crosswalk review decisions.

This validator writes partitioned local evidence files only. It never writes
geography_climate_region_mappings and never authorizes runtime activation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TEMPLATE_ROWS = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "geography_core_layer_district_crosswalk_review_batch_rows.jsonl"
)
DEFAULT_REVIEWED_CSV = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "geography_core_layer_district_crosswalk_review_batch.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)

EXPECTED_TEMPLATE_SHA256 = (
    "d6b1d185216b67d144d58336e66df2ccb2880c8bac71fa0d1296318eacc86d4e"
)
EXPECTED_ROW_COUNT = 1779

ALLOWED_DECISIONS = {
    "APPROVE_INACTIVE_MANUAL_REVIEW_MAPPING",
    "REJECT_DISTRICT_CROSSWALK",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
ALLOWED_EVIDENCE_BASES = {
    "POLYGON_OVERLAP_MANUAL_REVIEW",
    "AUTHORITATIVE_AGRO_CLIMATE_SOURCE",
    "OTHER_DOCUMENTED_EVIDENCE",
}
LOW_OVERLAP_APPROVAL_EVIDENCE = {
    "AUTHORITATIVE_AGRO_CLIMATE_SOURCE",
    "OTHER_DOCUMENTED_EVIDENCE",
}
REVIEW_FIELDS = {
    "review_decision",
    "review_evidence_basis",
    "reviewer",
    "review_notes",
}
IDENTITY_FIELDS = (
    "district_lgd_code",
    "region_system",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template-rows",
        type=Path,
        default=DEFAULT_TEMPLATE_ROWS,
    )
    parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=DEFAULT_REVIEWED_CSV,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def identity(row: dict[str, Any]) -> tuple[str, str]:
    return tuple(str(row.get(field) or "") for field in IDENTITY_FIELDS)


def csv_value_matches(value: str, expected: Any) -> bool:
    if expected is None:
        return value == ""
    if isinstance(expected, bool):
        return value.strip().casefold() == str(expected).casefold()
    if isinstance(expected, int) and not isinstance(expected, bool):
        try:
            return int(value) == expected
        except ValueError:
            return False
    if isinstance(expected, float):
        try:
            return float(value) == expected
        except ValueError:
            return False
    if isinstance(expected, (list, dict)):
        try:
            return json.loads(value) == expected
        except (json.JSONDecodeError, TypeError):
            return False
    return value == str(expected)


def immutable_fields_match(
    reviewed: dict[str, str],
    template: dict[str, Any],
) -> bool:
    for field, expected in template.items():
        if field in REVIEW_FIELDS:
            continue
        if field not in reviewed:
            return False
        if not csv_value_matches(reviewed[field], expected):
            return False
    return True


def validate_row(
    reviewed: dict[str, str],
    template: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    decision = reviewed["review_decision"].strip()
    evidence = reviewed["review_evidence_basis"].strip()
    reviewer = reviewed["reviewer"].strip()
    notes = reviewed["review_notes"].strip()
    priority = template["crosswalk_review_priority"]

    if not decision:
        errors.append("review_decision_required")
        return errors

    if decision not in ALLOWED_DECISIONS:
        errors.append("review_decision_not_allowed")

    if not reviewer:
        errors.append("reviewer_required")

    if not notes:
        errors.append("review_notes_required")

    if evidence and evidence not in ALLOWED_EVIDENCE_BASES:
        errors.append("review_evidence_basis_not_allowed")

    if decision == "APPROVE_INACTIVE_MANUAL_REVIEW_MAPPING":
        if evidence not in ALLOWED_EVIDENCE_BASES:
            errors.append("approval_evidence_basis_required")

        if priority not in {
            "C1_READY_FOR_MANUAL_REVIEW",
            "C2_LOW_OVERLAP_MANUAL_REVIEW",
        }:
            errors.append("priority_not_approvable")

        if priority == "C2_LOW_OVERLAP_MANUAL_REVIEW":
            if evidence not in LOW_OVERLAP_APPROVAL_EVIDENCE:
                errors.append(
                    "low_overlap_requires_documented_or_authoritative_evidence"
                )

        if not template["candidate_present"]:
            errors.append("approval_candidate_missing")

        if template["candidate_excluded"]:
            errors.append("approval_candidate_excluded")

        if template["candidate_is_active"]:
            errors.append("approval_candidate_must_remain_inactive")

        if not template["target_region_id"]:
            errors.append("approval_target_region_id_required")

        if not template["target_region_code"]:
            errors.append("approval_target_region_code_required")

        if (
            priority == "C1_READY_FOR_MANUAL_REVIEW"
            and not template[
                "would_write_inactive_manual_review_row"
            ]
        ):
            errors.append(
                "normal_approval_not_eligible_for_inactive_review_row"
            )

    if decision == "REJECT_DISTRICT_CROSSWALK":
        if evidence not in ALLOWED_EVIDENCE_BASES:
            errors.append("rejection_evidence_basis_required")

        if priority == "C5_CURRENT_DISTRICT_GEOMETRY_GAP":
            errors.append(
                "missing_geometry_row_must_be_deferred"
            )

    if decision == "DEFER_FOR_AUTHORITATIVE_RESEARCH":
        if priority == "C5_CURRENT_DISTRICT_GEOMETRY_GAP":
            if evidence:
                errors.append(
                    "missing_geometry_deferral_evidence_must_be_blank"
                )

    return errors


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )


def checksum(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    template_rows = read_jsonl(args.template_rows)
    reviewed_fields, reviewed_rows = read_csv(args.reviewed_csv)

    required_columns = set(template_rows[0]) if template_rows else set()
    missing_columns = sorted(required_columns - set(reviewed_fields))

    template_index = {
        identity(row): row
        for row in template_rows
    }
    reviewed_identities = [
        identity(row)
        for row in reviewed_rows
    ]

    duplicate_reviewed_identities = sorted(
        key
        for key, count in Counter(reviewed_identities).items()
        if count > 1
    )

    missing_identities = sorted(
        set(template_index) - set(reviewed_identities)
    )
    unexpected_identities = sorted(
        set(reviewed_identities) - set(template_index)
    )

    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    immutable_fields_unchanged = True

    for reviewed in reviewed_rows:
        row_identity = identity(reviewed)
        template = template_index.get(row_identity)

        if template is None:
            invalid.append({
                "identity": list(row_identity),
                "validation_errors": [
                    "unexpected_district_region_identity"
                ],
                "reviewed_row": reviewed,
            })
            continue

        immutable_match = immutable_fields_match(
            reviewed,
            template,
        )
        if not immutable_match:
            immutable_fields_unchanged = False

        errors = []
        if not immutable_match:
            errors.append("immutable_fields_changed")

        errors.extend(validate_row(reviewed, template))

        output_row = dict(template)
        output_row.update({
            field: reviewed.get(field, "").strip()
            for field in REVIEW_FIELDS
        })
        output_row["database_apply_authorized"] = False
        output_row["runtime_activation_authorized"] = False
        output_row["candidate_remains_inactive"] = True

        if errors:
            invalid.append({
                "identity": list(row_identity),
                "crosswalk_review_priority": template[
                    "crosswalk_review_priority"
                ],
                "validation_errors": sorted(set(errors)),
                "reviewed_row": output_row,
            })
            continue

        decision = output_row["review_decision"]
        if decision == "APPROVE_INACTIVE_MANUAL_REVIEW_MAPPING":
            approved.append(output_row)
        elif decision == "REJECT_DISTRICT_CROSSWALK":
            rejected.append(output_row)
        else:
            deferred.append(output_row)

    prefix = "geography_core_layer_district_crosswalk"
    approved_path = args.output_dir / f"{prefix}_approved_rows.jsonl"
    rejected_path = args.output_dir / f"{prefix}_rejected_rows.jsonl"
    deferred_path = args.output_dir / f"{prefix}_deferred_rows.jsonl"
    invalid_path = args.output_dir / f"{prefix}_invalid_rows.jsonl"
    summary_path = args.output_dir / f"{prefix}_decision_validation.json"

    write_jsonl(approved_path, approved)
    write_jsonl(rejected_path, rejected)
    write_jsonl(deferred_path, deferred)
    write_jsonl(invalid_path, invalid)

    counts_by_decision = Counter(
        row["review_decision"]
        for row in approved + rejected + deferred
    )
    counts_by_evidence = Counter(
        row["review_evidence_basis"]
        for row in approved + rejected + deferred
        if row["review_evidence_basis"]
    )

    template_hash = sha256(args.template_rows)

    checks = {
        "all_rows_valid": not invalid,
        "decision_partition_exact": (
            len(approved)
            + len(rejected)
            + len(deferred)
            == len(reviewed_rows)
        ),
        "immutable_fields_unchanged": immutable_fields_unchanged,
        "no_database_writes": True,
        "not_authorized_for_apply": True,
        "required_columns_present": not missing_columns,
        "reviewed_identity_unique": (
            not duplicate_reviewed_identities
        ),
        "reviewed_row_count_exact": (
            len(reviewed_rows) == EXPECTED_ROW_COUNT
        ),
        "scope_exact": (
            not missing_identities
            and not unexpected_identities
        ),
        "template_identity_unique": (
            len(template_index) == len(template_rows)
        ),
        "template_row_count_exact": (
            len(template_rows) == EXPECTED_ROW_COUNT
        ),
        "template_sha256_pinned": (
            template_hash == EXPECTED_TEMPLATE_SHA256
        ),
    }

    healthy = all(checks.values())

    result: dict[str, Any] = {
        "schema_version": (
            "geography_core_layer_district_crosswalk_decisions.v1"
        ),
        "status": (
            "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
            if healthy
            else "REVIEW_DECISIONS_INVALID"
        ),
        "healthy": healthy,
        "checks": checks,
        "allowed_review_decisions": sorted(
            ALLOWED_DECISIONS
        ),
        "allowed_evidence_bases": sorted(
            ALLOWED_EVIDENCE_BASES
        ),
        "expected_row_count": EXPECTED_ROW_COUNT,
        "row_count": len(reviewed_rows),
        "valid_row_count": (
            len(approved)
            + len(rejected)
            + len(deferred)
        ),
        "invalid_row_count": len(invalid),
        "counts_by_decision": dict(
            sorted(counts_by_decision.items())
        ),
        "counts_by_evidence_basis": dict(
            sorted(counts_by_evidence.items())
        ),
        "template_rows": str(args.template_rows),
        "template_rows_sha256": template_hash,
        "reviewed_csv": str(args.reviewed_csv),
        "reviewed_csv_sha256": sha256(args.reviewed_csv),
        "approved_rows": str(approved_path),
        "approved_rows_sha256": sha256(approved_path),
        "rejected_rows": str(rejected_path),
        "rejected_rows_sha256": sha256(rejected_path),
        "deferred_rows": str(deferred_path),
        "deferred_rows_sha256": sha256(deferred_path),
        "invalid_rows": str(invalid_path),
        "invalid_rows_sha256": sha256(invalid_path),
        "missing_columns": missing_columns,
        "missing_identities": [
            list(value) for value in missing_identities
        ],
        "unexpected_identities": [
            list(value) for value in unexpected_identities
        ],
        "duplicate_reviewed_identities": [
            list(value)
            for value in duplicate_reviewed_identities
        ],
        "policy": {
            "human_review_required": True,
            "approved_rows_remain_inactive": True,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "canonical_geography_changes_authorized": False,
            "android_behavior_change_authorized": False,
        },
        "database_writes_attempted": False,
    }

    checksum_source = dict(result)
    result["summary_checksum"] = checksum(
        checksum_source
    )

    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
