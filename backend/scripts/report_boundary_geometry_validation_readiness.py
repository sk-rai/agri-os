#!/usr/bin/env python3
"""Read-only NWDP boundary geometry validation readiness report.

This report explains why selected boundary runtime promotion is currently
blocked: geometry validation status, runtime eligibility posture, source-feature
coverage, and state/district blocker distribution. It does not repair geometry,
promote candidates, write runtime tables, enable lookup, overwrite LGD, or
change Android behavior.
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

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402


SCHEMA_VERSION = "boundary_geometry_validation_readiness.v1"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
VALID_GEOMETRY_STATUSES = ("VALID", "VALIDATED", "VALID_WITH_WARNINGS")


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
    parser = argparse.ArgumentParser(description="Read-only boundary geometry validation readiness report.")
    parser.add_argument("--output-dir", default="/tmp/boundary-geometry-validation-readiness")
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
        summary_row = conn.execute(text(f"""
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
                sf.geometry_validation_status,
                sf.eligible_for_runtime_after_promotion,
                sf.transformed_centroid,
                sf.transformed_bbox
              from geography_boundary_import_batches b
              join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
              left join geography_boundary_source_features sf on sf.id = c.source_feature_id
              left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
              left join geography_districts d
                on d.state_id = s.id
               and d.lgd_code::text = c.proposed_district_lgd_code::text
              where {where_sql}
            ),
            valid_runtime_eligible as (
              select *
              from candidates
              where source_feature_id is not null
                and proposed_village_id is not null
                and coalesce(eligible_for_runtime_after_promotion, false) = true
                and coalesce(geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
            ),
            selected_promotable as (
              select *
              from valid_runtime_eligible
              where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                and review_status = 'AUTO_CANDIDATE'
                and promotion_status = 'NOT_PROMOTED'
                and is_active = false
            )
            select
              count(*)::bigint as candidate_count,
              count(*) filter (where source_feature_id is null)::bigint as missing_source_feature_count,
              count(*) filter (where proposed_village_id is null)::bigint as missing_village_id_count,
              count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as valid_geometry_count,
              count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as invalid_geometry_count,
              count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') = 'UNKNOWN')::bigint as unknown_geometry_status_count,
              count(*) filter (where coalesce(eligible_for_runtime_after_promotion, false) = true)::bigint as runtime_eligible_source_count,
              count(*) filter (where coalesce(eligible_for_runtime_after_promotion, false) = false)::bigint as not_runtime_eligible_source_count,
              count(*) filter (where transformed_centroid is not null)::bigint as transformed_centroid_count,
              count(*) filter (where transformed_bbox is not null)::bigint as transformed_bbox_count,
              count(*) filter (where candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as direct_vlcode_match_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
              count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
              count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_candidate_count,
              count(*) filter (where is_active = true)::bigint as active_candidate_count,
              (select count(*)::bigint from valid_runtime_eligible)::bigint as valid_runtime_eligible_candidate_count,
              (select count(*)::bigint from selected_promotable)::bigint as selected_runtime_promotable_count,
              (select count(distinct proposed_village_id)::bigint from selected_promotable)::bigint as selected_runtime_promotable_village_count,
              (select count(*)::bigint from geography_boundary_runtime_sets)::bigint as existing_runtime_set_count,
              (select count(*)::bigint from geography_boundary_runtime_features)::bigint as existing_runtime_feature_count,
              (select count(*)::bigint from geography_boundary_runtime_crosswalks)::bigint as existing_runtime_crosswalk_count,
              (select count(*)::bigint from geography_boundary_runtime_sets where is_active = true)::bigint as active_runtime_set_count,
              (select count(*)::bigint from geography_boundary_runtime_features where is_active = true)::bigint as active_runtime_feature_count,
              (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true)::bigint as active_runtime_crosswalk_count
            from candidates
        """), params).mappings().one()

        status_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                select
                  coalesce(sf.geometry_validation_status, 'UNKNOWN') as geometry_validation_status,
                  coalesce(sf.eligible_for_runtime_after_promotion, false) as eligible_for_runtime_after_promotion,
                  count(*)::bigint as candidate_count,
                  count(*) filter (where c.candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as direct_vlcode_match_count,
                  count(*) filter (where c.review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
                  count(*) filter (where c.review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
                  count(*) filter (where c.review_status = 'BLOCKED')::bigint as blocked_count
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                left join geography_districts d
                  on d.state_id = s.id
                 and d.lgd_code::text = c.proposed_district_lgd_code::text
                where {where_sql}
                group by coalesce(sf.geometry_validation_status, 'UNKNOWN'), coalesce(sf.eligible_for_runtime_after_promotion, false)
                order by candidate_count desc, geometry_validation_status
            """), params)
        ]

        state_district_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                select
                  coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut) as state_or_ut,
                  coalesce(d.canonical_name, sf.source_district_name) as district,
                  count(*)::bigint as candidate_count,
                  count(*) filter (where coalesce(sf.geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as valid_geometry_count,
                  count(*) filter (where coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as invalid_geometry_count,
                  count(*) filter (where coalesce(sf.eligible_for_runtime_after_promotion, false) = true)::bigint as runtime_eligible_source_count,
                  count(*) filter (where coalesce(sf.eligible_for_runtime_after_promotion, false) = false)::bigint as not_runtime_eligible_source_count,
                  count(*) filter (
                    where c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
                      and c.review_status = 'AUTO_CANDIDATE'
                      and c.promotion_status = 'NOT_PROMOTED'
                      and c.is_active = false
                      and c.proposed_village_id is not null
                      and coalesce(sf.eligible_for_runtime_after_promotion, false) = true
                      and coalesce(sf.geometry_validation_status, 'UNKNOWN') in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
                  )::bigint as selected_runtime_promotable_count
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                left join geography_districts d
                  on d.state_id = s.id
                 and d.lgd_code::text = c.proposed_district_lgd_code::text
                where {where_sql}
                group by coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut), coalesce(d.canonical_name, sf.source_district_name)
                order by invalid_geometry_count desc, not_runtime_eligible_source_count desc, candidate_count desc, state_or_ut, district
                limit :limit
            """), params)
        ]

        blocker_samples = [
            row_dict(row)
            for row in conn.execute(text(f"""
                select
                  coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut) as state_or_ut,
                  coalesce(d.canonical_name, sf.source_district_name) as district,
                  sf.source_subdistrict_name,
                  sf.source_village_name,
                  sf.source_vlcode,
                  c.id::text as candidate_id,
                  c.proposed_village_id::text as proposed_village_id,
                  c.proposed_village_lgd_code,
                  c.candidate_bucket,
                  c.review_status,
                  c.promotion_status,
                  c.is_active,
                  c.confidence,
                  coalesce(sf.geometry_validation_status, 'UNKNOWN') as geometry_validation_status,
                  coalesce(sf.eligible_for_runtime_after_promotion, false) as eligible_for_runtime_after_promotion,
                  case
                    when c.source_feature_id is null then 'MISSING_SOURCE_FEATURE'
                    when c.proposed_village_id is null then 'MISSING_PROPOSED_VILLAGE'
                    when coalesce(sf.eligible_for_runtime_after_promotion, false) = false then 'SOURCE_NOT_RUNTIME_ELIGIBLE'
                    when coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS') then 'GEOMETRY_NOT_VALIDATED'
                    when c.candidate_bucket <> 'DIRECT_VLCODE_MATCH' then 'NON_DIRECT_BUCKET'
                    when c.review_status <> 'AUTO_CANDIDATE' then 'REVIEW_STATUS_NOT_AUTO_CANDIDATE'
                    when c.promotion_status <> 'NOT_PROMOTED' then 'ALREADY_PROMOTED_OR_NON_PROMOTABLE'
                    when c.is_active = true then 'CANDIDATE_ALREADY_ACTIVE'
                    else 'PROMOTABLE'
                  end as blocker
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                left join geography_districts d
                  on d.state_id = s.id
                 and d.lgd_code::text = c.proposed_district_lgd_code::text
                where {where_sql}
                  and (
                    c.source_feature_id is null
                    or c.proposed_village_id is null
                    or coalesce(sf.eligible_for_runtime_after_promotion, false) = false
                    or coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
                    or c.candidate_bucket <> 'DIRECT_VLCODE_MATCH'
                    or c.review_status <> 'AUTO_CANDIDATE'
                    or c.promotion_status <> 'NOT_PROMOTED'
                    or c.is_active = true
                  )
                order by state_or_ut, district, blocker, sf.source_village_name nulls last
                limit :limit
            """), params)
        ]

    summary = {key: int(value or 0) for key, value in row_dict(summary_row).items()}

    readiness = {
        "ready_for_admin_geometry_review": summary["candidate_count"] > 0,
        "ready_for_geometry_repair_plan": summary["invalid_geometry_count"] > 0 or summary["not_runtime_eligible_source_count"] > 0,
        "ready_for_selected_runtime_promotion_dry_run": summary["selected_runtime_promotable_count"] > 0,
        "ready_for_selected_runtime_promotion_apply": False,
        "ready_for_runtime_lookup_enablement": False,
        "ready_for_android_behavior_change": False,
        "requires_valid_geometry_before_runtime_promotion": True,
        "requires_runtime_eligible_source_before_runtime_promotion": True,
        "requires_state_or_district_scope_before_apply": True,
        "requires_rollback_or_supersession_plan": True,
    }

    guardrails = {
        "db_writes_attempted": False,
        "geometry_repair_attempted": False,
        "source_features_changed": False,
        "runtime_sets_written": False,
        "runtime_features_written": False,
        "runtime_crosswalks_written": False,
        "promotion_events_written": False,
        "boundary_candidates_promoted": False,
        "boundary_candidates_activated": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_BOUNDARY_GEOMETRY_VALIDATION_READINESS",
        "filters": {
            "state_or_ut": args.state_or_ut.strip() or None,
            "district": args.district.strip() or None,
            "limit": args.limit,
        },
        "claim_boundary": "This report is read-only. It inventories NWDP boundary geometry validation and runtime eligibility blockers without repairing geometry, changing source features, promoting candidates, writing runtime boundary tables, enabling lookup, overwriting LGD, or changing Android behavior.",
        "validation_policy": {
            "source_system": SOURCE_SYSTEM,
            "valid_geometry_statuses": list(VALID_GEOMETRY_STATUSES),
            "requires_runtime_eligible_source": True,
            "requires_direct_vlcode_match": True,
            "requires_auto_candidate_review_status": True,
            "requires_not_promoted": True,
            "requires_inactive_candidate": True,
            "requires_proposed_village_id": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "geometry_repair_supported_by_this_report": False,
            "runtime_promotion_supported_by_this_report": False,
            "android_behavior_change_supported_by_this_report": False,
        },
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "status_rows": status_rows,
        "state_district_rows": state_district_rows,
        "blocker_samples": blocker_samples,
        "output_files": {
            "json": str(output_dir / "boundary_geometry_validation_readiness.json"),
            "status_csv": str(output_dir / "boundary_geometry_validation_readiness_by_status.csv"),
            "state_district_csv": str(output_dir / "boundary_geometry_validation_readiness_by_state_district.csv"),
            "blocker_sample_csv": str(output_dir / "boundary_geometry_validation_readiness_blocker_samples.csv"),
        },
    }

    json_path = output_dir / "boundary_geometry_validation_readiness.json"
    status_csv = output_dir / "boundary_geometry_validation_readiness_by_status.csv"
    state_csv = output_dir / "boundary_geometry_validation_readiness_by_state_district.csv"
    sample_csv = output_dir / "boundary_geometry_validation_readiness_blocker_samples.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_csv(
        status_csv,
        status_rows,
        [
            "geometry_validation_status",
            "eligible_for_runtime_after_promotion",
            "candidate_count",
            "direct_vlcode_match_count",
            "auto_candidate_count",
            "manual_review_count",
            "blocked_count",
        ],
    )
    write_csv(
        state_csv,
        state_district_rows,
        [
            "state_or_ut",
            "district",
            "candidate_count",
            "valid_geometry_count",
            "invalid_geometry_count",
            "runtime_eligible_source_count",
            "not_runtime_eligible_source_count",
            "selected_runtime_promotable_count",
        ],
    )
    write_csv(
        sample_csv,
        blocker_samples,
        [
            "state_or_ut",
            "district",
            "source_subdistrict_name",
            "source_village_name",
            "source_vlcode",
            "candidate_id",
            "proposed_village_id",
            "proposed_village_lgd_code",
            "candidate_bucket",
            "review_status",
            "promotion_status",
            "is_active",
            "confidence",
            "geometry_validation_status",
            "eligible_for_runtime_after_promotion",
            "blocker",
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
