#!/usr/bin/env python3
"""Disabled apply guard for NWDP boundary validation metadata.

This command records a bounded validation-metadata plan and its confirmations,
but deliberately refuses every real database or runtime mutation.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402


SCHEMA_VERSION = "boundary_geometry_validation_metadata_apply_disabled_guard.v1"
MODE = "DISABLED_BOUNDARY_GEOMETRY_VALIDATION_METADATA_APPLY"

GUARDRAILS = {
    "db_writes_attempted": False,
    "source_files_changed": False,
    "source_features_changed": False,
    "geometry_repair_persisted": False,
    "geometry_validation_status_changed": False,
    "source_runtime_eligibility_changed": False,
    "boundary_candidates_promoted": False,
    "boundary_candidates_activated": False,
    "runtime_tables_written": False,
    "runtime_lookup_enabled": False,
    "lgd_geography_overwritten": False,
    "android_behavior_changed": False,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and reject boundary validation metadata apply."
    )
    parser.add_argument("--state-slug", default="")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--output-dir",
        default="/tmp/boundary-validation-metadata-apply-disabled",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--enable-validation-metadata-write",
        action="store_true",
    )
    parser.add_argument("--dry-run-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    return parser.parse_args()


def table_counts() -> dict[str, int]:
    query = text(
        """
        select
          (
            select count(*)::bigint
            from geography_boundary_source_features
          )::bigint as source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_source_features
            where geometry_validation_status = 'VALIDATED'
          )::bigint as validated_source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_source_features
            where geometry_validation_status = 'NOT_VALIDATED'
          )::bigint as not_validated_source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_source_features
            where geometry_validation_status = 'REPAIR_REQUIRED'
          )::bigint as repair_required_source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_source_features
            where geometry_validation_status = 'VALIDATION_REVIEW'
          )::bigint as validation_review_source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_source_features
            where coalesce(eligible_for_runtime_after_promotion, false) = true
          )::bigint as runtime_eligible_source_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
          )::bigint as boundary_candidate_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where coalesce(is_active, false) = true
          )::bigint as active_boundary_candidate_rows,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          )::bigint as promoted_boundary_candidate_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_sets
          )::bigint as runtime_set_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
          )::bigint as runtime_feature_rows,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
          )::bigint as runtime_crosswalk_rows
        """
    )

    with engine.connect() as connection:
        row = connection.execute(query).mappings().one()

    return {key: int(value or 0) for key, value in row.items()}


def run_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.state_slug or not args.state_or_ut:
        return {
            "healthy": False,
            "error": "STATE_SCOPE_REQUIRED_FOR_DRY_RUN",
            "summary": {},
            "rows": [],
        }

    dry_run_dir = Path(args.output_dir) / "dry_run"
    command = [
        sys.executable,
        str(
            ROOT
            / "backend/scripts/"
            "plan_boundary_geometry_validation_metadata_dry_run.py"
        ),
        "--state-slug",
        args.state_slug,
        "--state-or-ut",
        args.state_or_ut,
        "--limit",
        str(args.limit),
        "--output-dir",
        str(dry_run_dir),
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    candidates = sorted(dry_run_dir.glob("*.json"))
    if not candidates:
        return {
            "healthy": False,
            "error": "DRY_RUN_OUTPUT_NOT_FOUND",
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "summary": {},
            "rows": [],
        }

    data = json.loads(candidates[0].read_text(encoding="utf-8"))
    data["returncode"] = completed.returncode
    return data


def choose_error(
    args: argparse.Namespace,
    dry_run: dict[str, Any],
) -> str:
    if not args.apply:
        return "EXPLICIT_APPLY_FLAG_REQUIRED"

    if not args.state_slug or not args.state_or_ut:
        return "STATE_SCOPE_REQUIRED"

    if args.limit < 1 or args.limit > 500:
        return "BOUNDED_ROW_LIMIT_REQUIRED"

    if not args.enable_validation_metadata_write:
        return "ENABLE_VALIDATION_METADATA_WRITE_POLICY_FLAG_REQUIRED"

    actual_checksum = str(dry_run.get("source", {}).get("sha256") or "")

    if not args.source_sha256:
        return "SOURCE_CHECKSUM_CONFIRMATION_REQUIRED"

    if not actual_checksum or args.source_sha256.lower() != actual_checksum.lower():
        return "SOURCE_CHECKSUM_MISMATCH"

    if not args.rollback_token:
        return "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED"

    if not args.dry_run_reviewed:
        return "DRY_RUN_REVIEW_REQUIRED"

    if not args.admin_confirmation:
        return "ADMIN_CONFIRMATION_REQUIRED"

    if not dry_run.get("healthy"):
        return "VALIDATION_METADATA_DRY_RUN_NOT_HEALTHY"

    return "BOUNDARY_VALIDATION_METADATA_APPLY_DISABLED_BY_POLICY"


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = (
        output_dir
        / "boundary_validation_metadata_apply_disabled_audit.json"
    )
    csv_path = (
        output_dir
        / "boundary_validation_metadata_apply_disabled_rows.csv"
    )

    payload["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
    }

    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    rows = payload.get("dry_run", {}).get("rows", [])
    fieldnames = [
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "current_geometry_validation_status",
        "planned_geometry_validation_status",
        "source_geometry_hash",
        "classification",
        "metadata_change_planned",
        "runtime_eligibility_change_planned",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    return payload["output_files"]


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    before = table_counts()
    dry_run = run_dry_run(args)
    error = choose_error(args, dry_run)
    after = table_counts()

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": MODE,
        "error": error,
        "filters": {
            "state_slug": args.state_slug or None,
            "state_or_ut": args.state_or_ut or None,
            "limit": args.limit,
        },
        "confirmations": {
            "explicit_apply_requested": args.apply,
            "validation_metadata_write_policy_enabled": (
                args.enable_validation_metadata_write
            ),
            "source_sha256_supplied": bool(args.source_sha256),
            "dry_run_reviewed": args.dry_run_reviewed,
            "admin_confirmation": args.admin_confirmation,
            "rollback_token_supplied": bool(args.rollback_token),
        },
        "source_sha256": args.source_sha256 or None,
        "rollback_token": args.rollback_token or None,
        "policy": {
            "real_apply_supported": False,
            "state_scope_required": True,
            "maximum_row_limit": 500,
            "source_checksum_required": True,
            "dry_run_review_required": True,
            "rollback_or_supersession_plan_required": True,
            "admin_confirmation_required": True,
            "allowed_target_table": (
                "geography_boundary_source_features"
            ),
            "allowed_fields_if_future_apply_is_approved": [
                "source_geometry_hash",
                "source_bbox",
                "transformed_bbox",
                "transformed_centroid",
                "geometry_validation_status",
                "metadata",
            ],
            "runtime_eligibility_changes_allowed": False,
            "geometry_repair_allowed": False,
            "runtime_promotion_allowed": False,
        },
        "dry_run": dry_run,
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "guardrails": dict(GUARDRAILS),
    }

    write_outputs(output_dir, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
