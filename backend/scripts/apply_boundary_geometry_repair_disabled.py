#!/usr/bin/env python3
"""Disabled apply guard for NWDP boundary geometry repair/runtime eligibility.

This command intentionally refuses real geometry repair or runtime eligibility
changes. It wraps the boundary geometry repair classification report and writes
durable JSON/CSV audit files without changing source features, validation
status, runtime eligibility, candidates, runtime tables, lookup, LGD, or Android.
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

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402


SCHEMA_VERSION = "boundary_geometry_repair_apply_disabled_guard.v1"


def table_counts(conn) -> dict[str, int]:
    row = conn.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_source_features) as source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where eligible_for_runtime_after_promotion = true) as runtime_eligible_source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where geometry_validation_status in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')) as valid_geometry_source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where geometry_validation_status not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS') or geometry_validation_status is null) as invalid_or_unknown_geometry_source_feature_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_sets) as runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_promotion_events) as runtime_promotion_event_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def run_classification(output_dir: Path, state_or_ut: str, district: str, limit: int) -> dict[str, Any]:
    classification_dir = output_dir / "classification_source"
    classification_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "backend/scripts/report_boundary_geometry_repair_classification.py"),
        "--output-dir",
        str(classification_dir),
        "--limit",
        str(limit),
    ]
    if state_or_ut:
        cmd.extend(["--state-or-ut", state_or_ut])
    if district:
        cmd.extend(["--district", district])

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=240,
    )

    report_path = classification_dir / "boundary_geometry_repair_classification.json"
    if not report_path.exists():
        return {
            "healthy": False,
            "error": "BOUNDARY_GEOMETRY_REPAIR_CLASSIFICATION_DID_NOT_WRITE_JSON",
            "returncode": proc.returncode,
            "output": proc.stdout[-4000:],
        }

    data = json.loads(report_path.read_text(encoding="utf-8"))
    data["_classification_returncode"] = proc.returncode
    return data


def write_classification_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "repair_classification",
        "recommended_action",
        "candidate_count",
        "direct_vlcode_match_count",
        "auto_candidate_count",
        "manual_review_count",
        "blocked_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled NWDP boundary geometry repair apply guard.")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output-dir", default="/tmp/boundary-geometry-repair-apply-disabled")
    parser.add_argument("--apply", action="store_true", help="Records an explicit repair attempt, but real repair remains disabled.")
    parser.add_argument("--enable-geometry-repair", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--enable-runtime-eligibility-update", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--classification-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state_or_ut = args.state_or_ut.strip()
    district = args.district.strip()

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        before = table_counts(conn)

    classification = run_classification(output_dir, state_or_ut, district, args.limit)

    with engine.connect() as conn:
        after = table_counts(conn)

    if not args.apply:
        error = "EXPLICIT_APPLY_FLAG_REQUIRED"
    elif not state_or_ut and not district:
        error = "STATE_OR_DISTRICT_SCOPE_REQUIRED"
    elif not args.enable_geometry_repair:
        error = "ENABLE_GEOMETRY_REPAIR_POLICY_FLAG_REQUIRED"
    elif not args.enable_runtime_eligibility_update:
        error = "ENABLE_RUNTIME_ELIGIBILITY_UPDATE_POLICY_FLAG_REQUIRED"
    elif not args.rollback_token.strip():
        error = "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED"
    elif not args.classification_reviewed:
        error = "CLASSIFICATION_REVIEW_REQUIRED"
    elif not args.admin_confirmation:
        error = "ADMIN_CONFIRMATION_REQUIRED"
    else:
        error = "BOUNDARY_GEOMETRY_REPAIR_APPLY_DISABLED_BY_POLICY"

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "DISABLED_BOUNDARY_GEOMETRY_REPAIR_APPLY_GUARD",
        "error": error,
        "filters": {
            "state_or_ut": state_or_ut or None,
            "district": district or None,
            "limit": args.limit,
        },
        "apply_requested": bool(args.apply),
        "enable_geometry_repair_requested": bool(args.enable_geometry_repair),
        "enable_runtime_eligibility_update_requested": bool(args.enable_runtime_eligibility_update),
        "classification_reviewed": bool(args.classification_reviewed),
        "admin_confirmation": bool(args.admin_confirmation),
        "rollback_token": args.rollback_token.strip() or None,
        "claim_boundary": "This guard is intentionally non-mutating. It audits boundary geometry repair classification but refuses to repair geometry, change validation status, change runtime eligibility, mutate source features, promote/activate candidates, write runtime tables, enable lookup, overwrite LGD, or change Android behavior.",
        "classification_report": classification,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "policy": {
            "real_apply_supported": False,
            "explicit_apply_flag_required": True,
            "state_or_district_scope_required": True,
            "future_geometry_repair_policy_flag_required": True,
            "future_runtime_eligibility_policy_flag_required": True,
            "rollback_or_supersession_plan_required_before_real_apply": True,
            "classification_review_required_before_real_apply": True,
            "admin_confirmation_required_before_real_apply": True,
            "geometry_repair_write_allowed": False,
            "geometry_validation_status_write_allowed": False,
            "source_runtime_eligibility_write_allowed": False,
            "source_feature_write_allowed": False,
            "candidate_promotion_allowed": False,
            "candidate_activation_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "geometry_repair_attempted": False,
            "geometry_validation_status_changed": False,
            "source_runtime_eligibility_changed": False,
            "source_features_changed": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_admin_repair_planning": bool(classification.get("readiness", {}).get("ready_for_admin_repair_planning")),
            "ready_for_geometry_validation_pipeline_design": bool(classification.get("readiness", {}).get("ready_for_geometry_validation_pipeline_design")),
            "ready_for_runtime_eligibility_review": bool(classification.get("readiness", {}).get("ready_for_runtime_eligibility_review")),
            "ready_for_boundary_geometry_repair_apply": False,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "output_files": {
            "json": str(output_dir / "boundary_geometry_repair_apply_disabled_audit.json"),
            "csv": str(output_dir / "boundary_geometry_repair_apply_disabled_classifications.csv"),
        },
    }

    json_path = output_dir / "boundary_geometry_repair_apply_disabled_audit.json"
    csv_path = output_dir / "boundary_geometry_repair_apply_disabled_classifications.csv"

    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_classification_csv(csv_path, classification.get("classification_rows", []))

    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
