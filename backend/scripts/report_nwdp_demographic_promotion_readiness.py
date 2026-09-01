#!/usr/bin/env python3
"""Read-only NWDP demographic promotion readiness report by state/district."""

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

DEFAULT_OUT_DIR = ROOT / "data/staged/core_stack/nwdp_demographic_promotion_readiness"
TARGET_TABLE = "geography_village_demographic_profiles"


def i(value):
    return int(value or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-or-ut")
    parser.add_argument("--district")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=5000)
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
        rows = [
            dict(row)
            for row in conn.execute(text(f"""
                select
                  source_state_name as state_or_ut,
                  source_district_name as district,
                  count(*)::bigint as profile_row_count,
                  count(*) filter (
                    where review_status = 'APPROVED_FOR_PROMOTION'
                      and promotion_status = 'NOT_PROMOTED'
                      and is_active = false
                  )::bigint as eligible_for_promotion_count,
                  count(*) filter (
                    where not (
                      review_status = 'APPROVED_FOR_PROMOTION'
                      and promotion_status = 'NOT_PROMOTED'
                      and is_active = false
                    )
                  )::bigint as not_eligible_for_promotion_count,
                  count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
                  count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
                  count(*) filter (where review_status = 'APPROVED_FOR_PROMOTION')::bigint as approved_for_promotion_count,
                  count(*) filter (where review_status = 'REJECTED')::bigint as rejected_count,
                  count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
                  count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_profile_row_count,
                  count(*) filter (where is_active = true)::bigint as active_profile_row_count
                from {TARGET_TABLE}
                where {where_sql}
                group by source_state_name, source_district_name
                order by eligible_for_promotion_count desc, profile_row_count desc, source_state_name, source_district_name
                limit :limit
            """), params).mappings()
        ]

    normalized_rows = [
        {key: (i(value) if key.endswith("_count") else value) for key, value in row.items()}
        for row in rows
    ]

    total_profile_rows = sum(row["profile_row_count"] for row in normalized_rows)
    total_eligible = sum(row["eligible_for_promotion_count"] for row in normalized_rows)
    total_not_eligible = sum(row["not_eligible_for_promotion_count"] for row in normalized_rows)
    total_auto = sum(row["auto_candidate_count"] for row in normalized_rows)
    total_manual = sum(row["manual_review_count"] for row in normalized_rows)
    total_approved = sum(row["approved_for_promotion_count"] for row in normalized_rows)
    total_active = sum(row["active_profile_row_count"] for row in normalized_rows)
    total_promoted = sum(row["promoted_profile_row_count"] for row in normalized_rows)

    result = {
        "schema_version": "nwdp_demographic_promotion_readiness_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": total_profile_rows > 0,
        "mode": "READ_ONLY_STATE_DISTRICT_PROMOTION_READINESS_REPORT",
        "target_table": TARGET_TABLE,
        "source_system": SOURCE_SYSTEM,
        "source_version": SOURCE_VERSION,
        "filters": {
            "state_or_ut": args.state_or_ut,
            "district": args.district,
            "limit": args.limit,
        },
        "summary": {
            "state_district_row_count": len(normalized_rows),
            "profile_row_count": total_profile_rows,
            "eligible_for_promotion_count": total_eligible,
            "not_eligible_for_promotion_count": total_not_eligible,
            "auto_candidate_count": total_auto,
            "manual_review_count": total_manual,
            "approved_for_promotion_count": total_approved,
            "active_profile_row_count": total_active,
            "promoted_profile_row_count": total_promoted,
        },
        "eligibility_policy": {
            "eligible_requires_review_status": "APPROVED_FOR_PROMOTION",
            "eligible_requires_promotion_status": "NOT_PROMOTED",
            "eligible_requires_is_active": False,
            "not_eligible_includes_auto_candidate": True,
            "not_eligible_includes_manual_review": True,
            "not_eligible_includes_rejected_or_blocked": True,
            "not_eligible_includes_already_active_or_promoted": True,
        },
        "state_district_summary": normalized_rows,
        "top_not_eligible_districts": sorted(
            normalized_rows,
            key=lambda row: (-row["not_eligible_for_promotion_count"], row["state_or_ut"] or "", row["district"] or ""),
        )[:20],
        "top_eligible_districts": [
            row for row in normalized_rows
            if row["eligible_for_promotion_count"] > 0
        ][:20],
        "claim_boundary": (
            "This report is read-only. It summarizes eligible and not-eligible "
            "NWDP demographic profile rows by state/district for admin review, "
            "but does not change review status, promote profiles, activate rows, "
            "enable runtime lookup, or change Android behavior."
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
            "ready_for_admin_review_prioritization": total_not_eligible > 0,
            "ready_for_promotion_dry_run": total_eligible > 0,
            "ready_for_profile_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "nwdp_demographic_promotion_readiness_report.json"
    csv_path = args.output_dir / "nwdp_demographic_promotion_readiness_by_district.csv"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = [
        "state_or_ut",
        "district",
        "profile_row_count",
        "eligible_for_promotion_count",
        "not_eligible_for_promotion_count",
        "auto_candidate_count",
        "manual_review_count",
        "approved_for_promotion_count",
        "rejected_count",
        "blocked_count",
        "active_profile_row_count",
        "promoted_profile_row_count",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized_rows)

    result["output_files"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "json": str(json_path),
        "csv": str(csv_path),
        "healthy": result["healthy"],
        "summary": result["summary"],
        "top_not_eligible_districts": result["top_not_eligible_districts"][:5],
        "top_eligible_districts": result["top_eligible_districts"][:5],
    }, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
