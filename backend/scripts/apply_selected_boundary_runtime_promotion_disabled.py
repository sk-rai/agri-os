#!/usr/bin/env python3
"""Disabled apply guard for selected NWDP boundary runtime promotion.

This command intentionally refuses real runtime promotion. It wraps the
selected boundary runtime promotion readiness report and writes durable JSON/CSV
audit files so a future apply implementation can be reviewed safely.
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from app.core.config import settings


SCHEMA_VERSION = "selected_boundary_runtime_promotion_apply_disabled_guard.v1"


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
          (select count(*)::bigint from geography_boundary_runtime_sets) as runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_sets where is_active = true) as active_runtime_set_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_features where is_active = true) as active_runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true) as active_runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_promotion_events) as runtime_promotion_event_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def write_candidate_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "state_or_ut",
        "source_district_name",
        "source_subdistrict_name",
        "source_village_name",
        "source_vlcode",
        "candidate_id",
        "proposed_village_id",
        "proposed_village_lgd_code",
        "candidate_bucket",
        "review_status",
        "promotion_status",
        "confidence",
        "geometry_validation_status",
        "eligible_for_runtime_after_promotion",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_readiness(output_dir: Path, state_or_ut: str, district: str, limit: int) -> dict[str, Any]:
    readiness_dir = output_dir / "readiness_source"
    readiness_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "report_selected_boundary_runtime_promotion_readiness.py"),
        "--output-dir",
        str(readiness_dir),
        "--limit",
        str(limit),
    ]
    if state_or_ut:
        cmd.extend(["--state-or-ut", state_or_ut])
    if district:
        cmd.extend(["--district", district])

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT.parent),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )

    report_path = readiness_dir / "selected_boundary_runtime_promotion_readiness.json"
    if not report_path.exists():
        return {
            "healthy": False,
            "error": "READINESS_REPORT_DID_NOT_WRITE_JSON",
            "returncode": proc.returncode,
            "output": proc.stdout[-4000:],
        }

    data = json.loads(report_path.read_text(encoding="utf-8"))
    data["_readiness_report_returncode"] = proc.returncode
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled selected boundary runtime promotion apply guard.")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output-dir", default="/tmp/selected-boundary-runtime-promotion-apply-disabled")
    parser.add_argument("--apply", action="store_true", help="Records an explicit apply attempt, but real apply remains disabled.")
    parser.add_argument("--enable-selected-runtime-promotion", action="store_true", help="Reserved future policy flag; currently still disabled.")
    parser.add_argument("--dry-run-confirmed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state_or_ut = args.state_or_ut.strip()
    district = args.district.strip()

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        before = table_counts(conn)

    readiness = None
    if state_or_ut or district:
        readiness = run_readiness(output_dir, state_or_ut, district, args.limit)
    else:
        readiness = {
            "healthy": False,
            "error": "STATE_OR_DISTRICT_SCOPE_REQUIRED_BEFORE_READINESS_SELECTION",
            "summary": {},
            "readiness": {},
            "selected_candidate_samples": [],
        }

    with engine.connect() as conn:
        after = table_counts(conn)

    if not args.apply:
        error = "EXPLICIT_APPLY_FLAG_REQUIRED"
    elif not (state_or_ut or district):
        error = "STATE_OR_DISTRICT_SCOPE_REQUIRED"
    elif not args.rollback_token.strip():
        error = "ROLLBACK_OR_SUPERSESSION_PLAN_REQUIRED"
    elif not args.dry_run_confirmed:
        error = "DRY_RUN_CONFIRMATION_REQUIRED"
    elif not args.admin_confirmation:
        error = "ADMIN_CONFIRMATION_REQUIRED"
    else:
        error = "SELECTED_BOUNDARY_RUNTIME_PROMOTION_APPLY_DISABLED_BY_POLICY"

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "DISABLED_SELECTED_BOUNDARY_RUNTIME_PROMOTION_APPLY_GUARD",
        "error": error,
        "filters": {
            "state_or_ut": state_or_ut or None,
            "district": district or None,
            "limit": args.limit,
        },
        "apply_requested": bool(args.apply),
        "enable_selected_runtime_promotion_requested": bool(args.enable_selected_runtime_promotion),
        "dry_run_confirmed": bool(args.dry_run_confirmed),
        "admin_confirmation": bool(args.admin_confirmation),
        "rollback_token": args.rollback_token.strip() or None,
        "claim_boundary": "This guard is intentionally non-mutating. It audits selected NWDP boundary runtime promotion readiness but refuses to write runtime tables, promote or activate candidates, enable lookup APIs, overwrite LGD geography, or change Android behavior.",
        "readiness_report": readiness,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "policy": {
            "real_apply_supported": False,
            "explicit_apply_flag_required": True,
            "future_enable_policy_flag_required": True,
            "state_or_district_scope_required_before_real_apply": True,
            "rollback_or_supersession_plan_required_before_real_apply": True,
            "dry_run_required_before_real_apply": True,
            "admin_confirmation_required_before_real_apply": True,
            "candidate_bucket_required": "DIRECT_VLCODE_MATCH",
            "review_status_required": "AUTO_CANDIDATE",
            "promotion_status_required": "NOT_PROMOTED",
            "candidate_is_active_required": False,
            "requires_runtime_eligible_source_feature": True,
            "requires_valid_geometry": True,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_sets_written": False,
            "runtime_features_written": False,
            "runtime_crosswalks_written": False,
            "runtime_promotion_events_written": False,
            "runtime_lookup_enabled": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_real_apply_implementation_design": bool((readiness or {}).get("healthy")),
        },
        "output_files": {
            "json": str(output_dir / "selected_boundary_runtime_promotion_apply_disabled_audit.json"),
            "csv": str(output_dir / "selected_boundary_runtime_promotion_apply_disabled_candidates.csv"),
        },
    }

    json_path = output_dir / "selected_boundary_runtime_promotion_apply_disabled_audit.json"
    csv_path = output_dir / "selected_boundary_runtime_promotion_apply_disabled_candidates.csv"

    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    write_candidate_csv(csv_path, (readiness or {}).get("selected_candidate_samples", []))

    print(json.dumps(audit, indent=2, sort_keys=True, default=json_default))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
