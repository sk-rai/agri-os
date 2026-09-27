#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path

EXPECTED_TEMPLATE_SHA256 = (
    "a7fdcd8d392e9d84df47c78af8cce7935d75ffff0ea8f38e5d74990befa23be7"
)
DECISIONS = {
    "APPROVE_PROJECT_SCOPED_MANUAL_MAPPING",
    "CONFIRM_GLOBAL_REMEDIATION_ROUTE",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
}
REVIEW_FIELDS = {
    "project_tenant_id",
    "project_id",
    "review_decision",
    "reviewer",
    "review_notes",
    "evidence_reference",
}
REQUIRED_COLUMNS = REVIEW_FIELDS | {
    "candidate_id",
    "source_feature_id",
    "resolution_route",
    "project_manual_mapping_eligible",
    "canonical_target_village_id",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-rows", required=True, type=Path)
    parser.add_argument("--reviewed-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    template_hash = sha256(args.template_rows)
    template_rows = [
        json.loads(line)
        for line in args.template_rows.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    template_by_id = {
        row["candidate_id"]: row for row in template_rows
    }

    with args.reviewed_csv.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        reviewed_rows = list(reader)

    reviewed_ids = [
        row.get("candidate_id", "") for row in reviewed_rows
    ]
    missing_columns = sorted(REQUIRED_COLUMNS - columns)
    missing_ids = sorted(set(template_by_id) - set(reviewed_ids))
    unexpected_ids = sorted(set(reviewed_ids) - set(template_by_id))

    valid_rows = []
    invalid_rows = []
    partitions = {
        "APPROVE_PROJECT_SCOPED_MANUAL_MAPPING": [],
        "CONFIRM_GLOBAL_REMEDIATION_ROUTE": [],
        "DEFER_FOR_AUTHORITATIVE_RESEARCH": [],
    }

    immutable_fields = sorted(
        set(template_rows[0]) - REVIEW_FIELDS
    ) if template_rows else []

    for row in reviewed_rows:
        errors = []
        candidate_id = row.get("candidate_id", "")
        template = template_by_id.get(candidate_id)

        if template is None:
            errors.append("CANDIDATE_OUTSIDE_TEMPLATE_SCOPE")
        else:
            for field in immutable_fields:
                expected = template.get(field)
                actual = row.get(field, "")
                if isinstance(expected, bool):
                    unchanged = truthy(actual) == expected
                elif expected is None:
                    unchanged = actual in {"", None}
                else:
                    unchanged = str(actual) == str(expected)
                if not unchanged:
                    errors.append(
                        f"IMMUTABLE_FIELD_CHANGED:{field}"
                    )

        decision = row.get("review_decision", "").strip()
        reviewer = row.get("reviewer", "").strip()
        notes = row.get("review_notes", "").strip()
        reference = row.get("evidence_reference", "").strip()
        tenant_id = row.get("project_tenant_id", "").strip()
        project_id = row.get("project_id", "").strip()

        if decision not in DECISIONS:
            errors.append("INVALID_OR_BLANK_REVIEW_DECISION")
        if not reviewer:
            errors.append("REVIEWER_REQUIRED")
        if not notes:
            errors.append("REVIEW_NOTES_REQUIRED")

        if decision == "APPROVE_PROJECT_SCOPED_MANUAL_MAPPING":
            eligible = (
                template is not None
                and template["project_manual_mapping_eligible"]
            )
            if not eligible:
                errors.append(
                    "PROJECT_MANUAL_MAPPING_NOT_ELIGIBLE"
                )
            if not template or not template.get(
                "canonical_target_village_id"
            ):
                errors.append("CANONICAL_TARGET_REQUIRED")
            if not tenant_id:
                errors.append("PROJECT_TENANT_ID_REQUIRED")
            if not valid_uuid(project_id):
                errors.append("VALID_PROJECT_ID_REQUIRED")
            if not reference:
                errors.append("EVIDENCE_REFERENCE_REQUIRED")

        elif decision == "CONFIRM_GLOBAL_REMEDIATION_ROUTE":
            if tenant_id or project_id:
                errors.append(
                    "PROJECT_SCOPE_FORBIDDEN_FOR_GLOBAL_ROUTE"
                )
            if not reference:
                errors.append("EVIDENCE_REFERENCE_REQUIRED")

        elif decision == "DEFER_FOR_AUTHORITATIVE_RESEARCH":
            if tenant_id or project_id:
                errors.append(
                    "PROJECT_SCOPE_FORBIDDEN_FOR_DEFER"
                )
            if reference:
                errors.append(
                    "EVIDENCE_REFERENCE_FORBIDDEN_FOR_DEFER"
                )

        output = {
            **row,
            "validation_errors": sorted(set(errors)),
        }
        if errors:
            invalid_rows.append(output)
        else:
            valid_rows.append(output)
            partitions[decision].append(output)

    identity_scope_exact = (
        set(reviewed_ids) == set(template_by_id)
    )
    reviewed_identity_unique = (
        len(reviewed_ids) == len(set(reviewed_ids))
    )
    immutable_unchanged = not any(
        any(
            error.startswith("IMMUTABLE_FIELD_CHANGED:")
            for error in row["validation_errors"]
        )
        for row in invalid_rows
    )

    checks = {
        "template_sha256_pinned":
            template_hash == EXPECTED_TEMPLATE_SHA256,
        "required_columns_present": not missing_columns,
        "template_row_count_exact": len(template_rows) == 16,
        "reviewed_row_count_exact": len(reviewed_rows) == 16,
        "template_candidate_identity_unique":
            len(template_by_id) == len(template_rows),
        "reviewed_candidate_identity_unique":
            reviewed_identity_unique,
        "candidate_identity_scope_exact": identity_scope_exact,
        "immutable_fields_unchanged": immutable_unchanged,
        "all_rows_valid": not invalid_rows,
        "decision_partition_exact":
            len(valid_rows) == len(reviewed_rows),
        "no_database_writes": True,
        "not_authorized_for_apply": True,
    }
    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = "nwdp_legacy_canonical_gap_resolution"
    paths = {
        "project_approved":
            args.output_dir
            / f"{prefix}_project_approved_rows.jsonl",
        "global_confirmed":
            args.output_dir
            / f"{prefix}_global_confirmed_rows.jsonl",
        "deferred":
            args.output_dir
            / f"{prefix}_deferred_rows.jsonl",
        "invalid":
            args.output_dir
            / f"{prefix}_invalid_rows.jsonl",
    }
    write_jsonl(
        paths["project_approved"],
        partitions["APPROVE_PROJECT_SCOPED_MANUAL_MAPPING"],
    )
    write_jsonl(
        paths["global_confirmed"],
        partitions["CONFIRM_GLOBAL_REMEDIATION_ROUTE"],
    )
    write_jsonl(
        paths["deferred"],
        partitions["DEFER_FOR_AUTHORITATIVE_RESEARCH"],
    )
    write_jsonl(paths["invalid"], invalid_rows)

    summary_core = {
        "schema_version":
            "nwdp_legacy_canonical_gap_resolution_decisions.v1",
        "status":
            "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
            if healthy else "REVIEW_DECISIONS_INVALID",
        "healthy": healthy,
        "template_rows": str(args.template_rows.resolve()),
        "template_rows_sha256": template_hash,
        "reviewed_csv": str(args.reviewed_csv.resolve()),
        "reviewed_csv_sha256": sha256(args.reviewed_csv),
        "expected_row_count": 16,
        "row_count": len(reviewed_rows),
        "valid_row_count": len(valid_rows),
        "invalid_row_count": len(invalid_rows),
        "counts_by_decision": dict(sorted(Counter(
            row["review_decision"] for row in valid_rows
        ).items())),
        "checks": checks,
        "missing_columns": missing_columns,
        "missing_candidate_ids": missing_ids,
        "unexpected_candidate_ids": unexpected_ids,
        "allowed_review_decisions": sorted(DECISIONS),
        "policy": {
            "canonical_changes_authorized": False,
            "project_mapping_apply_authorized": False,
            "runtime_activation_authorized": False,
            "human_review_required": True,
            "project_manual_mapping_tenant_scoped": True,
            "project_manual_mapping_project_scoped": True,
        },
        "database_writes_attempted": False,
    }
    for name, output_path in paths.items():
        summary_core[f"{name}_rows"] = str(
            output_path.resolve()
        )
        summary_core[f"{name}_rows_sha256"] = sha256(
            output_path
        )

    checksum = hashlib.sha256(
        json.dumps(
            summary_core,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    summary = {
        **summary_core,
        "summary_checksum": checksum,
    }
    summary_path = (
        args.output_dir
        / f"{prefix}_decision_validation.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
