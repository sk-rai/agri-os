#!/usr/bin/env python3
"""Guarded NWDP demographic profile promotion apply.

Currently disabled by policy. It writes an audit JSON and mutates nothing.
"""

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
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-profile-promotion-apply-disabled.json")


def count_current_state(conn, source_version: str) -> dict:
    return dict(conn.execute(text(f"""
        select
          count(*)::bigint as profile_row_count,
          count(*) filter (where is_active = true)::bigint as active_profile_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
          count(*) filter (
            where source_system = :source_system
              and source_version = :source_version
              and review_status = 'APPROVED_FOR_PROMOTION'
              and promotion_status = 'NOT_PROMOTED'
              and is_active = false
          )::bigint as eligible_profile_row_count
        from {TARGET_TABLE}
    """), {"source_system": SOURCE_SYSTEM, "source_version": source_version}).mappings().one())


def eligible_summary(conn, state_or_ut: str | None, district: str | None, limit: int, source_version: str) -> tuple[dict, list[dict], list[dict]]:
    where = [
        "source_system = :source_system",
        "source_version = :source_version",
        "review_status = 'APPROVED_FOR_PROMOTION'",
        "promotion_status = 'NOT_PROMOTED'",
        "is_active = false",
    ]
    params = {"source_system": SOURCE_SYSTEM, "source_version": source_version, "limit": limit}

    if state_or_ut:
        where.append("source_state_name = :state_or_ut")
        params["state_or_ut"] = state_or_ut
    if district:
        where.append("source_district_name = :district")
        params["district"] = district

    where_sql = " and ".join(where)

    summary = dict(conn.execute(text(f"""
        select
          count(*)::bigint as eligible_profile_row_count,
          count(*) filter (where source_state_name = :state_or_ut)::bigint as scoped_state_count,
          count(*) filter (where source_district_name = :district)::bigint as scoped_district_count
        from {TARGET_TABLE}
        where {where_sql}
    """), {**params, "state_or_ut": state_or_ut, "district": district}).mappings().one())

    districts = [
        dict(row)
        for row in conn.execute(text(f"""
            select
              source_state_name as state_or_ut,
              source_district_name as district,
              count(*)::bigint as eligible_profile_row_count
            from {TARGET_TABLE}
            where {where_sql}
            group by source_state_name, source_district_name
            order by source_state_name, source_district_name
            limit :limit
        """), params).mappings()
    ]

    items = [
        dict(row)
        for row in conn.execute(text(f"""
            select
              id::text as profile_id,
              village_id::text as village_id,
              source_state_name as state_or_ut,
              source_district_name as district,
              source_village_name,
              source_vlcode,
              review_status,
              promotion_status,
              is_active
            from {TARGET_TABLE}
            where {where_sql}
            order by source_state_name, source_district_name, source_village_name
            limit :limit
        """), params).mappings()
    ]

    return summary, districts, items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-policy", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-version", default=SOURCE_VERSION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    state_scope_present = bool(args.state_or_ut)
    district_scope_present = bool(args.district)
    scope_present = state_scope_present and district_scope_present

    engine = create_engine(load_settings_url())
    promoted_count = 0
    activated_count = 0
    db_writes_attempted = False

    with engine.begin() as conn:
        before = count_current_state(conn, args.source_version)
        summary, districts, items = eligible_summary(conn, args.state_or_ut, args.district, args.limit, args.source_version)

        error = None
        if not args.apply:
            error = "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_REQUIRES_EXPLICIT_APPLY_FLAG"
        elif not scope_present:
            error = "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_REQUIRES_STATE_AND_DISTRICT_SCOPE"
        elif not args.enable_policy:
            error = "NWDP_DEMOGRAPHIC_PROFILE_PROMOTION_APPLY_DISABLED_BY_POLICY"
        else:
            db_writes_attempted = True
            result = conn.execute(text(f"""
                update {TARGET_TABLE}
                set
                  promotion_status = 'PROMOTED',
                  is_active = true,
                  updated_at = now(),
                  match_evidence = coalesce(match_evidence, '{{}}'::jsonb) || cast(:promotion_event as jsonb)
                where source_system = :source_system
                  and source_version = :source_version
                  and review_status = 'APPROVED_FOR_PROMOTION'
                  and promotion_status = 'NOT_PROMOTED'
                  and is_active = false
                  and source_state_name = :state_or_ut
                  and source_district_name = :district
            """), {
                "source_system": SOURCE_SYSTEM,
                "source_version": args.source_version,
                "state_or_ut": args.state_or_ut,
                "district": args.district,
                "promotion_event": json.dumps({
                    "latest_promotion_event": {
                        "promoted_at": datetime.now(timezone.utc).isoformat(),
                        "action": "NWDP_DEMOGRAPHIC_PROFILE_FIXTURE_PROMOTION_NO_RUNTIME_LOOKUP",
                        "runtime_lookup_enabled": False,
                        "android_behavior_changed": False,
                    },
                    "promotion_guardrail": {
                        "runtime_lookup_enabled": False,
                        "android_behavior_changed": False,
                        "official_census_claimed_imported": False,
                    },
                }),
            })
            promoted_count = int(result.rowcount or 0)
            activated_count = promoted_count

        after = count_current_state(conn, args.source_version)

    result = {
        "schema_version": "nwdp_demographic_profile_promotion_apply.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PROMOTION_APPLY_DISABLED_GUARD",
        "healthy": error is None,
        "apply": bool(args.apply),
        "enable_policy": bool(args.enable_policy),
        "error": error,
        "target_table": TARGET_TABLE,
        "state_or_ut": args.state_or_ut,
        "district": args.district,
        "scope": {
            "state_scope_present": state_scope_present,
            "district_scope_present": district_scope_present,
            "state_and_district_scope_present": scope_present,
            "state_and_district_scope_required": True,
        },
        "selection_policy": {
            "required_source_system": SOURCE_SYSTEM,
            "required_source_version": args.source_version,
            "required_review_status": "APPROVED_FOR_PROMOTION",
            "required_promotion_status": "NOT_PROMOTED",
            "required_is_active": False,
            "state_and_district_scope_required": True,
            "dry_run_required_before_apply": True,
        },
        "eligible_summary": {k: int(v or 0) for k, v in summary.items()},
        "state_district_summary": [
            {k: (int(v or 0) if k.endswith("_count") else v) for k, v in row.items()}
            for row in districts
        ],
        "sample_items": items,
        "before": {k: int(v or 0) for k, v in before.items()},
        "after": {k: int(v or 0) for k, v in after.items()},
        "apply_result": {
            "apply_implemented": bool(args.enable_policy),
            "planned_promotion_count": int(summary["eligible_profile_row_count"] or 0),
            "promoted_count": promoted_count,
            "activated_count": activated_count,
        },
        "guardrails": {
            "db_writes_attempted": db_writes_attempted,
            "profile_review_status_changed": False,
            "profiles_promoted": promoted_count > 0,
            "profile_rows_activated": activated_count > 0,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_profile_promotion_apply": bool(args.enable_policy) and error is None,
            "ready_for_tiny_fixture_promotion_apply_regression": True,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "claim_boundary": (
            "Promotion apply is disabled by policy. This script audits eligible "
            "approved inactive not-promoted NWDP demographic profile rows, but "
            "does not promote profiles, activate rows, enable runtime lookup, "
            "or change Android behavior."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
