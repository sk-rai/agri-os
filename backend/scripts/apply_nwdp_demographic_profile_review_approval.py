#!/usr/bin/env python3
"""Guarded NWDP demographic profile review approval apply.

Disabled by policy by default. With --enable-policy, it can move scoped
AUTO_CANDIDATE fixture/test rows to APPROVED_FOR_PROMOTION for regression
validation. It never promotes profiles, activates rows, enables runtime lookup,
or changes Android behavior.
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
DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-profile-review-approval-apply-disabled.json")


def i(value) -> int:
    return int(value or 0)


def current_counts(conn) -> dict:
    return dict(conn.execute(text(f"""
        select
          count(*)::bigint as profile_row_count,
          count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
          count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
          count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
          count(*) filter (where review_status = 'REJECTED')::bigint as rejected_count,
          count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
          count(*) filter (where is_active = true)::bigint as active_profile_row_count,
          count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count
        from {TARGET_TABLE}
        where source_system = :source_system
          and source_version = :source_version
    """), {
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
    }).mappings().one())


def scoped_candidate_report(conn, state_or_ut: str | None, district: str | None, max_rows: int, limit: int) -> tuple[dict, list[dict]]:
    where = [
        "source_system = :source_system",
        "source_version = :source_version",
        "review_status = 'AUTO_CANDIDATE'",
        "promotion_status = 'NOT_PROMOTED'",
        "is_active = false",
    ]
    params = {
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
        "state_or_ut": state_or_ut,
        "district": district,
        "limit": limit,
    }

    if state_or_ut:
        where.append("source_state_name = :state_or_ut")
    if district:
        where.append("source_district_name = :district")

    where_sql = " and ".join(where)

    summary = dict(conn.execute(text(f"""
        select
          count(*)::bigint as candidate_profile_row_count,
          count(*) filter (where coalesce(total_population, 0) > 0)::bigint as population_nonzero_count,
          count(*) filter (where coalesce(total_households, 0) > 0)::bigint as household_nonzero_count,
          count(*) filter (where source_state_name = :state_or_ut)::bigint as scoped_state_count,
          count(*) filter (where source_district_name = :district)::bigint as scoped_district_count
        from {TARGET_TABLE}
        where {where_sql}
    """), params).mappings().one())

    candidate_count = i(summary["candidate_profile_row_count"])
    summary["planned_approval_count"] = min(candidate_count, max_rows) if max_rows > 0 else 0
    summary["max_rows"] = max_rows

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
            where {where_sql}
            order by
              coalesce(total_population, 0) desc,
              source_subdistrict_name nulls last,
              source_village_name nulls last,
              id
            limit :limit
        """), params).mappings()
    ]

    return summary, items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-policy", action="store_true")
    parser.add_argument("--reviewer-notes")
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    state_scope_present = bool(args.state_or_ut)
    district_scope_present = bool(args.district)
    scope_present = state_scope_present and district_scope_present
    notes_present = bool((args.reviewer_notes or "").strip())
    max_rows_present = args.max_rows > 0

    error = None
    if not args.apply:
        error = "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_EXPLICIT_APPLY_FLAG"
    elif not scope_present:
        error = "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_STATE_AND_DISTRICT_SCOPE"
    elif not notes_present:
        error = "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_REVIEWER_NOTES"
    elif not max_rows_present:
        error = "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_REQUIRES_POSITIVE_MAX_ROWS"
    elif not args.enable_policy:
        error = "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_APPROVAL_APPLY_DISABLED_BY_POLICY"

    approved_count = 0
    db_writes_attempted = False

    engine = create_engine(load_settings_url())
    with engine.begin() as conn:
        before = current_counts(conn)
        candidate_summary, sample_items = scoped_candidate_report(
            conn,
            args.state_or_ut,
            args.district,
            args.max_rows,
            args.limit,
        )

        if error is None:
            db_writes_attempted = True
            approval_event = {
                "latest_review_event": {
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                    "from_review_status": "AUTO_CANDIDATE",
                    "to_review_status": "APPROVED_FOR_PROMOTION",
                    "reviewer_decision": "BULK_APPROVE_FOR_PROMOTION",
                    "reviewer_notes": args.reviewer_notes,
                    "action": "NWDP_DEMOGRAPHIC_PROFILE_FIXTURE_BULK_REVIEW_APPROVAL_NO_PROMOTION",
                },
                "review_guardrail": {
                    "promotion_status_remains_not_promoted": True,
                    "is_active_remains_false": True,
                    "runtime_lookup_changed": False,
                    "android_behavior_changed": False,
                    "official_census_claimed_imported": False,
                },
            }

            result = conn.execute(text(f"""
                with selected as (
                  select id
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
                    source_village_name nulls last,
                    id
                  limit :max_rows
                )
                update {TARGET_TABLE} p
                set
                  review_status = 'APPROVED_FOR_PROMOTION',
                  updated_at = now(),
                  match_evidence = coalesce(p.match_evidence, '{{}}'::jsonb) || cast(:approval_event as jsonb)
                from selected
                where p.id = selected.id
            """), {
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
                "state_or_ut": args.state_or_ut,
                "district": args.district,
                "max_rows": args.max_rows,
                "approval_event": json.dumps(approval_event),
            })
            approved_count = i(result.rowcount)

        after = current_counts(conn)

    result = {
        "schema_version": "nwdp_demographic_profile_review_approval_apply.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "REVIEW_APPROVAL_APPLY_DISABLED_GUARD",
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
        "approval_policy": {
            "required_source_system": SOURCE_SYSTEM,
            "required_source_version": SOURCE_VERSION,
            "required_review_status": "AUTO_CANDIDATE",
            "required_promotion_status": "NOT_PROMOTED",
            "required_is_active": False,
            "target_review_status": "APPROVED_FOR_PROMOTION",
            "reviewer_notes_required": True,
            "positive_max_rows_required": True,
            "bulk_approval_apply_enabled": bool(args.enable_policy),
        },
        "approval_summary": {key: i(value) for key, value in candidate_summary.items()},
        "sample_items": sample_items,
        "before": {key: i(value) for key, value in before.items()},
        "after": {key: i(value) for key, value in after.items()},
        "apply_result": {
            "apply_implemented": bool(args.enable_policy),
            "planned_approval_count": i(candidate_summary["planned_approval_count"]),
            "approved_count": approved_count,
        },
        "guardrails": {
            "db_writes_attempted": db_writes_attempted,
            "profile_review_status_changed": approved_count > 0,
            "profiles_promoted": False,
            "profile_rows_activated": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
            "lgd_geography_overwritten": False,
        },
        "readiness": {
            "ready_for_tiny_fixture_review_approval_apply_regression": True,
            "ready_for_real_scoped_review_approval_apply": bool(args.enable_policy) and error is None,
            "ready_for_promotion_dry_run": approved_count > 0,
            "ready_for_profile_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "claim_boundary": (
            "Review approval apply is disabled by policy unless explicitly enabled "
            "for a scoped regression. It can move inactive auto-candidate not-promoted "
            "NWDP demographic profiles to approved-for-promotion, but does not promote "
            "profiles, activate rows, enable runtime lookup, or change Android behavior."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
