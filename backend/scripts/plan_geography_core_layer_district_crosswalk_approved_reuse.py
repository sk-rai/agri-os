#!/usr/bin/env python3
"""Plan reuse of validated Core district crosswalk mappings.

This is read-only. It consumes the validated approved-row partition and
reconciles each approval to an existing inactive POLY_REV district mapping.
It never inserts, updates, activates, promotes, or deletes database rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
DEFAULT_VALIDATION = DEFAULT_DIR / (
    "geography_core_layer_district_crosswalk_decision_validation.json"
)
DEFAULT_APPROVED = DEFAULT_DIR / (
    "geography_core_layer_district_crosswalk_approved_rows.jsonl"
)

VALIDATION_SCHEMA = "geography_core_layer_district_crosswalk_decisions.v1"
VALIDATION_STATUS = "VALIDATED_NOT_AUTHORIZED_FOR_APPLY"
APPROVAL_DECISION = "APPROVE_INACTIVE_MANUAL_REVIEW_MAPPING"
SOURCE_CONFIDENCE = "POLY_REV"
SOURCE_REVIEW_STATUS = "MANUAL_REVIEW"
PLAN_SCHEMA = (
    "geography_core_layer_district_crosswalk_approved_reuse_plan.v1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation-summary",
        type=Path,
        default=DEFAULT_VALIDATION,
    )
    parser.add_argument(
        "--approved-rows",
        type=Path,
        default=DEFAULT_APPROVED,
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
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def mapping_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("target_region_code") or row.get("region_code") or ""),
        str(row.get("scope_level") or ""),
        str(row.get("state_lgd_code") or ""),
        str(row.get("district_lgd_code") or ""),
    )


def load_existing_mappings() -> list[dict[str, Any]]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return [
            dict(row)
            for row in db.execute(
                text(
                    """
                    select
                      id::text as mapping_id,
                      region_id::text as region_id,
                      region_code,
                      scope_level,
                      state_lgd_code,
                      district_lgd_code,
                      confidence,
                      review_status,
                      version,
                      is_active
                    from geography_climate_region_mappings
                    where scope_level = 'DISTRICT'
                    order by
                      region_code,
                      state_lgd_code,
                      district_lgd_code,
                      id
                    """
                )
            ).mappings()
        ]
    finally:
        db.close()


def validate_inputs(
    summary: dict[str, Any],
    approved_path: Path,
    approved_rows: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if summary.get("schema_version") != VALIDATION_SCHEMA:
        errors.append("validation_schema_mismatch")
    if summary.get("status") != VALIDATION_STATUS:
        errors.append("validation_status_not_approved")
    if summary.get("healthy") is not True:
        errors.append("validation_not_healthy")

    checks = summary.get("checks") or {}
    if not checks or not all(value is True for value in checks.values()):
        errors.append("validation_checks_not_all_true")

    if summary.get("approved_rows_sha256") != sha256(approved_path):
        errors.append("approved_rows_sha256_mismatch")

    expected_approved = int(
        (summary.get("counts_by_decision") or {}).get(
            APPROVAL_DECISION,
            0,
        )
    )
    if expected_approved != len(approved_rows):
        errors.append("approved_row_count_mismatch")

    identities = [mapping_key(row) for row in approved_rows]
    if len(identities) != len(set(identities)):
        errors.append("approved_mapping_identity_not_unique")

    for row in approved_rows:
        if row.get("review_decision") != APPROVAL_DECISION:
            errors.append("approved_partition_contains_non_approval")
            break

    return sorted(set(errors))


def reconcile(
    approved_rows: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in existing_rows:
        index.setdefault(mapping_key(row), []).append(row)

    plan_rows = []
    for approved in sorted(
        approved_rows,
        key=lambda row: (
            str(row.get("state_lgd_code") or ""),
            str(row.get("district_lgd_code") or ""),
            str(row.get("region_system") or ""),
        ),
    ):
        key = mapping_key(approved)
        matches = index.get(key, [])
        exact = [
            row
            for row in matches
            if str(row.get("region_id") or "")
            == str(approved.get("target_region_id") or "")
        ]

        action = "BLOCKED_APPROVED_ROW_NOT_FOUND"
        reasons: list[str] = []

        if len(matches) > 1 or len(exact) > 1:
            action = "BLOCKED_EXISTING_MAPPING_MISMATCH"
            reasons.append("multiple_existing_mapping_rows")
        elif not exact:
            if matches:
                action = "BLOCKED_EXISTING_MAPPING_MISMATCH"
                reasons.append("target_region_id_mismatch")
            else:
                reasons.append("existing_mapping_not_found")
        else:
            existing = exact[0]
            if existing["is_active"]:
                action = "BLOCKED_MAPPING_ALREADY_ACTIVE"
                reasons.append("existing_mapping_is_active")
            elif existing["confidence"] != SOURCE_CONFIDENCE:
                action = "BLOCKED_EXISTING_MAPPING_MISMATCH"
                reasons.append("existing_confidence_not_poly_rev")
            elif existing["review_status"] != SOURCE_REVIEW_STATUS:
                action = "BLOCKED_EXISTING_MAPPING_MISMATCH"
                reasons.append("existing_review_status_not_manual_review")
            else:
                action = "REUSE_EXISTING_INACTIVE_MAPPING"

        existing = exact[0] if len(exact) == 1 else None
        mapping_id = existing["mapping_id"] if existing else None

        plan_rows.append(
            {
                "state_or_ut": approved.get("state_or_ut"),
                "state_lgd_code": approved.get("state_lgd_code"),
                "district": approved.get("district"),
                "district_lgd_code": approved.get("district_lgd_code"),
                "region_system": approved.get("region_system"),
                "region_class_name": approved.get("region_class_name"),
                "target_region_id": approved.get("target_region_id"),
                "target_region_code": approved.get("target_region_code"),
                "review_decision": approved.get("review_decision"),
                "review_evidence_basis": approved.get(
                    "review_evidence_basis"
                ),
                "reviewer": approved.get("reviewer"),
                "existing_mapping_id": mapping_id,
                "existing_confidence": (
                    existing.get("confidence") if existing else None
                ),
                "existing_review_status": (
                    existing.get("review_status") if existing else None
                ),
                "existing_is_active": (
                    bool(existing.get("is_active"))
                    if existing
                    else None
                ),
                "plan_action": action,
                "blocked_reasons": reasons,
                "rollback_identity": (
                    f"geography_climate_region_mappings:{mapping_id}"
                    if mapping_id
                    else None
                ),
                "would_insert": False,
                "would_update": False,
                "would_activate": False,
                "would_promote": False,
                "database_writes_attempted": False,
            }
        )

    return plan_rows


def write_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / (
        "geography_core_layer_district_crosswalk_approved_reuse_plan_rows.jsonl"
    )
    csv_path = output_dir / (
        "geography_core_layer_district_crosswalk_approved_reuse_plan.csv"
    )
    summary_path = output_dir / (
        "geography_core_layer_district_crosswalk_approved_reuse_plan.json"
    )

    with rows_path.open("w", encoding="utf-8") as handle:
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

    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["blocked_reasons"] = json.dumps(
            row["blocked_reasons"],
            ensure_ascii=False,
            sort_keys=True,
        )
        flat_rows.append(flat)

    fieldnames = sorted(
        {field for row in flat_rows for field in row}
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)

    summary["rows"] = str(rows_path.resolve())
    summary["rows_sha256"] = sha256(rows_path)
    summary["csv"] = str(csv_path.resolve())
    summary["csv_sha256"] = sha256(csv_path)
    summary["summary_checksum"] = canonical_sha256(
        {
            key: value
            for key, value in summary.items()
            if key not in {
                "rows",
                "rows_sha256",
                "csv",
                "csv_sha256",
                "summary_checksum",
            }
        }
    )
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
    return summary_path, rows_path, csv_path


def main() -> int:
    args = parse_args()

    if not args.validation_summary.exists():
        print("validation summary missing", file=sys.stderr)
        return 1
    if not args.approved_rows.exists():
        print("approved rows missing", file=sys.stderr)
        return 1

    validation = json.loads(
        args.validation_summary.read_text(encoding="utf-8")
    )
    approved_rows = read_jsonl(args.approved_rows)
    errors = validate_inputs(
        validation,
        args.approved_rows,
        approved_rows,
    )

    if errors:
        print(
            json.dumps(
                {
                    "schema_version": PLAN_SCHEMA,
                    "healthy": False,
                    "status": "VALIDATED_APPROVALS_REQUIRED",
                    "input_errors": errors,
                    "database_writes_attempted": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    plan_rows = reconcile(
        approved_rows,
        load_existing_mappings(),
    )
    counts = Counter(row["plan_action"] for row in plan_rows)
    reusable = counts.get("REUSE_EXISTING_INACTIVE_MAPPING", 0)
    blocked = len(plan_rows) - reusable

    checks = {
        "validation_healthy": validation["healthy"] is True,
        "validation_status_exact": (
            validation["status"] == VALIDATION_STATUS
        ),
        "approved_rows_sha256_pinned": (
            validation["approved_rows_sha256"]
            == sha256(args.approved_rows)
        ),
        "approved_row_count_exact": (
            len(plan_rows)
            == int(
                validation["counts_by_decision"].get(
                    APPROVAL_DECISION,
                    0,
                )
            )
        ),
        "approved_identity_unique": (
            len(plan_rows)
            == len(
                {
                    (
                        row["district_lgd_code"],
                        row["region_system"],
                    )
                    for row in plan_rows
                }
            )
        ),
        "no_duplicate_inserts_planned": all(
            not row["would_insert"] for row in plan_rows
        ),
        "no_updates_planned": all(
            not row["would_update"] for row in plan_rows
        ),
        "no_activation_planned": all(
            not row["would_activate"] for row in plan_rows
        ),
        "no_promotion_planned": all(
            not row["would_promote"] for row in plan_rows
        ),
        "no_database_writes": True,
        "not_authorized_for_apply": True,
    }
    healthy = all(checks.values()) and blocked == 0

    summary = {
        "schema_version": PLAN_SCHEMA,
        "status": (
            "EXISTING_INACTIVE_REUSE_PLAN_READY_NOT_AUTHORIZED"
            if healthy
            else "APPROVED_REUSE_PLAN_BLOCKED"
        ),
        "healthy": healthy,
        "database_writes_attempted": False,
        "validation_summary": str(
            args.validation_summary.resolve()
        ),
        "validation_summary_sha256": sha256(
            args.validation_summary
        ),
        "approved_rows": str(args.approved_rows.resolve()),
        "approved_rows_sha256": sha256(args.approved_rows),
        "approved_row_count": len(plan_rows),
        "reusable_existing_inactive_count": reusable,
        "blocked_row_count": blocked,
        "counts_by_plan_action": dict(sorted(counts.items())),
        "checks": checks,
        "policy": {
            "duplicate_inserts_authorized": False,
            "mapping_updates_authorized": False,
            "mapping_activation_authorized": False,
            "mapping_promotion_authorized": False,
            "canonical_geography_changes_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
            "human_review_required": True,
        },
    }

    paths = write_outputs(
        args.output_dir,
        plan_rows,
        summary,
    )
    print(
        json.dumps(
            {
                **summary,
                "summary": str(paths[0].resolve()),
                "rows": str(paths[1].resolve()),
                "csv": str(paths[2].resolve()),
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
