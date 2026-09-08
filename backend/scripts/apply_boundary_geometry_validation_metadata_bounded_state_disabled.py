#!/usr/bin/env python3
"""Disabled guard for bounded state validation metadata apply."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402

SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_bounded_state_apply_disabled.v1"
)
EVENT_TABLE = "geography_boundary_validation_metadata_events"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-slug", default="")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--plan-checksum", default="")
    parser.add_argument("--rollback-token", default="")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--enable-bounded-validation-metadata-write",
        action="store_true",
    )
    parser.add_argument("--dry-run-reviewed", action="store_true")
    parser.add_argument("--event-schema-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    return parser.parse_args()


def counts() -> dict[str, int]:
    with engine.connect() as connection:
        row = connection.execute(text(f"""
            select
              (select count(*) from geography_boundary_source_features)
                as source_feature_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'NOT_VALIDATED')
                as not_validated_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'VALIDATED')
                as validated_rows,
              (select count(*) from geography_boundary_source_features
               where eligible_for_runtime_after_promotion = true)
                as runtime_eligible_source_rows,
              (select count(*) from geography_boundary_crosswalk_candidates)
                as candidate_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where is_active = true)
                as active_candidate_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where promotion_status = 'PROMOTED')
                as promoted_candidate_rows,
              (select count(*) from geography_boundary_runtime_sets)
                as runtime_set_rows,
              (select count(*) from geography_boundary_runtime_features)
                as runtime_feature_rows,
              (select count(*) from geography_boundary_runtime_crosswalks)
                as runtime_crosswalk_rows,
              (select count(*) from {EVENT_TABLE})
                as validation_event_rows,
              (select count(*) from {EVENT_TABLE}
               where is_active = true)
                as active_validation_event_rows
        """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def canonical_checksum(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def recompute_plan_checksum(plan: dict[str, Any]) -> str:
    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}
    payload = {
        "schema_version": plan.get("schema_version"),
        "state_slug": scope.get("state_slug"),
        "state_or_ut": scope.get("state_or_ut"),
        "import_batch_id": scope.get("import_batch_id"),
        "source_sha256": source.get("sha256"),
        "geometry_hash_algorithm":
            source.get("geometry_hash_algorithm"),
        "cursor_after_index": scope.get("cursor_after_index"),
        "limit": scope.get("limit"),
        "rows": plan.get("rows") or [],
    }
    return canonical_checksum(payload)


def load_plan(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "PLAN_JSON_REQUIRED"
    if not path.is_file():
        return None, "PLAN_JSON_NOT_FOUND"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "PLAN_JSON_INVALID"
    if not isinstance(value, dict):
        return None, "PLAN_JSON_INVALID"
    return value, None


def plan_error(
    args: argparse.Namespace,
    plan: dict[str, Any] | None,
    load_error: str | None,
) -> str:
    if not args.apply:
        return "EXPLICIT_APPLY_FLAG_REQUIRED"
    if not args.state_slug or not args.state_or_ut:
        return "STATE_SCOPE_REQUIRED"
    if load_error:
        return load_error
    if not args.source_sha256:
        return "SOURCE_CHECKSUM_REQUIRED"
    if not args.plan_checksum:
        return "PLAN_CHECKSUM_REQUIRED"
    if not args.enable_bounded_validation_metadata_write:
        return "BOUNDED_METADATA_WRITE_POLICY_FLAG_REQUIRED"
    if not args.rollback_token:
        return "ROLLBACK_OR_SUPERSESSION_TOKEN_REQUIRED"
    if not args.dry_run_reviewed:
        return "DRY_RUN_REVIEW_REQUIRED"
    if not args.event_schema_reviewed:
        return "EVENT_SCHEMA_REVIEW_REQUIRED"
    if not args.admin_confirmation:
        return "ADMIN_CONFIRMATION_REQUIRED"

    assert plan is not None
    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}
    rows = plan.get("rows") or []

    if plan.get("healthy") is not True:
        return "PLAN_NOT_HEALTHY"
    if (
        plan.get("schema_version")
        != "boundary_geometry_validation_metadata_bounded_state_plan.v1"
    ):
        return "PLAN_SCHEMA_VERSION_MISMATCH"
    if scope.get("state_slug") != args.state_slug:
        return "PLAN_STATE_SLUG_MISMATCH"
    if str(scope.get("state_or_ut", "")).lower() != args.state_or_ut.lower():
        return "PLAN_STATE_NAME_MISMATCH"
    if source.get("sha256") != args.source_sha256:
        return "PLAN_SOURCE_CHECKSUM_MISMATCH"
    if batch.get("plan_checksum") != args.plan_checksum:
        return "PLAN_CHECKSUM_MISMATCH"
    if recompute_plan_checksum(plan) != args.plan_checksum:
        return "PLAN_CONTENT_CHECKSUM_MISMATCH"
    if not rows:
        return "PLAN_HAS_NO_ROWS"
    if len(rows) > 500 or batch.get("selected_row_count") != len(rows):
        return "PLAN_ROW_LIMIT_OR_ACCOUNTING_INVALID"
    if not all(
        row.get("classification") == "VALIDATED_NO_REPAIR"
        and row.get("current_geometry_validation_status")
        == "NOT_VALIDATED"
        and row.get("planned_geometry_validation_status") == "VALIDATED"
        and row.get("runtime_eligibility_change_planned") is False
        for row in rows
    ):
        return "PLAN_CONTAINS_INELIGIBLE_ROWS"

    if not inspect(engine).has_table(EVENT_TABLE):
        return "VALIDATION_EVENT_SCHEMA_REQUIRED"

    return "BOUNDED_STATE_VALIDATION_METADATA_APPLY_DISABLED_BY_POLICY"


def guardrails() -> dict[str, bool]:
    return {
        "db_writes_attempted": False,
        "source_files_changed": False,
        "source_features_changed": False,
        "validation_metadata_written": False,
        "validation_events_written": False,
        "geometry_repair_persisted": False,
        "source_runtime_eligibility_changed": False,
        "boundary_candidates_promoted": False,
        "boundary_candidates_activated": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "lgd_geography_overwritten": False,
        "android_behavior_changed": False,
    }


def write_outputs(
    output_dir: Path,
    audit: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = (
        output_dir
        / "bounded_validation_metadata_apply_disabled_audit.json"
    )
    csv_path = (
        output_dir
        / "bounded_validation_metadata_apply_disabled_rows.csv"
    )
    audit["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
    }
    json_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    fields = [
        "sequence",
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "current_geometry_validation_status",
        "planned_geometry_validation_status",
        "classification",
        "source_geometry_hash",
        "runtime_eligibility_change_planned",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = arguments()
    before = counts()
    plan, load_error = load_plan(args.plan_json)
    error = plan_error(args, plan, load_error)
    after = counts()
    rows = list((plan or {}).get("rows") or [])

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": (
            "DISABLED_BOUNDED_STATE_BOUNDARY_VALIDATION_METADATA_APPLY"
        ),
        "error": error,
        "scope": {
            "state_slug": args.state_slug or None,
            "state_or_ut": args.state_or_ut or None,
        },
        "source_sha256": args.source_sha256 or None,
        "plan_checksum": args.plan_checksum or None,
        "plan_json": str(args.plan_json) if args.plan_json else None,
        "rollback_token": args.rollback_token or None,
        "confirmations": {
            "explicit_apply_requested": args.apply,
            "bounded_metadata_write_policy_enabled":
                args.enable_bounded_validation_metadata_write,
            "dry_run_reviewed": args.dry_run_reviewed,
            "event_schema_reviewed": args.event_schema_reviewed,
            "admin_confirmation": args.admin_confirmation,
        },
        "plan_summary": {
            "schema_version": (plan or {}).get("schema_version"),
            "scope": (plan or {}).get("scope"),
            "source": (plan or {}).get("source"),
            "batch": (plan or {}).get("batch"),
            "state_classification":
                (plan or {}).get("state_classification"),
        },
        "policy": {
            "real_apply_supported": False,
            "maximum_row_count": 500,
            "validated_without_repair_only": True,
            "target_table": "geography_boundary_source_features",
            "event_table": EVENT_TABLE,
            "geometry_repair_allowed": False,
            "runtime_eligibility_change_allowed": False,
            "candidate_write_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "guardrails": guardrails(),
    }

    write_outputs(args.output_dir, audit, rows)
    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
