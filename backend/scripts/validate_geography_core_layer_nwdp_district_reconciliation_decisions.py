#!/usr/bin/env python3
"""Validate NWDP district reconciliation evidence decisions.

This validator writes partitioned local evidence only. Acceptance confirms
that NWDP evidence may support authoritative research; it never approves Core
mappings, changes canonical geography, or authorizes database/runtime action.
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
DEFAULT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
DEFAULT_TEMPLATE_ROWS = DEFAULT_DIR / (
    "geography_core_layer_nwdp_district_reconciliation_"
    "review_batch_rows.jsonl"
)
DEFAULT_REVIEWED_CSV = DEFAULT_DIR / (
    "geography_core_layer_nwdp_district_reconciliation_"
    "review_batch.csv"
)

EXPECTED_TEMPLATE_SHA256 = (
    "0ae567a34d739a92c8fa75a0b7e0713a9231d5c410ed8134b5e1881d8b49e420"
)
EXPECTED_ROW_COUNT = 13

ALLOWED_DECISIONS = {
    "ACCEPT_NWDP_RECONCILIATION_EVIDENCE_FOR_RESEARCH",
    "REJECT_NWDP_RECONCILIATION_EVIDENCE",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
ALLOWED_EVIDENCE_BASES = {
    "LGD_VILLAGE_CODE_CONTINUITY",
    "OFFICIAL_REORGANIZATION_NOTIFICATION",
    "AUTHORITATIVE_CURRENT_DISTRICT_GEOMETRY",
    "OTHER_DOCUMENTED_EVIDENCE",
}
AUTHORITATIVE_ACCEPTANCE_BASES = {
    "OFFICIAL_REORGANIZATION_NOTIFICATION",
    "AUTHORITATIVE_CURRENT_DISTRICT_GEOMETRY",
    "OTHER_DOCUMENTED_EVIDENCE",
}
REVIEW_FIELDS = {
    "review_decision",
    "review_evidence_basis",
    "authoritative_source_title",
    "authoritative_source_url",
    "authoritative_source_date",
    "authoritative_notification_number",
    "reviewer",
    "review_notes",
}
IDENTITY_FIELDS = (
    "state_lgd_code",
    "district_lgd_code",
)
SCHEMA_VERSION = (
    "geography_core_layer_nwdp_district_reconciliation_decisions.v1"
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
        default=DEFAULT_DIR,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def identity(row: dict[str, Any]) -> tuple[str, str]:
    return tuple(
        str(row.get(field) or "")
        for field in IDENTITY_FIELDS
    )


def csv_value_matches(value: str, expected: Any) -> bool:
    if expected is None:
        return value == ""
    if isinstance(expected, bool):
        return value.strip().casefold() == str(
            expected
        ).casefold()
    if isinstance(expected, int) and not isinstance(
        expected,
        bool,
    ):
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
        if not csv_value_matches(
            reviewed[field],
            expected,
        ):
            return False
    return True


def validate_row(
    reviewed: dict[str, str],
    template: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    decision = reviewed["review_decision"].strip()
    evidence = reviewed[
        "review_evidence_basis"
    ].strip()
    source_title = reviewed[
        "authoritative_source_title"
    ].strip()
    source_url = reviewed[
        "authoritative_source_url"
    ].strip()
    source_date = reviewed[
        "authoritative_source_date"
    ].strip()
    reviewer = reviewed["reviewer"].strip()
    notes = reviewed["review_notes"].strip()

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

    if (
        template["evidence_status"]
        == "NWDP_NO_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
        and evidence == "LGD_VILLAGE_CODE_CONTINUITY"
    ):
        errors.append(
            "no_nwdp_evidence_cannot_claim_village_code_continuity"
        )

    if decision == (
        "ACCEPT_NWDP_RECONCILIATION_EVIDENCE_FOR_RESEARCH"
    ):
        if evidence not in AUTHORITATIVE_ACCEPTANCE_BASES:
            errors.append(
                "acceptance_requires_authoritative_evidence_basis"
            )
        if not source_title:
            errors.append(
                "acceptance_authoritative_source_title_required"
            )
        if not source_url:
            errors.append(
                "acceptance_authoritative_source_url_required"
            )
        if not source_date:
            errors.append(
                "acceptance_authoritative_source_date_required"
            )
        if (
            template[
                "matched_canonical_village_count"
            ]
            <= 0
        ):
            errors.append(
                "acceptance_requires_nwdp_reconciliation_evidence"
            )

    if decision == (
        "REJECT_NWDP_RECONCILIATION_EVIDENCE"
    ):
        if evidence not in ALLOWED_EVIDENCE_BASES:
            errors.append(
                "rejection_evidence_basis_required"
            )

    if decision == (
        "DEFER_FOR_AUTHORITATIVE_RESEARCH"
    ):
        if (
            evidence
            and evidence not in ALLOWED_EVIDENCE_BASES
        ):
            errors.append(
                "deferral_evidence_basis_not_allowed"
            )

    return errors


def write_jsonl(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8") as handle:
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


def main() -> int:
    args = parse_args()

    template_rows = read_jsonl(args.template_rows)
    fieldnames, reviewed_rows = read_csv(
        args.reviewed_csv
    )

    template_by_identity = {
        identity(row): row for row in template_rows
    }
    reviewed_identities = [
        identity(row) for row in reviewed_rows
    ]
    template_identities = [
        identity(row) for row in template_rows
    ]

    required_columns = set(template_rows[0]) if template_rows else set()
    missing_columns = sorted(
        required_columns - set(fieldnames)
    )

    reviewed_identity_set = set(reviewed_identities)
    template_identity_set = set(template_identities)
    missing_identities = sorted(
        template_identity_set - reviewed_identity_set
    )
    unexpected_identities = sorted(
        reviewed_identity_set - template_identity_set
    )

    duplicate_identities = sorted(
        identity_value
        for identity_value, count in Counter(
            reviewed_identities
        ).items()
        if count > 1
    )

    accepted_rows = []
    rejected_rows = []
    deferred_rows = []
    invalid_rows = []

    counts_by_decision: Counter[str] = Counter()
    counts_by_evidence_basis: Counter[str] = Counter()

    for reviewed in reviewed_rows:
        row_identity = identity(reviewed)
        template = template_by_identity.get(row_identity)
        errors: list[str] = []

        if template is None:
            errors.append("identity_not_in_template")
        else:
            if not immutable_fields_match(
                reviewed,
                template,
            ):
                errors.append(
                    "immutable_fields_changed"
                )
            errors.extend(
                validate_row(reviewed, template)
            )

        output_row: dict[str, Any] = dict(reviewed)
        output_row["validation_errors"] = sorted(
            set(errors)
        )

        if errors:
            invalid_rows.append(output_row)
            continue

        decision = reviewed[
            "review_decision"
        ].strip()
        evidence = reviewed[
            "review_evidence_basis"
        ].strip()

        counts_by_decision[decision] += 1
        if evidence:
            counts_by_evidence_basis[evidence] += 1

        if decision == (
            "ACCEPT_NWDP_RECONCILIATION_EVIDENCE_FOR_RESEARCH"
        ):
            accepted_rows.append(output_row)
        elif decision == (
            "REJECT_NWDP_RECONCILIATION_EVIDENCE"
        ):
            rejected_rows.append(output_row)
        else:
            deferred_rows.append(output_row)

    checks = {
        "template_sha256_pinned": (
            sha256(args.template_rows)
            == EXPECTED_TEMPLATE_SHA256
        ),
        "template_row_count_exact": (
            len(template_rows) == EXPECTED_ROW_COUNT
        ),
        "reviewed_row_count_exact": (
            len(reviewed_rows) == EXPECTED_ROW_COUNT
        ),
        "required_columns_present": (
            not missing_columns
        ),
        "template_identity_unique": (
            len(template_identities)
            == len(set(template_identities))
        ),
        "reviewed_identity_unique": (
            not duplicate_identities
        ),
        "scope_exact": (
            not missing_identities
            and not unexpected_identities
        ),
        "immutable_fields_unchanged": all(
            "immutable_fields_changed"
            not in row["validation_errors"]
            for row in invalid_rows
        ),
        "all_rows_valid": not invalid_rows,
        "decision_partition_exact": (
            len(accepted_rows)
            + len(rejected_rows)
            + len(deferred_rows)
            == len(reviewed_rows)
        ),
        "no_database_writes": True,
        "not_authorized_for_apply": True,
    }

    healthy = all(checks.values())

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    accepted_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "accepted_rows.jsonl"
    )
    rejected_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "rejected_rows.jsonl"
    )
    deferred_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "deferred_rows.jsonl"
    )
    invalid_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "invalid_rows.jsonl"
    )
    summary_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "decision_validation.json"
    )

    write_jsonl(accepted_path, accepted_rows)
    write_jsonl(rejected_path, rejected_rows)
    write_jsonl(deferred_path, deferred_rows)
    write_jsonl(invalid_path, invalid_rows)

    core_summary = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "VALIDATED_RESEARCH_ONLY_NOT_AUTHORIZED_FOR_APPLY"
            if healthy
            else "RECONCILIATION_DECISIONS_INVALID"
        ),
        "healthy": healthy,
        "database_writes_attempted": False,
        "template_rows": str(
            args.template_rows.resolve()
        ),
        "template_rows_sha256": sha256(
            args.template_rows
        ),
        "reviewed_csv": str(
            args.reviewed_csv.resolve()
        ),
        "reviewed_csv_sha256": sha256(
            args.reviewed_csv
        ),
        "expected_row_count": EXPECTED_ROW_COUNT,
        "row_count": len(reviewed_rows),
        "valid_row_count": (
            len(reviewed_rows) - len(invalid_rows)
        ),
        "invalid_row_count": len(invalid_rows),
        "counts_by_decision": dict(
            sorted(counts_by_decision.items())
        ),
        "counts_by_evidence_basis": dict(
            sorted(counts_by_evidence_basis.items())
        ),
        "allowed_review_decisions": sorted(
            ALLOWED_DECISIONS
        ),
        "allowed_evidence_bases": sorted(
            ALLOWED_EVIDENCE_BASES
        ),
        "missing_columns": missing_columns,
        "missing_identities": missing_identities,
        "unexpected_identities": unexpected_identities,
        "duplicate_reviewed_identities": (
            duplicate_identities
        ),
        "checks": checks,
        "policy": {
            "lgd_remains_canonical": True,
            "accepted_rows_are_research_evidence_only": True,
            "authoritative_confirmation_required_for_acceptance": True,
            "core_mapping_approval_authorized": False,
            "canonical_geography_changes_authorized": False,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
    }

    summary = {
        **core_summary,
        "accepted_rows": str(accepted_path.resolve()),
        "accepted_rows_sha256": sha256(accepted_path),
        "rejected_rows": str(rejected_path.resolve()),
        "rejected_rows_sha256": sha256(rejected_path),
        "deferred_rows": str(deferred_path.resolve()),
        "deferred_rows_sha256": sha256(deferred_path),
        "invalid_rows": str(invalid_path.resolve()),
        "invalid_rows_sha256": sha256(invalid_path),
        "summary_checksum": canonical_sha256(core_summary),
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
