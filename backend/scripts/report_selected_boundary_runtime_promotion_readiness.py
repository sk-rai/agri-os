#!/usr/bin/env python3
"""Read-only readiness report for selected NWDP boundary runtime promotion.

This report answers which staged NWDP boundary candidates are safe to consider
for a future selected runtime promotion, without writing runtime rows, promoting
candidates, enabling lookup, or changing Android behavior.
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


SCHEMA_VERSION = "selected_boundary_runtime_promotion_readiness.v1"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def db_url_from_settings() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only selected boundary runtime promotion readiness report.")
    parser.add_argument("--output-dir", default="/tmp/selected-boundary-runtime-promotion-readiness")
    parser.add_argument("--state-or-ut", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    where = ["b.source_system = :source_system"]
    params: dict[str, Any] = {
        "source_system": SOURCE_SYSTEM,
        "state_or_ut": args.state_or_ut.strip(),
        "district": args.district.strip(),
        "limit": args.limit,
    }

    if args.state_or_ut.strip():
        where.append("lower(trim(coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut))) = lower(trim(:state_or_ut))")
    if args.district.strip():
        where.append("lower(trim(coalesce(d.canonical_name, sf.source_district_name))) = lower(trim(:district))")

    where_sql = " and ".join(where)

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        summary = row_dict(conn.execute(text(f"""
            with candidates as (
              select
                c.id,
                c.source_feature_id,
                c.candidate_bucket,
                c.review_status,
                c.promotion_status,
                c.is_active,
                c.proposed_village_id,
                c.proposed_village_lgd_code,
                c.proposed_district_lgd_code,
                c.proposed_state_lgd_code,
                c.confidence,
                sf.geometry_validation_status,
                sf.eligible_for_runtime_after_promotion,
                sf.transformed_centroid,
                sf.transformed_bbox,
                sf.source_state_name,
                sf.source_district_name,
                s.id as state_id,
                d.id as district_id
              from geography_boundary_import_batches b
              join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
              left join geography_boundary_source_features sf on sf.id = c.source_feature_id
              left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
              left join geography_districts d
                on d.state_id = s.id
               and d.lgd_code::text = c.proposed_district_lgd_code::text
              where {where_sql}
            ),
            promotable as (
              select *
              from candidates
              where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                and review_status = 'AUTO_CANDIDATE'
                and promotion_status = 'NOT_PROMOTED'
                and is_active = false
                and proposed_village_id is not null
                and source_feature_id is not null
                and coalesce(eligible_for_runtime_after_promotion, false) = true
                and coalesce(geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
            )
            select
              count(*)::bigint as candidate_count,
              count(*) filter (where candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as direct_vlcode_match_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_candidate_count,
              count(*) filter (where is_active = true)::bigint as active_candidate_count,
              count(*) filter (where proposed_village_id is null)::bigint as missing_village_id_count,
              count(*) filter (where source_feature_id is null)::bigint as missing_source_feature_count,
              count(*) filter (where coalesce(eligible_for_runtime_after_promotion, false) = false)::bigint as not_runtime_eligible_source_count,
              count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as invalid_geometry_count,
              (select count(*)::bigint from promotable)::bigint as selected_runtime_promotable_count,
              (select count(distinct proposed_village_id)::bigint from promotable)::bigint as selected_runtime_promotable_village_count,
              (select count(*)::bigint from geography_boundary_runtime_sets)::bigint as existing_runtime_set_count,
              (select count(*)::bigint from geography_boundary_runtime_features)::bigint as existing_runtime_feature_count,
              (select count(*)::bigint from geography_boundary_runtime_crosswalks)::bigint as existing_runtime_crosswalk_count,
              (select count(*)::bigint from geography_boundary_runtime_promotion_events)::bigint as existing_runtime_promotion_event_count,
              (select count(*)::bigint from geography_boundary_runtime_sets where is_active = true)::bigint as active_runtime_set_count,
              (select count(*)::bigint from geography_boundary_runtime_features where is_active = true)::bigint as active_runtime_feature_count,
              (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true)::bigint as active_runtime_crosswalk_count
            from candidates
        """), params).one())

        state_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                with candidates as (
                  select
                    c.id,
                    c.candidate_bucket,
                    c.review_status,
                    c.promotion_status,
                    c.is_active,
                    c.proposed_village_id,
                    sf.eligible_for_runtime_after_promotion,
                    sf.geometry_validation_status,
                    coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut) as state_or_ut,
                    coalesce(d.canonical_name, sf.source_district_name) as district
                  from geography_boundary_import_batches b
                  join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                  left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                  left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                  left join geography_districts d
                    on d.state_id = s.id
                   and d.lgd_code::text = c.proposed_district_lgd_code::text
                  where {where_sql}
                )
                select
                  state_or_ut,
                  district,
                  count(*)::bigint as candidate_count,
                  count(*) filter (
                    where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                      and review_status = 'AUTO_CANDIDATE'
                      and promotion_status = 'NOT_PROMOTED'
                      and is_active = false
                      and proposed_village_id is not null
                      and coalesce(eligible_for_runtime_after_promotion, false) = true
                      and coalesce(geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
                  )::bigint as selected_runtime_promotable_count,
                  count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
                  count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count
                from candidates
                group by state_or_ut, district
                order by selected_runtime_promotable_count desc, candidate_count desc, state_or_ut, district
                limit :limit
            """), params)
        ]

        samples = [
            row_dict(row)
            for row in conn.execute(text(f"""
                select
                  b.state_or_ut,
                  sf.source_district_name,
                  sf.source_subdistrict_name,
                  sf.source_village_name,
                  sf.source_vlcode,
                  c.id::text as candidate_id,
                  c.proposed_village_id::text as proposed_village_id,
                  c.proposed_village_lgd_code,
                  c.candidate_bucket,
                  c.review_status,
                  c.promotion_status,
                  c.confidence,
                  sf.geometry_validation_status,
                  sf.eligible_for_runtime_after_promotion
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                join geography_boundary_source_features sf on sf.id = c.source_feature_id
                left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                left join geography_districts d
                  on d.state_id = s.id
                 and d.lgd_code::text = c.proposed_district_lgd_code::text
                where {where_sql}
                  and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and c.review_status = 'AUTO_CANDIDATE'
                  and c.promotion_status = 'NOT_PROMOTED'
                  and c.is_active = false
                  and c.proposed_village_id is not null
                  and coalesce(sf.eligible_for_runtime_after_promotion, false) = true
                  and coalesce(sf.geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
                order by b.state_or_ut, sf.source_district_name, sf.source_feature_index
                limit :limit
            """), params)
        ]

    summary = {key: int(value or 0) for key, value in summary.items()}

    readiness = {
        "ready_for_selected_runtime_promotion_dry_run": summary["selected_runtime_promotable_count"] > 0,
        "ready_for_selected_runtime_promotion_apply": False,
        "ready_for_runtime_lookup_enablement": False,
        "ready_for_android_behavior_change": False,
        "requires_state_or_district_scope_before_apply": True,
        "requires_admin_review_before_apply": True,
        "requires_rollback_or_supersession_plan": True,
    }

    guardrails = {
        "db_writes_attempted": False,
        "runtime_sets_written": False,
        "runtime_features_written": False,
        "runtime_crosswalks_written": False,
        "promotion_events_written": False,
        "candidates_promoted": False,
        "candidates_activated": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_SELECTED_BOUNDARY_RUNTIME_PROMOTION_READINESS",
        "filters": {
            "state_or_ut": args.state_or_ut.strip() or None,
            "district": args.district.strip() or None,
            "limit": args.limit,
        },
        "claim_boundary": "This report is read-only. It identifies staged NWDP boundary candidates that may be considered for a future selected runtime promotion, but does not write runtime tables, promote candidates, enable lookup, overwrite LGD, or change Android behavior.",
        "promotion_policy": {
            "source_system": SOURCE_SYSTEM,
            "required_candidate_bucket": "DIRECT_VLCODE_MATCH",
            "required_review_status": "AUTO_CANDIDATE",
            "required_promotion_status": "NOT_PROMOTED",
            "required_candidate_is_active": False,
            "requires_proposed_village_id": True,
            "requires_source_feature_id": True,
            "requires_runtime_eligible_source": True,
            "requires_valid_geometry": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "real_apply_supported_by_this_report": False,
            "runtime_lookup_enablement_supported_by_this_report": False,
            "android_behavior_change_supported_by_this_report": False,
        },
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "state_district_rows": state_rows,
        "selected_candidate_samples": samples,
        "output_files": {
            "json": str(output_dir / "selected_boundary_runtime_promotion_readiness.json"),
            "state_district_csv": str(output_dir / "selected_boundary_runtime_promotion_readiness_by_state_district.csv"),
            "sample_csv": str(output_dir / "selected_boundary_runtime_promotion_readiness_samples.csv"),
        },
    }

    (output_dir / "selected_boundary_runtime_promotion_readiness.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "selected_boundary_runtime_promotion_readiness_by_state_district.csv",
        state_rows,
        ["state_or_ut", "district", "candidate_count", "selected_runtime_promotable_count", "manual_review_count", "blocked_count"],
    )
    write_csv(
        output_dir / "selected_boundary_runtime_promotion_readiness_samples.csv",
        samples,
        [
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
        ],
    )

    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "healthy": True,
        "summary": summary,
        "readiness": readiness,
        "outputs": report["output_files"],
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
