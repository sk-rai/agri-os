#!/usr/bin/env python3
"""Read-only NWDP boundary geometry repair classification report.

This report classifies boundary runtime blockers into validation/repair/re-import
or exclusion buckets. It does not repair geometries, mutate source features,
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


SCHEMA_VERSION = "boundary_geometry_repair_classification.v1"
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


def repair_classification_case() -> str:
    return """
      case
        when c.source_feature_id is null then 'REIMPORT_MISSING_SOURCE_FEATURE'
        when c.proposed_village_id is null then 'CROSSWALK_REVIEW_MISSING_PROPOSED_VILLAGE'
        when coalesce(sf.eligible_for_runtime_after_promotion, false) = false
             and coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
          then 'VALIDATE_GEOMETRY_AND_RUNTIME_ELIGIBILITY'
        when coalesce(sf.geometry_validation_status, 'UNKNOWN') = 'UNKNOWN'
          then 'VALIDATE_GEOMETRY_STATUS'
        when coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
          then 'REPAIR_OR_REIMPORT_INVALID_GEOMETRY'
        when coalesce(sf.eligible_for_runtime_after_promotion, false) = false
          then 'SOURCE_RUNTIME_ELIGIBILITY_REVIEW'
        when c.candidate_bucket <> 'DIRECT_VLCODE_MATCH'
          then 'CROSSWALK_REVIEW_NON_DIRECT_BUCKET'
        when c.review_status = 'MANUAL_REVIEW'
          then 'MANUAL_REVIEW_REQUIRED'
        when c.review_status = 'BLOCKED'
          then 'PERMANENT_OR_POLICY_EXCLUSION'
        when c.review_status <> 'AUTO_CANDIDATE'
          then 'REVIEW_STATUS_RECONCILIATION'
        when c.promotion_status <> 'NOT_PROMOTED'
          then 'PROMOTION_STATUS_RECONCILIATION'
        when c.is_active = true
          then 'ACTIVE_CANDIDATE_RECONCILIATION'
        else 'NO_REPAIR_NEEDED_RUNTIME_PROMOTABLE'
      end
    """


def repair_action_case() -> str:
    return """
      case
        when repair_classification = 'REIMPORT_MISSING_SOURCE_FEATURE'
          then 'Re-import or restore source feature linkage before geometry validation.'
        when repair_classification = 'CROSSWALK_REVIEW_MISSING_PROPOSED_VILLAGE'
          then 'Resolve candidate to canonical LGD village before geometry work.'
        when repair_classification = 'VALIDATE_GEOMETRY_AND_RUNTIME_ELIGIBILITY'
          then 'Run geometry validation pipeline, then mark source feature runtime eligibility only after validation passes.'
        when repair_classification = 'VALIDATE_GEOMETRY_STATUS'
          then 'Run geometry validation and assign explicit validation status.'
        when repair_classification = 'REPAIR_OR_REIMPORT_INVALID_GEOMETRY'
          then 'Repair topology/transform or re-import source geometry; keep runtime promotion blocked.'
        when repair_classification = 'SOURCE_RUNTIME_ELIGIBILITY_REVIEW'
          then 'Review source provenance/geometry policy and set runtime eligibility only through a separate guarded workflow.'
        when repair_classification = 'CROSSWALK_REVIEW_NON_DIRECT_BUCKET'
          then 'Resolve non-direct crosswalk bucket manually before considering runtime promotion.'
        when repair_classification = 'MANUAL_REVIEW_REQUIRED'
          then 'Complete admin manual review before runtime workflows.'
        when repair_classification = 'PERMANENT_OR_POLICY_EXCLUSION'
          then 'Keep excluded unless a supersession policy explicitly unblocks it.'
        when repair_classification = 'NO_REPAIR_NEEDED_RUNTIME_PROMOTABLE'
          then 'Eligible for future selected-runtime dry-run only; real apply remains separately guarded.'
        else 'Review classification before any runtime action.'
      end
    """


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only boundary geometry repair classification report.")
    parser.add_argument("--output-dir", default="/tmp/boundary-geometry-repair-classification")
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
    classification = repair_classification_case()
    action = repair_action_case()

    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        summary = row_dict(conn.execute(text(f"""
            with classified as (
              select
                c.id,
                c.candidate_bucket,
                c.review_status,
                c.promotion_status,
                c.is_active,
                c.proposed_village_id,
                c.source_feature_id,
                coalesce(sf.geometry_validation_status, 'UNKNOWN') as geometry_validation_status,
                coalesce(sf.eligible_for_runtime_after_promotion, false) as eligible_for_runtime_after_promotion,
                {classification} as repair_classification
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
              count(*)::bigint as candidate_count,
              count(*) filter (where repair_classification = 'NO_REPAIR_NEEDED_RUNTIME_PROMOTABLE')::bigint as no_repair_needed_runtime_promotable_count,
              count(*) filter (where repair_classification = 'VALIDATE_GEOMETRY_AND_RUNTIME_ELIGIBILITY')::bigint as validate_geometry_and_runtime_eligibility_count,
              count(*) filter (where repair_classification = 'VALIDATE_GEOMETRY_STATUS')::bigint as validate_geometry_status_count,
              count(*) filter (where repair_classification = 'REPAIR_OR_REIMPORT_INVALID_GEOMETRY')::bigint as repair_or_reimport_invalid_geometry_count,
              count(*) filter (where repair_classification = 'SOURCE_RUNTIME_ELIGIBILITY_REVIEW')::bigint as source_runtime_eligibility_review_count,
              count(*) filter (where repair_classification = 'REIMPORT_MISSING_SOURCE_FEATURE')::bigint as reimport_missing_source_feature_count,
              count(*) filter (where repair_classification = 'CROSSWALK_REVIEW_MISSING_PROPOSED_VILLAGE')::bigint as crosswalk_review_missing_proposed_village_count,
              count(*) filter (where repair_classification = 'CROSSWALK_REVIEW_NON_DIRECT_BUCKET')::bigint as crosswalk_review_non_direct_bucket_count,
              count(*) filter (where repair_classification = 'MANUAL_REVIEW_REQUIRED')::bigint as manual_review_required_count,
              count(*) filter (where repair_classification = 'PERMANENT_OR_POLICY_EXCLUSION')::bigint as permanent_or_policy_exclusion_count,
              count(*) filter (where geometry_validation_status not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS'))::bigint as invalid_or_unknown_geometry_count,
              count(*) filter (where eligible_for_runtime_after_promotion = false)::bigint as runtime_ineligible_source_count,
              count(*) filter (
                where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                  and review_status = 'AUTO_CANDIDATE'
                  and promotion_status = 'NOT_PROMOTED'
                  and is_active = false
              )::bigint as direct_auto_not_promoted_inactive_count,
              count(*) filter (where promotion_status = 'PROMOTED')::bigint as promoted_candidate_count,
              count(*) filter (where is_active = true)::bigint as active_candidate_count,
              (select count(*)::bigint from geography_boundary_runtime_features where is_active = true)::bigint as active_runtime_feature_count,
              (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true)::bigint as active_runtime_crosswalk_count
            from classified
        """), params).mappings().one())

        classification_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                with classified as (
                  select
                    c.id,
                    c.candidate_bucket,
                    c.review_status,
                    c.promotion_status,
                    c.is_active,
                    coalesce(sf.geometry_validation_status, 'UNKNOWN') as geometry_validation_status,
                    coalesce(sf.eligible_for_runtime_after_promotion, false) as eligible_for_runtime_after_promotion,
                    {classification} as repair_classification
                  from geography_boundary_import_batches b
                  join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                  left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                  left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                  left join geography_districts d
                    on d.state_id = s.id
                   and d.lgd_code::text = c.proposed_district_lgd_code::text
                  where {where_sql}
                ),
                with_actions as (
                  select *, {action} as recommended_action
                  from classified
                )
                select
                  repair_classification,
                  recommended_action,
                  count(*)::bigint as candidate_count,
                  count(*) filter (where candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as direct_vlcode_match_count,
                  count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as auto_candidate_count,
                  count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as manual_review_count,
                  count(*) filter (where review_status = 'BLOCKED')::bigint as blocked_count
                from with_actions
                group by repair_classification, recommended_action
                order by candidate_count desc, repair_classification
            """), params).mappings()
        ]

        state_district_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                with classified as (
                  select
                    coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut) as state_or_ut,
                    coalesce(d.canonical_name, sf.source_district_name) as district,
                    c.candidate_bucket,
                    c.review_status,
                    c.promotion_status,
                    c.is_active,
                    {classification} as repair_classification
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
                  count(*) filter (where repair_classification = 'NO_REPAIR_NEEDED_RUNTIME_PROMOTABLE')::bigint as no_repair_needed_runtime_promotable_count,
                  count(*) filter (where repair_classification in ('VALIDATE_GEOMETRY_AND_RUNTIME_ELIGIBILITY', 'VALIDATE_GEOMETRY_STATUS', 'REPAIR_OR_REIMPORT_INVALID_GEOMETRY'))::bigint as geometry_validation_or_repair_count,
                  count(*) filter (where repair_classification = 'SOURCE_RUNTIME_ELIGIBILITY_REVIEW')::bigint as source_runtime_eligibility_review_count,
                  count(*) filter (where repair_classification = 'CROSSWALK_REVIEW_NON_DIRECT_BUCKET')::bigint as crosswalk_review_non_direct_bucket_count,
                  count(*) filter (where repair_classification = 'MANUAL_REVIEW_REQUIRED')::bigint as manual_review_required_count,
                  count(*) filter (where repair_classification = 'PERMANENT_OR_POLICY_EXCLUSION')::bigint as permanent_or_policy_exclusion_count
                from classified
                group by state_or_ut, district
                order by geometry_validation_or_repair_count desc, source_runtime_eligibility_review_count desc, candidate_count desc, state_or_ut, district
                limit :limit
            """), params).mappings()
        ]

        sample_rows = [
            row_dict(row)
            for row in conn.execute(text(f"""
                with classified as (
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
                    {classification} as repair_classification
                  from geography_boundary_import_batches b
                  join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                  left join geography_boundary_source_features sf on sf.id = c.source_feature_id
                  left join geography_states s on s.lgd_code::text = c.proposed_state_lgd_code::text
                  left join geography_districts d
                    on d.state_id = s.id
                   and d.lgd_code::text = c.proposed_district_lgd_code::text
                  where {where_sql}
                ),
                with_actions as (
                  select *, {action} as recommended_action
                  from classified
                )
                select *
                from with_actions
                where repair_classification <> 'NO_REPAIR_NEEDED_RUNTIME_PROMOTABLE'
                order by repair_classification, state_or_ut, district, source_village_name nulls last
                limit :limit
            """), params).mappings()
        ]

    summary = {key: int(value or 0) for key, value in summary.items()}
    for rows in (classification_rows, state_district_rows):
        for row in rows:
            for key, value in list(row.items()):
                if key.endswith("_count"):
                    row[key] = int(value or 0)

    readiness = {
        "ready_for_admin_repair_planning": summary["candidate_count"] > 0,
        "ready_for_geometry_validation_pipeline_design": (
            summary["validate_geometry_and_runtime_eligibility_count"] > 0
            or summary["validate_geometry_status_count"] > 0
            or summary["repair_or_reimport_invalid_geometry_count"] > 0
        ),
        "ready_for_runtime_eligibility_review": summary["runtime_ineligible_source_count"] > 0,
        "ready_for_selected_runtime_promotion_dry_run": summary["no_repair_needed_runtime_promotable_count"] > 0,
        "ready_for_selected_runtime_promotion_apply": False,
        "ready_for_runtime_lookup_enablement": False,
        "ready_for_android_behavior_change": False,
    }

    guardrails = {
        "db_writes_attempted": False,
        "geometry_repair_attempted": False,
        "geometry_validation_status_changed": False,
        "source_runtime_eligibility_changed": False,
        "source_features_changed": False,
        "boundary_candidates_promoted": False,
        "boundary_candidates_activated": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_BOUNDARY_GEOMETRY_REPAIR_CLASSIFICATION",
        "filters": {
            "state_or_ut": args.state_or_ut.strip() or None,
            "district": args.district.strip() or None,
            "limit": args.limit,
        },
        "claim_boundary": "This report is read-only. It classifies NWDP boundary geometry/runtime blockers for future repair planning without repairing geometry, changing validation status, changing runtime eligibility, promoting candidates, writing runtime tables, enabling lookup, overwriting LGD, or changing Android behavior.",
        "classification_policy": {
            "source_system": SOURCE_SYSTEM,
            "valid_geometry_statuses": list(VALID_GEOMETRY_STATUSES),
            "runtime_promotion_requires_valid_geometry": True,
            "runtime_promotion_requires_runtime_eligible_source": True,
            "runtime_promotion_requires_direct_auto_not_promoted_inactive_candidate": True,
            "state_or_district_scope_required_before_apply": True,
            "rollback_or_supersession_plan_required_before_apply": True,
            "geometry_repair_supported_by_this_report": False,
            "runtime_promotion_supported_by_this_report": False,
            "android_behavior_change_supported_by_this_report": False,
        },
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "classification_rows": classification_rows,
        "state_district_rows": state_district_rows,
        "sample_rows": sample_rows,
        "output_files": {
            "json": str(output_dir / "boundary_geometry_repair_classification.json"),
            "classification_csv": str(output_dir / "boundary_geometry_repair_classification_by_bucket.csv"),
            "state_district_csv": str(output_dir / "boundary_geometry_repair_classification_by_state_district.csv"),
            "sample_csv": str(output_dir / "boundary_geometry_repair_classification_samples.csv"),
        },
    }

    json_path = output_dir / "boundary_geometry_repair_classification.json"
    classification_csv = output_dir / "boundary_geometry_repair_classification_by_bucket.csv"
    state_csv = output_dir / "boundary_geometry_repair_classification_by_state_district.csv"
    sample_csv = output_dir / "boundary_geometry_repair_classification_samples.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_csv(
        classification_csv,
        classification_rows,
        [
            "repair_classification",
            "recommended_action",
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
            "no_repair_needed_runtime_promotable_count",
            "geometry_validation_or_repair_count",
            "source_runtime_eligibility_review_count",
            "crosswalk_review_non_direct_bucket_count",
            "manual_review_required_count",
            "permanent_or_policy_exclusion_count",
        ],
    )
    write_csv(
        sample_csv,
        sample_rows,
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
            "repair_classification",
            "recommended_action",
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
