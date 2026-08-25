#!/usr/bin/env python3
"""Read-only plan for all-state NWDP inactive staging import."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATCH_PLAN_JSON = Path("/tmp/nwdp-boundary-all-state-match-plan.json")
DEFAULT_MATCH_PLAN_CSV = Path("/tmp/nwdp-boundary-all-state-match-plan.csv")
DEFAULT_OUTPUT = ROOT / "data/staged/nwdp_boundary_all_state/20260824T110250Z/inactive_staging_import_plan.json"
EXPECTED_SOURCE_FEATURE_COUNT = 654_285
EXPECTED_STATE_COUNT = 36


def build_plan(match_plan_json: Path, match_plan_csv: Path) -> dict[str, Any]:
    match_plan = json.loads(match_plan_json.read_text(encoding="utf-8"))
    state_counts: dict[str, int] = {}
    bucket_counts: Counter[str] = Counter()
    review_status_counts: Counter[str] = Counter()
    proposed_scope_counts: Counter[str] = Counter()

    with match_plan_csv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            state = row.get("state_or_ut") or ""
            state_counts[state] = state_counts.get(state, 0) + 1
            bucket_counts[row.get("candidate_bucket") or row.get("bucket") or ""] += 1
            review_status_counts[row.get("review_status") or ""] += 1
            proposed_scope_counts[row.get("proposed_scope") or ""] += 1

    planned_total = sum(state_counts.values())
    source_summary = match_plan.get("summary") or {}
    healthy = (
        match_plan.get("healthy") is True
        and len(state_counts) == EXPECTED_STATE_COUNT
        and planned_total == EXPECTED_SOURCE_FEATURE_COUNT
        and planned_total == int(source_summary.get("source_feature_count") or 0)
        and dict(bucket_counts) == source_summary.get("bucket_counts")
        and dict(review_status_counts) == source_summary.get("review_status_counts")
    )

    return {
        "schema_version": "nwdp_boundary_all_state_inactive_staging_import_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "mode": "READ_ONLY_INACTIVE_STAGING_IMPORT_PLAN",
        "source_match_plan": str(match_plan_json),
        "source_match_csv": str(match_plan_csv),
        "summary": {
            "state_or_ut_count": len(state_counts),
            "planned_import_batch_count": len(state_counts),
            "planned_source_feature_insert_count": planned_total,
            "planned_candidate_insert_count": planned_total,
            "planned_active_source_feature_count": 0,
            "planned_active_candidate_count": 0,
            "planned_runtime_write_count": 0,
            "bucket_counts": dict(sorted(bucket_counts.items())),
            "review_status_counts": dict(sorted(review_status_counts.items())),
            "proposed_scope_counts": dict(sorted(proposed_scope_counts.items())),
        },
        "state_plans": [
            {
                "state_or_ut": state,
                "planned_import_batch_count": 1,
                "planned_source_feature_insert_count": count,
                "planned_candidate_insert_count": count,
                "planned_active_source_feature_count": 0,
                "planned_active_candidate_count": 0,
                "planned_runtime_write_count": 0,
            }
            for state, count in sorted(state_counts.items())
        ],
        "idempotency_policy": {
            "state_by_state": True,
            "re_run_requires_absent_or_clean_inactive_batch": True,
            "duplicate_source_file_sha256_must_be_blocked": True,
            "existing_active_batch_for_same_state_source_system_must_block": True,
        },
        "apply_policy": {
            "apply_implemented": False,
            "apply_requires_separate_checkpoint": True,
            "initial_apply_scope": "inactive staging rows only",
            "runtime_tables_allowed": False,
            "candidate_activation_allowed": False,
            "candidate_promotion_allowed": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
            "lookup_api_enabled": False,
        },
        "readiness": {
            "ready_for_inactive_staging_import_design": healthy,
            "ready_for_inactive_staging_import_apply": False,
            "ready_for_runtime_table_write": False,
            "ready_for_runtime_spatial_matching": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-plan-json", type=Path, default=DEFAULT_MATCH_PLAN_JSON)
    parser.add_argument("--match-plan-csv", type=Path, default=DEFAULT_MATCH_PLAN_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = build_plan(args.match_plan_json, args.match_plan_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
