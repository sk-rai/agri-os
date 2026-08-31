#!/usr/bin/env python3
"""Fast plan-only all-state NWDP demographic inactive profile apply.

Uses DB aggregate counts only. It does not scan raw GeoJSON and does not write
profile rows.
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

from scripts.apply_nwdp_demographic_profile_import import (  # noqa: E402
    SOURCE_SYSTEM,
    SOURCE_VERSION,
    load_settings_url,
    normalize_state_key,
    state_key_aliases,
)


DEFAULT_OUTPUT = Path("/tmp/nwdp-demographic-all-state-inactive-apply-plan.json")
NATIONAL_SUMMARY = ROOT / "data/staged/core_stack/nwdp_full_overlay_runs/20260829_full_national_2worker/combined_national_overlay_summary.json"


def load_national_summary() -> dict:
    if not NATIONAL_SUMMARY.exists():
        return {}
    return json.loads(NATIONAL_SUMMARY.read_text(encoding="utf-8"))


def summary_count(summary: dict, key: str):
    """Read national summary count from either top-level or nested shapes."""

    if key in summary:
        return summary.get(key)

    for nested_key in ("summary", "counts", "totals"):
        nested = summary.get(nested_key)
        if isinstance(nested, dict) and key in nested:
            return nested.get(key)

    return None


def fetch_state_candidate_counts() -> list[dict]:
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                select
                  b.state_or_ut,
                  count(*)::bigint as planned_profile_rows
                from geography_boundary_crosswalk_candidates c
                join geography_boundary_import_batches b on b.id = c.import_batch_id
                where b.source_system = :source_system
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.proposed_village_id is not null
                group by b.state_or_ut
                order by b.state_or_ut
            """),
            {"source_system": SOURCE_SYSTEM},
        ).mappings().all()

    return [
        {
            "state_or_ut": str(row["state_or_ut"]),
            "planned_profile_rows": int(row["planned_profile_rows"]),
        }
        for row in rows
    ]


def fetch_existing_profile_counts() -> dict[str, int]:
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                select
                  source_state_name,
                  count(*)::bigint as existing_profile_rows
                from geography_village_demographic_profiles
                where source_system = :source_system
                  and source_version = :source_version
                group by source_state_name
            """),
            {
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
            },
        ).mappings().all()

    counts: dict[str, int] = {}
    for row in rows:
        state_name = str(row["source_state_name"])
        count = int(row["existing_profile_rows"])
        for alias in state_key_aliases(state_name):
            counts[alias] = counts.get(alias, 0) + count
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-rows-per-state", type=int, default=200000)
    args = parser.parse_args()

    national = load_national_summary()
    planned_by_state = fetch_state_candidate_counts()
    existing_by_state = fetch_existing_profile_counts()

    state_plans = []
    for row in planned_by_state:
        planned = row["planned_profile_rows"]
        existing = max(existing_by_state.get(alias, 0) for alias in state_key_aliases(row["state_or_ut"]))
        remaining = max(planned - existing, 0)
        state_plans.append({
            "state_or_ut": row["state_or_ut"],
            "planned_profile_rows": planned,
            "existing_profile_rows": existing,
            "remaining_insert_rows": remaining,
            "max_rows_per_state": args.max_rows_per_state,
            "within_max_rows": planned <= args.max_rows_per_state,
            "ready_for_state_apply": remaining > 0 and planned <= args.max_rows_per_state,
        })

    total_planned = sum(row["planned_profile_rows"] for row in state_plans)
    total_existing = sum(row["existing_profile_rows"] for row in state_plans)
    total_remaining = sum(row["remaining_insert_rows"] for row in state_plans)

    result = {
        "schema_version": "nwdp_demographic_all_state_inactive_apply_plan.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": total_planned > 0,
        "mode": "FAST_DB_AGGREGATE_PLAN_ONLY_ALL_STATE_INACTIVE_PROFILE_APPLY",
        "target_table": "geography_village_demographic_profiles",
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
        "state_count": len(state_plans),
        "total_planned_profile_rows": total_planned,
        "total_existing_profile_rows": total_existing,
        "total_remaining_insert_rows": total_remaining,
        "national_overlay_summary": {
            "path": str(NATIONAL_SUMMARY),
            "available": bool(national),
            "overlaid_count": summary_count(national, "overlaid_count"),
            "eligible_candidate_count": summary_count(national, "eligible_candidate_count"),
        },
        "state_plans": state_plans,
        "recommended_execution": {
            "execution_model": "one state/UT at a time",
            "apply_command": "backend/scripts/apply_nwdp_demographic_profile_import.py --state-or-ut <STATE> --apply --max-rows <COUNT>",
            "resume_policy": "rerun state safely; existing source_feature_id rows are skipped",
            "all_state_single_transaction_allowed": False,
        },
        "performance_policy": {
            "raw_geojson_scanned": False,
            "db_aggregate_only": True,
            "expected_runtime_seconds": "low single digits",
        },
        "claim_boundary": (
            "This is an all-state DB-aggregate plan only. It does not insert "
            "demographic profile rows, promote profiles, activate candidates, "
            "enable runtime lookup, change Android behavior, or claim official "
            "Census import."
        ),
        "guardrails": {
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "profiles_promoted": False,
            "lgd_geography_overwritten": False,
            "official_census_claimed_imported": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_one_state_at_a_time_apply": total_remaining > 0,
            "ready_for_single_all_state_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "output": str(args.output),
        "healthy": result["healthy"],
        "state_count": result["state_count"],
        "total_planned_profile_rows": total_planned,
        "total_existing_profile_rows": total_existing,
        "total_remaining_insert_rows": total_remaining,
        "andaman": [row for row in state_plans if row["state_or_ut"] == "Andaman & Nicobar Island"],
    }, indent=2, sort_keys=True))

    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
