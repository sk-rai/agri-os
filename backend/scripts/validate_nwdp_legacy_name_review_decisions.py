#!/usr/bin/env python3
"""Validate completed legacy NWDP name-review decisions without database writes."""

from __future__ import annotations

import argparse
import csv
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


SCHEMA_VERSION = "nwdp_legacy_name_review_decisions.v2"

PROFILE_CONFIGS = {
    "strong": {
        "template_rows_filename":
            "nwdp_legacy_strong_name_review_batch_rows.jsonl",
        "reviewed_csv_filename":
            "nwdp_legacy_strong_name_review_batch.csv",
        "expected_template_rows_sha256":
            "7cb16e8003488db5e9d2fb08c4f3248ce277cef757954ba3161f22c58dbb3b8b",
        "expected_rows": 217,
        "output_prefix": "nwdp_legacy_name_review",
        "allowed_evidence_bases": {
            "ADMINISTRATIVE_QUALIFIER",
            "TOKEN_ORDER_EQUIVALENCE",
            "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
            "AUTHORITATIVE_SOURCE_CONFIRMATION",
            "OTHER_DOCUMENTED_EVIDENCE",
        },
        "additional_required_columns": set(),
    },
    "high-similarity": {
        "template_rows_filename":
            "nwdp_legacy_high_similarity_review_batch_rows.jsonl",
        "reviewed_csv_filename":
            "nwdp_legacy_high_similarity_review_batch.csv",
        "expected_template_rows_sha256":
            "13eab896a106893f5709b018200745123874f643072cac0f673ef259511c75ae",
        "expected_rows": 4_004,
        "output_prefix":
            "nwdp_legacy_high_similarity_name_review",
        "allowed_evidence_bases": {
            "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
            "AUTHORITATIVE_SOURCE_CONFIRMATION",
            "OTHER_DOCUMENTED_EVIDENCE",
        },
        "additional_required_columns": {
            "review_priority",
            "review_focus",
            "source_name_normalized",
            "canonical_name_normalized",
        },
    },
    "moderate-similarity": {
        "template_rows_filename":
            "nwdp_legacy_moderate_similarity_review_batch_rows.jsonl",
        "reviewed_csv_filename":
            "nwdp_legacy_moderate_similarity_review_batch.csv",
        "expected_template_rows_sha256":
            "f11610c7b31f6de52ecd13af11e86ee3f88e134c66dfc2a31204fc113616af4a",
        "expected_rows": 1_877,
        "output_prefix":
            "nwdp_legacy_moderate_similarity_name_review",
        "allowed_evidence_bases": {
            "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
            "AUTHORITATIVE_SOURCE_CONFIRMATION",
            "OTHER_DOCUMENTED_EVIDENCE",
        },
        "additional_required_columns": {
            "review_priority",
            "review_focus",
            "source_name_normalized",
            "canonical_name_normalized",
        },
    },

    "low-similarity": {
        "template_rows_filename":
            "nwdp_legacy_low_similarity_review_batch_rows.jsonl",
        "reviewed_csv_filename":
            "nwdp_legacy_low_similarity_review_batch.csv",
        "expected_template_rows_sha256":
            "52969883443199b87d3b805df4ec6c38861b19421899f20a2f8b3b9b11bf92e1",
        "expected_rows": 1_442,
        "output_prefix":
            "nwdp_legacy_low_similarity_name_review",
        "allowed_evidence_bases": {
            "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
            "AUTHORITATIVE_SOURCE_CONFIRMATION",
        },
        "additional_required_columns": {
            "review_priority",
            "review_focus",
            "source_name_normalized",
            "canonical_name_normalized",
        },
    },

}

ALLOWED_DECISIONS = {
    "APPROVE_EQUIVALENCE",
    "REJECT_EQUIVALENCE",
    "DEFER_FOR_SOURCE_RESEARCH",
}
ALLOWED_EVIDENCE_BASES = {
    "ADMINISTRATIVE_QUALIFIER",
    "TOKEN_ORDER_EQUIVALENCE",
    "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
    "AUTHORITATIVE_SOURCE_CONFIRMATION",
    "OTHER_DOCUMENTED_EVIDENCE",
}
REFERENCE_REQUIRED_BASES = {
    "VERNACULAR_TRANSLITERATION_EQUIVALENCE",
    "AUTHORITATIVE_SOURCE_CONFIRMATION",
    "OTHER_DOCUMENTED_EVIDENCE",
}

MUTABLE_FIELDS = {
    "evidence_basis",
    "evidence_reference",
    "review_decision",
    "reviewer",
    "review_notes",
}

REQUIRED_COLUMNS = {
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
    "evidence_basis",
    "evidence_reference",
    "review_decision",
    "reviewer",
    "review_notes",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_CONFIGS),
        default="strong",
    )
    parser.add_argument(
        "--template-rows",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


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


def load_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = [
            {
                key: text(value)
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]

    return headers, rows


def immutable_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def validate_review_row(
    row: dict[str, str],
    template: dict[str, Any],
    immutable_columns: list[str],
    profile_allowed_evidence_bases: set[str],
) -> list[str]:
    failures: list[str] = []

    for column in immutable_columns:
        reviewed_value = text(row.get(column))
        template_value = immutable_value(template.get(column))

        if reviewed_value != template_value:
            failures.append(
                f"IMMUTABLE_FIELD_CHANGED:{column}"
            )

    decision = text(row.get("review_decision"))
    reviewer = text(row.get("reviewer"))
    notes = text(row.get("review_notes"))
    basis = text(row.get("evidence_basis"))
    reference = text(row.get("evidence_reference"))

    if not decision:
        failures.append("DECISION_MISSING")
        return failures

    if decision not in ALLOWED_DECISIONS:
        failures.append(f"DECISION_INVALID:{decision}")

    if not reviewer:
        failures.append("REVIEWER_MISSING")

    if not notes:
        failures.append("REVIEW_NOTES_MISSING")

    if basis and basis not in ALLOWED_EVIDENCE_BASES:
        failures.append(f"EVIDENCE_BASIS_INVALID:{basis}")
    elif (
        basis
        and basis not in profile_allowed_evidence_bases
    ):
        failures.append(
            f"EVIDENCE_BASIS_NOT_ALLOWED_FOR_PROFILE:{basis}"
        )

    if decision == "APPROVE_EQUIVALENCE":
        if not basis:
            failures.append("APPROVAL_EVIDENCE_BASIS_MISSING")

        if basis in REFERENCE_REQUIRED_BASES and not reference:
            failures.append(
                "APPROVAL_EVIDENCE_REFERENCE_MISSING"
            )

        band = text(template.get("evidence_band"))

        if (
            basis == "ADMINISTRATIVE_QUALIFIER"
            and band != "ADMINISTRATIVE_QUALIFIER_ONLY"
        ):
            failures.append(
                "ADMINISTRATIVE_BASIS_BAND_MISMATCH"
            )

        if (
            basis == "TOKEN_ORDER_EQUIVALENCE"
            and band != "TOKEN_ORDER_ONLY"
        ):
            failures.append("TOKEN_ORDER_BASIS_BAND_MISMATCH")

    return failures


def main() -> int:
    args = parse_args()
    config = PROFILE_CONFIGS[args.profile]

    template_path = (
        args.template_rows
        if args.template_rows is not None
        else (
            DEFAULT_OUTPUT_DIR
            / config["template_rows_filename"]
        )
    ).resolve()
    reviewed_csv_path = (
        args.reviewed_csv
        if args.reviewed_csv is not None
        else (
            DEFAULT_OUTPUT_DIR
            / config["reviewed_csv_filename"]
        )
    ).resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    expected_template_sha256 = str(
        config["expected_template_rows_sha256"]
    )
    expected_rows = int(config["expected_rows"])
    output_prefix = str(config["output_prefix"])
    profile_allowed_evidence_bases = set(
        config["allowed_evidence_bases"]
    )
    required_columns = (
        REQUIRED_COLUMNS
        | set(config["additional_required_columns"])
    )

    if not template_path.is_file():
        raise ValueError(
            f"TEMPLATE_ROWS_NOT_FOUND:{template_path}"
        )
    if not reviewed_csv_path.is_file():
        raise ValueError(
            f"REVIEWED_CSV_NOT_FOUND:{reviewed_csv_path}"
        )

    template_sha256 = sha256_file(template_path)
    template_rows = load_jsonl(template_path)
    headers, reviewed_rows = load_csv(reviewed_csv_path)

    template_by_candidate = {
        text(row.get("candidate_id")): row
        for row in template_rows
    }

    duplicate_template_ids = (
        len(template_by_candidate) != len(template_rows)
    )

    reviewed_candidate_ids = [
        text(row.get("candidate_id"))
        for row in reviewed_rows
    ]
    duplicate_reviewed_ids = (
        len(reviewed_candidate_ids)
        != len(set(reviewed_candidate_ids))
    )

    missing_columns = sorted(
        required_columns - set(headers)
    )
    unexpected_candidate_ids = sorted(
        candidate_id
        for candidate_id in reviewed_candidate_ids
        if candidate_id not in template_by_candidate
    )
    missing_candidate_ids = sorted(
        set(template_by_candidate)
        - set(reviewed_candidate_ids)
    )

    immutable_columns = sorted(
        required_columns - MUTABLE_FIELDS
    )

    validated_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    if not missing_columns:
        for row in reviewed_rows:
            candidate_id = text(row.get("candidate_id"))
            template = template_by_candidate.get(candidate_id)

            if template is None:
                continue

            failures = validate_review_row(
                row,
                template,
                immutable_columns,
                profile_allowed_evidence_bases,
            )

            validated = {
                **template,
                "evidence_basis": text(
                    row.get("evidence_basis")
                ),
                "evidence_reference": text(
                    row.get("evidence_reference")
                ),
                "review_decision": text(
                    row.get("review_decision")
                ),
                "reviewer": text(row.get("reviewer")),
                "review_notes": text(
                    row.get("review_notes")
                ),
                "decision_validation_failures": failures,
                "decision_valid": not failures,
                "database_action_authorized": False,
            }

            if failures:
                invalid_rows.append(validated)
            else:
                validated_rows.append(validated)

    validated_rows.sort(
        key=lambda row: int(row["sequence"])
    )
    invalid_rows.sort(
        key=lambda row: int(row["sequence"])
    )

    decision_counts = Counter(
        text(row.get("review_decision"))
        for row in validated_rows
    )
    evidence_basis_counts = Counter(
        text(row.get("evidence_basis"))
        for row in validated_rows
        if text(row.get("evidence_basis"))
    )

    approved_rows = [
        row
        for row in validated_rows
        if row["review_decision"]
        == "APPROVE_EQUIVALENCE"
    ]
    rejected_rows = [
        row
        for row in validated_rows
        if row["review_decision"]
        == "REJECT_EQUIVALENCE"
    ]
    deferred_rows = [
        row
        for row in validated_rows
        if row["review_decision"]
        == "DEFER_FOR_SOURCE_RESEARCH"
    ]

    checks = {
        "template_sha256_pinned": (
            template_sha256
            == expected_template_sha256
        ),
        "template_row_count_exact": (
            len(template_rows) == expected_rows
        ),
        "reviewed_row_count_exact": (
            len(reviewed_rows) == expected_rows
        ),
        "required_columns_present": not missing_columns,
        "template_candidate_identity_unique": (
            not duplicate_template_ids
        ),
        "reviewed_candidate_identity_unique": (
            not duplicate_reviewed_ids
        ),
        "candidate_identity_scope_exact": (
            not missing_candidate_ids
            and not unexpected_candidate_ids
        ),
        "all_rows_valid": (
            len(validated_rows) == expected_rows
            and not invalid_rows
        ),
        "decision_partition_exact": (
            len(approved_rows)
            + len(rejected_rows)
            + len(deferred_rows)
            == expected_rows
        ),
        "no_database_writes": True,
        "not_authorized_for_apply": True,
    }

    healthy = all(checks.values())

    approved_path = (
        output_dir
        / f"{output_prefix}_approved_rows.jsonl"
    )
    rejected_path = (
        output_dir
        / f"{output_prefix}_rejected_rows.jsonl"
    )
    deferred_path = (
        output_dir
        / f"{output_prefix}_deferred_rows.jsonl"
    )
    invalid_path = (
        output_dir
        / f"{output_prefix}_invalid_rows.jsonl"
    )
    summary_path = (
        output_dir
        / f"{output_prefix}_decision_validation.json"
    )

    atomic_write_jsonl(approved_path, approved_rows)
    atomic_write_jsonl(rejected_path, rejected_rows)
    atomic_write_jsonl(deferred_path, deferred_rows)
    atomic_write_jsonl(invalid_path, invalid_rows)

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": args.profile,
        "expected_row_count": expected_rows,
        "allowed_evidence_bases": sorted(
            profile_allowed_evidence_bases
        ),
        "status": (
            "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
            if healthy
            else "REVIEW_DECISIONS_INVALID"
        ),
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
        "template_rows": str(template_path),
        "template_rows_sha256": template_sha256,
        "reviewed_csv": str(reviewed_csv_path),
        "reviewed_csv_sha256": sha256_file(
            reviewed_csv_path
        ),
        "row_count": len(reviewed_rows),
        "valid_row_count": len(validated_rows),
        "invalid_row_count": len(invalid_rows),
        "counts_by_decision": dict(
            sorted(decision_counts.items())
        ),
        "counts_by_evidence_basis": dict(
            sorted(evidence_basis_counts.items())
        ),
        "missing_columns": missing_columns,
        "missing_candidate_ids": missing_candidate_ids,
        "unexpected_candidate_ids": (
            unexpected_candidate_ids
        ),
        "approved_rows": str(approved_path),
        "approved_rows_sha256": sha256_file(
            approved_path
        ),
        "rejected_rows": str(rejected_path),
        "rejected_rows_sha256": sha256_file(
            rejected_path
        ),
        "deferred_rows": str(deferred_path),
        "deferred_rows_sha256": sha256_file(
            deferred_path
        ),
        "invalid_rows": str(invalid_path),
        "invalid_rows_sha256": sha256_file(
            invalid_path
        ),
    }

    summary["summary_checksum"] = canonical_checksum(summary)
    atomic_write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
