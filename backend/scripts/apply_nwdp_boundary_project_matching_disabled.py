#!/usr/bin/env python3
"""Disabled apply guard for NWDP boundary project matching.

This command intentionally refuses real project-boundary writes. It wraps the
scope-aware dry-run selector and emits durable JSON/CSV audit files so a future
apply implementation can be reviewed safely before being enabled.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from app.core.config import settings
from scripts.plan_nwdp_boundary_project_matching_apply_dry_run import build_plan


SCHEMA_VERSION = "nwdp_boundary_project_matching_apply_disabled_guard.v1"


def db_url_from_settings() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def json_default(value: Any) -> str:
    return str(value)


def table_counts(conn) -> dict[str, int]:
    row = conn.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_project_matches) as project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where is_active = true) as active_project_match_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def write_selected_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "candidate_id",
        "proposed_village_id",
        "proposed_village_lgd_code",
        "state_or_ut",
        "source_district_name",
        "source_subdistrict_name",
        "source_village_name",
        "source_vlcode",
        "candidate_bucket",
        "review_status",
        "promotion_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled NWDP boundary project matching apply guard.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output-dir", default="/tmp/nwdp-boundary-project-matching-apply-disabled")
    parser.add_argument("--apply", action="store_true", help="Records an explicit apply attempt, but real apply remains disabled.")
    parser.add_argument("--enable-project-boundary-apply", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--rollback-token", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        before = table_counts(conn)

    dry_run = build_plan(args.project_id, args.limit)

    with engine.connect() as conn:
        after = table_counts(conn)

    unchanged = before == after
    disabled_reason = (
        "PROJECT_BOUNDARY_MATCHING_APPLY_DISABLED_BY_POLICY"
        if args.apply
        else "EXPLICIT_APPLY_FLAG_REQUIRED"
    )

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "DISABLED_PROJECT_BOUNDARY_MATCHING_APPLY_GUARD",
        "error": disabled_reason,
        "project_id": args.project_id,
        "apply_requested": bool(args.apply),
        "enable_project_boundary_apply_requested": bool(args.enable_project_boundary_apply),
        "rollback_token": args.rollback_token or None,
        "claim_boundary": "This guard is intentionally non-mutating. It audits the scope-aware project-boundary dry-run selection but refuses to write geography_boundary_project_matches, mutate NWDP candidates, write runtime boundary tables, enable lookup APIs, or change Android behavior.",
        "dry_run": dry_run,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": unchanged,
        "policy": {
            "real_apply_supported": False,
            "explicit_apply_flag_required": True,
            "future_enable_policy_flag_required": True,
            "rollback_token_required_before_real_apply": True,
            "dry_run_required_before_real_apply": True,
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "review_status_required": "AUTO_CANDIDATE",
            "promotion_status_required": "NOT_PROMOTED",
            "candidate_is_active_required": False,
            "project_scope_required": True,
            "android_behavior_change_allowed": False,
            "runtime_spatial_matching_allowed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "project_boundary_matches_written": False,
            "boundary_candidates_activated": False,
            "boundary_candidates_promoted": False,
            "runtime_boundary_features_written": False,
            "runtime_boundary_crosswalks_written": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_project_boundary_apply": False,
            "ready_for_project_boundary_apply_implementation_design": dry_run.get("healthy") is True,
            "ready_for_selected_boundary_runtime_promotion": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "output_files": {
            "json": str(output_dir / "project_boundary_apply_disabled_audit.json"),
            "csv": str(output_dir / "project_boundary_apply_disabled_selected_candidates.csv"),
        },
    }

    json_path = output_dir / "project_boundary_apply_disabled_audit.json"
    csv_path = output_dir / "project_boundary_apply_disabled_selected_candidates.csv"

    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    write_selected_csv(csv_path, dry_run.get("selected_candidate_samples", []))

    print(json.dumps(audit, indent=2, sort_keys=True, default=json_default))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
