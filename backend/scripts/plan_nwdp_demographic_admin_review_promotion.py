#!/usr/bin/env python3
"""Read-only plan for NWDP demographic admin review/promotion workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402

TARGET_TABLE = "geography_village_demographic_profiles"
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-admin-review-promotion-plan.json")


def i(value):
    return int(value or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    where = ["source_system = :source_system", "source_version = :source_version"]
    params = {"source_system": SOURCE_SYSTEM, "source_version": SOURCE_VERSION, "limit": args.limit}

    if args.state_or_ut:
        where.append("source_state_name = :state_or_ut")
        params["state_or_ut"] = args.state_or_ut
    if args.district:
        where.append("source_district_name = :district")
        params["district"] = args.district

    where_sql = " and ".join(where)
    engine = create_engine(load_settings_url())

    with engine.connect() as conn:
        summary = conn.execute(text(f"""
            select
              count(*)::bigint as profile_row_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where review_status = 'REJECTED')::bigint as rejected_count,
              count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
              count(*) filter (
                where is_active = false
                  and promotion_status = 'NOT_PROMOTED'
                  and review_status = 'AUTO_CANDIDATE'
              )::bigint as review_queue_candidate_count,
              count(*) filter (
                where is_active = false
                  and promotion_status = 'NOT_PROMOTED'
                  and review_status = 'APPROVED_FOR_PROMOTION'
              )::bigint as promotion_queue_candidate_count
            from {TARGET_TABLE}
            where {where_sql}
        """), params).mappings().one()

        state_district = conn.execute(text(f"""
            select
              source_state_name as state_or_ut,
              source_district_name as district,
              count(*)::bigint as profile_row_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
              count(*) filter (where is_active = true)::bigint as active_profile_row_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
            from {TARGET_TABLE}
            where {where_sql}
            group by source_state_name, source_district_name
            order by source_state_name, source_district_name
            limit :limit
        """), params).mappings().all()

    summary = {k: i(v) for k, v in summary.items()}
    state_district = [
        {k: (i(v) if k.endswith("_count") else v) for k, v in row.items()}
        for row in state_district
    ]

    result = {
        "schema_version": "nwdp_demographic_admin_review_promotion_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": summary["profile_row_count"] > 0,
        "mode": "READ_ONLY_ADMIN_REVIEW_PROMOTION_PLAN",
        "target_table": TARGET_TABLE,
        "filters": {"state_or_ut": args.state_or_ut, "district": args.district, "limit": args.limit},
        "summary": summary,
        "approved_vs_manual_review": {
            "approved_for_promotion_count": summary["approved_for_promotion_count"],
            "manual_review_count": summary["manual_review_count"],
        },
        "state_district_summary": state_district,
        "review_policy": {
            "admin_should_analyze_by_state_district": True,
            "bulk_review_without_state_or_district_filter_allowed": False,
            "allowed_future_review_statuses": [
                "MANUAL_REVIEW",
                "APPROVED_FOR_PROMOTION",
                "REJECTED",
                "BLOCKED",
            ],
            "review_notes_required": True,
            "review_update_requires_separate_endpoint": True,
        },
        "promotion_policy": {
            "promotion_supported_by_this_plan": False,
            "promotion_requires_separate_dry_run": True,
            "promotion_requires_separate_apply_checkpoint": True,
            "required_review_status_for_future_promotion": "APPROVED_FOR_PROMOTION",
            "required_current_promotion_status": "NOT_PROMOTED",
            "required_current_is_active": False,
        },
        "recommended_next_endpoint_shape": {
            "review_update": "PATCH /api/v1/master-data/geography/nwdp-demographic-profiles/{profile_id}/review",
            "promotion_dry_run": "GET /api/v1/master-data/geography/nwdp-demographic-profiles/promotion/dry-run?state_or_ut=<STATE>&district=<DISTRICT>",
        },
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
            "ready_for_admin_review_endpoint_design": summary["review_queue_candidate_count"] > 0,
            "ready_for_admin_review_update_apply": False,
            "ready_for_promotion_dry_run_design": True,
            "ready_for_profile_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }

    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "healthy": result["healthy"],
        "profile_row_count": summary["profile_row_count"],
        "review_queue_candidate_count": summary["review_queue_candidate_count"],
        "promotion_queue_candidate_count": summary["promotion_queue_candidate_count"],
        "approved_vs_manual_review": result["approved_vs_manual_review"],
    }, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
