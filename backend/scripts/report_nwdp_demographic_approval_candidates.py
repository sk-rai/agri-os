#!/usr/bin/env python3
"""Read-only NWDP demographic approval candidate report for a state/district."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

TARGET_TABLE = "geography_village_demographic_profiles"
DEFAULT_OUT_DIR = ROOT / "data/staged/core_stack/nwdp_demographic_approval_candidates"


def i(value):
    return int(value or 0)


def f(value):
    return float(value or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut", required=True)
    parser.add_argument("--district", required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    params = {
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
        "state_or_ut": args.state_or_ut,
        "district": args.district,
        "limit": args.limit,
    }

    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        summary = dict(conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (
                where review_status = 'AUTO_CANDIDATE'
                  and promotion_status = 'NOT_PROMOTED'
                  and is_active = false
              )::bigint as approval_candidate_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where review_status = 'REJECTED')::bigint as rejected_count,
              count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
              count(*) filter (where coalesce(total_population, 0) > 0)::bigint as population_nonzero_count,
              count(*) filter (where coalesce(total_households, 0) > 0)::bigint as household_nonzero_count
            from {TARGET_TABLE}
            where source_system = :source_system
              and source_version = :source_version
              and source_state_name = :state_or_ut
              and source_district_name = :district
        """), params).mappings().one())

        items = [
            dict(row)
            for row in conn.execute(text(f"""
                select
                  id::text as profile_id,
                  village_id::text as village_id,
                  source_state_name as state_or_ut,
                  source_district_name as district,
                  source_subdistrict_name,
                  source_village_name,
                  source_vlcode,
                  total_population,
                  total_households,
                  rural_urban,
                  review_status,
                  promotion_status,
                  is_active
                from {TARGET_TABLE}
                where source_system = :source_system
                  and source_version = :source_version
                  and source_state_name = :state_or_ut
                  and source_district_name = :district
                  and review_status = 'AUTO_CANDIDATE'
                  and promotion_status = 'NOT_PROMOTED'
                  and is_active = false
                order by
                  coalesce(total_population, 0) desc,
                  source_subdistrict_name nulls last,
                  source_village_name nulls last
                limit :limit
            """), params).mappings()
        ]

    summary = {key: i(value) for key, value in summary.items()}
    profile_count = summary["profile_row_count"]
    approval_count = summary["approval_candidate_count"]

    result = {
        "schema_version": "nwdp_demographic_approval_candidates_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": profile_count > 0,
        "mode": "READ_ONLY_APPROVAL_CANDIDATE_REPORT",
        "target_table": TARGET_TABLE,
        "filters": {
            "state_or_ut": args.state_or_ut,
            "district": args.district,
            "limit": args.limit,
        },
        "summary": {
            **summary,
            "approval_candidate_ratio": f(approval_count / profile_count) if profile_count else 0.0,
            "population_nonzero_ratio": f(summary["population_nonzero_count"] / profile_count) if profile_count else 0.0,
            "household_nonzero_ratio": f(summary["household_nonzero_count"] / profile_count) if profile_count else 0.0,
        },
        "approval_policy": {
            "approval_candidates_require_review_status": "AUTO_CANDIDATE",
            "approval_candidates_require_promotion_status": "NOT_PROMOTED",
            "approval_candidates_require_is_active": False,
            "state_and_district_scope_required": True,
            "review_notes_required_before_apply": True,
            "bulk_approval_apply_supported_by_this_report": False,
        },
        "items": items,
        "claim_boundary": (
            "This report is read-only. It identifies inactive auto-candidate "
            "NWDP demographic profiles for possible admin approval in one "
            "state/district, but does not change review status, promote profiles, "
            "activate rows, enable runtime lookup, or change Android behavior."
        ),
        "guardrails": {
            "db_writes_attempted": False,
            "profile_review_status_changed": False,
            "profiles_promoted": False,
            "profile_rows_activated": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_scoped_admin_approval_plan": approval_count > 0,
            "ready_for_bulk_approval_apply": False,
            "ready_for_promotion_dry_run": False,
            "ready_for_profile_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe_state = args.state_or_ut.lower().replace(" ", "_").replace("&", "and")
    safe_district = args.district.lower().replace(" ", "_").replace("&", "and")
    json_path = args.output_dir / f"{safe_state}__{safe_district}__approval_candidates.json"
    csv_path = args.output_dir / f"{safe_state}__{safe_district}__approval_candidates.csv"

    result["output_files"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = [
        "profile_id",
        "village_id",
        "state_or_ut",
        "district",
        "source_subdistrict_name",
        "source_village_name",
        "source_vlcode",
        "total_population",
        "total_households",
        "rural_urban",
        "review_status",
        "promotion_status",
        "is_active",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)

    print(json.dumps({
        "json": str(json_path),
        "csv": str(csv_path),
        "healthy": result["healthy"],
        "summary": result["summary"],
        "sample_count": len(items),
    }, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
