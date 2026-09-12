"""Geography cascade API endpoints.

GET /api/v1/master-data/geography/states
GET /api/v1/master-data/geography/districts?state_id=
GET /api/v1/master-data/geography/blocks?district_id=
GET /api/v1/master-data/geography/villages?block_id=  (block-scoped)
GET /api/v1/master-data/geography/villages?district_id=  (district-wide, for offline cache)
GET /api/v1/master-data/geography/villages/search?q=&district_id=  (fuzzy, optionally scoped)
GET /api/v1/master-data/geography/villages/by-lgd-codes?lgd_codes=  (bulk canonical lookup)
"""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.admin_auth import AdminPermission, require_admin_permission
from app.core.database import get_db
from scripts.report_project_boundary_readiness import (
    SOURCE_SYSTEM as PROJECT_BOUNDARY_SOURCE_SYSTEM,
    build_scope_village_sql as _build_project_boundary_scope_village_sql,
    rows as _project_boundary_rows,
    scope_counts_for_project as _project_boundary_scope_counts_for_project,
)
from scripts.report_external_api_readiness import (
    safe_count as _external_api_safe_count,
    soil_provider_rows as _external_api_soil_provider_rows,
    weather_rows as _external_api_weather_rows,
)
from scripts.report_boundary_geometry_validation_readiness import (
    VALID_GEOMETRY_STATUSES as _BOUNDARY_VALID_GEOMETRY_STATUSES,
)
from scripts.report_boundary_geometry_repair_classification import (
    repair_action_case as _boundary_repair_action_case,
    repair_classification_case as _boundary_repair_classification_case,
)

from app.modules.master_data.models import (
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
    GeographyPostalReference,
    GeographyVillagePinLink,
)

router = APIRouter(prefix="/geography", tags=["geography"])


def _build_external_api_readiness_rollup(db: Session) -> dict[str, Any]:
    """Read-only external API/provider readiness rollup for the geography admin matrix."""

    weather = _external_api_weather_rows(db)
    soil = _external_api_soil_provider_rows(db)
    provider_rows = weather + soil

    summary = {
        "provider_surface_count": len(provider_rows),
        "weather_provider_config_count": len(weather),
        "weather_provider_enabled_count": sum(1 for row in weather if row["is_enabled"]),
        "weather_live_execution_enabled_count": sum(1 for row in weather if row["live_execution_enabled"]),
        "weather_demo_mode_provider_count": sum(1 for row in weather if row["demo_mode"]),
        "soil_provider_surface_count": len(soil),
        "soil_live_execution_enabled_count": 0,
        "weather_snapshot_count": _external_api_safe_count(db, "weather_snapshots"),
        "weather_fresh_snapshot_count": _external_api_safe_count(db, "weather_snapshots", "expires_at is null or expires_at > now()"),
        "soil_enrichment_snapshot_count": _external_api_safe_count(db, "soil_enrichment_snapshots"),
        "soil_enrichment_available_snapshot_count": _external_api_safe_count(db, "soil_enrichment_snapshots", "status = 'AVAILABLE'"),
        "soil_enrichment_job_audit_count": _external_api_safe_count(db, "soil_enrichment_job_audit_events"),
        "soil_enrichment_failed_job_audit_count": _external_api_safe_count(db, "soil_enrichment_job_audit_events", "status = 'FAILED'"),
        "field_event_external_api_count": _external_api_safe_count(db, "field_event_reports", "source = 'EXTERNAL_API'"),
        "providers_ready_for_live_runtime_count": sum(1 for row in provider_rows if row["ready_for_runtime_use"]),
    }

    return {
        "summary": summary,
        "provider_rows": provider_rows[:20],
        "readiness": {
            "ready_for_admin_review": True,
            "ready_for_weather_runtime_provider_execution": summary["weather_live_execution_enabled_count"] > 0,
            "ready_for_soil_runtime_provider_execution": False,
            "ready_for_external_api_runtime_use": summary["providers_ready_for_live_runtime_count"] > 0,
            "ready_for_android_behavior_change": False,
            "requires_provider_credentials_review": True,
            "requires_live_execution_policy_approval": True,
            "requires_rate_limit_and_cost_guardrails": True,
            "requires_worker_scheduler_enablement_review": True,
            "requires_failure_retry_audit_review": True,
        },
        "runtime_policy": {
            "central_http_boundary": "app.modules.media.provider_http_client.execute_provider_http_request",
            "live_execution_default": "BLOCKED_UNTIL_APPROVED",
            "retryable_http_statuses": [408, 425, 429, 500, 502, 503, 504],
            "non_retryable_http_statuses": [400, 401, 403, 404, 422],
        },
        "guardrails": {
            "external_api_called": False,
            "provider_worker_executed": False,
            "provider_config_changed": False,
            "provider_live_execution_enabled": False,
            "db_writes_attempted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }


def _build_project_boundary_readiness_rollup(db: Session) -> dict[str, Any]:
    """Read-only project boundary readiness rollup for the geography admin matrix."""

    projects = _project_boundary_rows(
        db,
        """
        select
          id::text as project_id,
          tenant_id::text as tenant_id,
          name as project_name,
          status::text as project_status,
          geography_scope
        from projects
        where is_active = true
        order by created_at desc nulls last, name asc
        limit 200
        """,
    )

    raw = dict(
        db.execute(
            text("""
                select
                  (select count(*)::bigint from projects where is_active = true) as active_project_count,
                  (select count(*)::bigint from projects where is_active = true and geography_scope is not null and geography_scope::text not in ('{}', 'null', '[]')) as projects_with_non_empty_geography_scope_count,
                  (select count(*)::bigint from geography_boundary_project_matches where is_active = true) as active_project_boundary_match_count,
                  (select count(*)::bigint from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id where b.source_system = :source_system) as raw_boundary_candidate_count,
                  (select count(*)::bigint from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id join geography_boundary_source_features f on f.id = c.source_feature_id where b.source_system = :source_system and f.geometry_validation_status = 'VALIDATED' and c.candidate_bucket = 'DIRECT_VLCODE_MATCH' and c.review_status = 'AUTO_CANDIDATE' and c.promotion_status = 'NOT_PROMOTED' and c.is_active = false and c.proposed_village_id is not null) as raw_eligible_boundary_candidate_count
            """),
            {"source_system": PROJECT_BOUNDARY_SOURCE_SYSTEM},
        ).mappings().one()
    )

    project_rows: list[dict[str, Any]] = []
    for project in projects:
        scope = project.get("geography_scope") or {}
        if isinstance(scope, str):
            try:
                scope = json.loads(scope)
            except Exception:
                scope = {}
        if not isinstance(scope, dict):
            scope = {}

        counts = _project_boundary_scope_counts_for_project(db, project["project_id"], scope)
        resolved = int(counts["scope_resolved_village_count"] or 0)
        covered = int(counts["scope_villages_with_eligible_boundary_count"] or 0)
        eligible = int(counts["scope_eligible_boundary_candidate_count"] or 0)

        project_rows.append({
            "project_id": project["project_id"],
            "tenant_id": project["tenant_id"],
            "project_name": project["project_name"],
            "project_status": project["project_status"],
            "scope_resolved_village_count": resolved,
            "villages_with_eligible_boundary_count": covered,
            "villages_without_eligible_boundary_count": max(resolved - covered, 0),
            "eligible_boundary_candidate_count": eligible,
            "eligible_boundary_coverage_ratio": round(covered / resolved, 6) if resolved else 0,
            "scope_sources": counts.get("scope_sources", []),
            "ready_for_project_boundary_dry_run": resolved > 0 and eligible > 0,
            "ready_for_project_boundary_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_android_behavior_change": False,
        })

    project_rows.sort(
        key=lambda row: (
            -int(row["scope_resolved_village_count"] or 0),
            -int(row["eligible_boundary_candidate_count"] or 0),
            row["project_name"],
        )
    )

    summary = {key: int(value or 0) for key, value in raw.items()}
    summary.update({
        "project_count_in_rollup": len(project_rows),
        "projects_with_resolved_scope_count": sum(1 for row in project_rows if row["scope_resolved_village_count"] > 0),
        "projects_ready_for_project_boundary_dry_run_count": sum(1 for row in project_rows if row["ready_for_project_boundary_dry_run"]),
        "scope_resolved_village_count": sum(row["scope_resolved_village_count"] for row in project_rows),
        "scope_villages_with_eligible_boundary_count": sum(row["villages_with_eligible_boundary_count"] for row in project_rows),
        "scope_villages_without_eligible_boundary_count": sum(row["villages_without_eligible_boundary_count"] for row in project_rows),
        "scope_eligible_boundary_candidate_count": sum(row["eligible_boundary_candidate_count"] for row in project_rows),
    })

    return {
        "summary": summary,
        "top_projects": project_rows[:10],
        "scope_resolution_policy": {
            "state_scope_used_only_without_narrower_scope": True,
            "state_field_qualifies_district_and_village_name_scopes": True,
            "supported_scope_keys": [
                "village_lgd_codes",
                "village_names",
                "pin_codes",
                "district_lgd_codes",
                "districts",
                "state_lgd_codes",
                "state_ids",
                "state",
            ],
        },
        "readiness": {
            "ready_for_admin_review": True,
            "ready_for_project_boundary_dry_run": summary["projects_ready_for_project_boundary_dry_run_count"] > 0,
            "ready_for_project_boundary_apply": False,
            "ready_for_selected_boundary_runtime_promotion": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_android_behavior_change": False,
        },
    }




def _build_boundary_geometry_validation_readiness_rollup(
    db: Session,
    state_or_ut: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Read-only NWDP boundary geometry validation readiness rollup."""

    where = ["b.source_system = :source_system"]
    params: dict[str, Any] = {
        "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
        "state_or_ut": (state_or_ut or "").strip(),
        "district": (district or "").strip(),
    }

    if params["state_or_ut"]:
        where.append("lower(trim(coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut))) = lower(trim(:state_or_ut))")
    if params["district"]:
        where.append("lower(trim(coalesce(d.canonical_name, sf.source_district_name))) = lower(trim(:district))")

    where_sql = " and ".join(where)

    summary = dict(db.execute(text(f"""
        with candidates as (
          select
            c.id,
            c.source_feature_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status,
            c.is_active,
            c.proposed_village_id,
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
          count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') in ('NOT_VALIDATED', 'UNKNOWN'))::bigint as not_validated_geometry_count,
          count(*) filter (where coalesce(geometry_validation_status, 'UNKNOWN') in ('INVALID', 'INVALID_GEOMETRY', 'VALIDATION_FAILED'))::bigint as confirmed_invalid_geometry_count,
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
    """), params).mappings().one())

    status_rows = [
        dict(row)
        for row in db.execute(text(f"""
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
            limit 20
        """), params).mappings()
    ]

    summary = {key: int(value or 0) for key, value in summary.items()}
    for row in status_rows:
        for key in ("candidate_count", "direct_vlcode_match_count", "auto_candidate_count", "manual_review_count", "blocked_count"):
            row[key] = int(row.get(key) or 0)

    return {
        "summary": summary,
        "status_rows": status_rows,
        "validation_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "valid_geometry_statuses": list(_BOUNDARY_VALID_GEOMETRY_STATUSES),
            "requires_runtime_eligible_source": True,
            "requires_direct_vlcode_match": True,
            "requires_auto_candidate_review_status": True,
            "requires_not_promoted": True,
            "requires_inactive_candidate": True,
            "requires_proposed_village_id": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "geometry_repair_supported_by_this_rollup": False,
            "runtime_promotion_supported_by_this_rollup": False,
            "android_behavior_change_supported_by_this_rollup": False,
        },
        "readiness": {
            "ready_for_admin_geometry_review": summary["candidate_count"] > 0,
            "ready_for_geometry_repair_plan": summary["not_validated_geometry_count"] > 0 or summary["confirmed_invalid_geometry_count"] > 0 or summary["not_runtime_eligible_source_count"] > 0,
            "ready_for_selected_runtime_promotion_dry_run": summary["selected_runtime_promotable_count"] > 0,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "requires_valid_geometry_before_runtime_promotion": True,
            "requires_runtime_eligible_source_before_runtime_promotion": True,
            "requires_state_or_district_scope_before_apply": True,
            "requires_rollback_or_supersession_plan": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "geometry_repair_attempted": False,
            "source_features_changed": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
    }



def _build_boundary_geometry_repair_classification_rollup(
    db: Session,
    state_or_ut: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Read-only boundary geometry repair classification rollup."""

    where = ["b.source_system = :source_system"]
    params: dict[str, Any] = {
        "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
        "state_or_ut": (state_or_ut or "").strip(),
        "district": (district or "").strip(),
    }

    if params["state_or_ut"]:
        where.append("lower(trim(coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut))) = lower(trim(:state_or_ut))")
    if params["district"]:
        where.append("lower(trim(coalesce(d.canonical_name, sf.source_district_name))) = lower(trim(:district))")

    where_sql = " and ".join(where)
    classification = _boundary_repair_classification_case()
    action = _boundary_repair_action_case()

    summary = dict(db.execute(text(f"""
        with classified as (
          select
            c.id,
            c.source_feature_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status,
            c.is_active,
            c.proposed_village_id,
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
        dict(row)
        for row in db.execute(text(f"""
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
            limit 20
        """), params).mappings()
    ]

    summary = {key: int(value or 0) for key, value in summary.items()}
    for row in classification_rows:
        for key, value in list(row.items()):
            if key.endswith("_count"):
                row[key] = int(value or 0)

    return {
        "summary": summary,
        "classification_rows": classification_rows,
        "classification_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "valid_geometry_statuses": list(_BOUNDARY_VALID_GEOMETRY_STATUSES),
            "runtime_promotion_requires_valid_geometry": True,
            "runtime_promotion_requires_runtime_eligible_source": True,
            "runtime_promotion_requires_direct_auto_not_promoted_inactive_candidate": True,
            "state_or_district_scope_required_before_apply": True,
            "rollback_or_supersession_plan_required_before_apply": True,
            "geometry_repair_supported_by_this_rollup": False,
            "runtime_promotion_supported_by_this_rollup": False,
            "android_behavior_change_supported_by_this_rollup": False,
        },
        "readiness": {
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
        },
        "guardrails": {
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
        },
    }

def _build_boundary_geometry_repair_event_rollup(
    db: Session,
    state_or_ut: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Read-only audit rollup for boundary geometry repair events."""

    table_present = bool(
        db.execute(
            text(
                "select to_regclass("
                "'public.geography_boundary_geometry_repair_events'"
                ") is not null"
            )
        ).scalar()
    )

    summary = {
        "repair_event_table_present": table_present,
        "repair_event_count": 0,
        "active_repair_event_count": 0,
        "applied_repair_event_count": 0,
        "rolled_back_repair_event_count": 0,
        "tiny_fixture_repair_event_count": 0,
        "active_tiny_fixture_repair_event_count": 0,
    }
    recent_events: list[dict[str, Any]] = []

    if table_present:
        where = ["1 = 1"]
        params: dict[str, Any] = {
            "state_or_ut": (state_or_ut or "").strip(),
            "district": (district or "").strip(),
            "tiny_fixture_method": "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY",
        }

        if params["state_or_ut"]:
            where.append(
                "lower(trim(coalesce(state_or_ut, ''))) = "
                "lower(trim(:state_or_ut))"
            )
        if params["district"]:
            where.append(
                "lower(trim(coalesce(district, ''))) = "
                "lower(trim(:district))"
            )

        where_sql = " and ".join(where)

        counts = dict(
            db.execute(
                text(f"""
                    select
                      count(*)::bigint as repair_event_count,
                      count(*) filter (
                        where is_active = true
                      )::bigint as active_repair_event_count,
                      count(*) filter (
                        where repair_status = 'APPLIED'
                      )::bigint as applied_repair_event_count,
                      count(*) filter (
                        where repair_status = 'ROLLED_BACK'
                      )::bigint as rolled_back_repair_event_count,
                      count(*) filter (
                        where repair_method = :tiny_fixture_method
                      )::bigint as tiny_fixture_repair_event_count,
                      count(*) filter (
                        where repair_method = :tiny_fixture_method
                          and is_active = true
                      )::bigint as active_tiny_fixture_repair_event_count
                    from geography_boundary_geometry_repair_events
                    where {where_sql}
                """),
                params,
            ).mappings().one()
        )

        summary.update({
            key: int(value or 0)
            for key, value in counts.items()
        })

        recent_events = [
            dict(row)
            for row in db.execute(
                text(f"""
                    select
                      id::text as repair_event_id,
                      source_feature_id::text as source_feature_id,
                      source_system,
                      state_or_ut,
                      district,
                      repair_action,
                      repair_status,
                      repair_method,
                      rollback_token,
                      applied_at,
                      rolled_back_at,
                      is_active
                    from geography_boundary_geometry_repair_events
                    where {where_sql}
                    order by coalesce(
                      rolled_back_at,
                      applied_at,
                      created_at
                    ) desc, id
                    limit 20
                """),
                params,
            ).mappings()
        ]

        for row in recent_events:
            for key in ("applied_at", "rolled_back_at"):
                if row.get(key) is not None:
                    row[key] = row[key].isoformat()

    return {
        "summary": summary,
        "recent_events": recent_events,
        "audit_policy": {
            "read_only_rollup": True,
            "target_table": "geography_boundary_geometry_repair_events",
            "tiny_fixture_repair_method": (
                "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY"
            ),
            "broad_geometry_repair_enabled": False,
            "selected_runtime_promotion_separately_gated": True,
        },
        "readiness": {
            "ready_for_admin_audit_review": table_present,
            "ready_for_broad_geometry_repair_apply": False,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "guardrails": {
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
        },
    }


def _build_selected_boundary_runtime_promotion_readiness_rollup(
    db: Session,
    state_or_ut: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Read-only selected NWDP boundary runtime promotion readiness rollup."""

    where = ["b.source_system = :source_system"]
    params: dict[str, Any] = {
        "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
        "state_or_ut": (state_or_ut or "").strip(),
        "district": (district or "").strip(),
    }

    if params["state_or_ut"]:
        where.append("lower(trim(coalesce(s.canonical_name, sf.source_state_name, b.state_or_ut))) = lower(trim(:state_or_ut))")
    if params["district"]:
        where.append("lower(trim(coalesce(d.canonical_name, sf.source_district_name))) = lower(trim(:district))")

    where_sql = " and ".join(where)

    summary = dict(db.execute(text(f"""
        with candidates as (
          select
            c.id,
            c.source_feature_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status,
            c.is_active,
            c.proposed_village_id,
            sf.geometry_validation_status,
            sf.eligible_for_runtime_after_promotion
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
    """), params).mappings().one())

    summary = {key: int(value or 0) for key, value in summary.items()}
    return {
        "summary": summary,
        "candidate_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "candidate_bucket": "DIRECT_VLCODE_MATCH",
            "review_status": "AUTO_CANDIDATE",
            "promotion_status": "NOT_PROMOTED",
            "required_is_active": False,
            "requires_proposed_village_id": True,
            "requires_source_feature": True,
            "requires_runtime_eligible_source_feature": True,
            "allowed_geometry_validation_statuses": ["VALID", "VALIDATED", "VALID_WITH_WARNINGS"],
        },
        "readiness": {
            "ready_for_selected_runtime_promotion_dry_run": summary["selected_runtime_promotable_count"] > 0,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "requires_admin_review_before_apply": True,
            "requires_rollback_or_supersession_plan": True,
            "requires_state_or_district_scope_before_apply": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
    }


def _build_geography_layer_readiness_matrix(
    db: Session,
    state_or_ut: Optional[str] = None,
    district: Optional[str] = None,
    limit: int = 5000,
) -> dict:
    """Read-only state/district cross-layer geography readiness matrix."""

    source_system = "NWDP_GSI_VILLAGE_BOUNDARY"
    source_version = "20260824T110250Z"

    where = ["s.is_active = true", "d.is_active = true"]
    params: dict[str, Any] = {
        "limit": limit,
        "source_system": source_system,
        "source_version": source_version,
    }

    if state_or_ut:
        where.append("lower(trim(s.canonical_name)) = lower(trim(:state_or_ut))")
        params["state_or_ut"] = state_or_ut
    if district:
        where.append("lower(trim(d.canonical_name)) = lower(trim(:district))")
        params["district"] = district

    where_sql = " and ".join(where)

    sql = f"""
        with base as (
          select
            s.id as state_id,
            d.id as district_id,
            s.canonical_name as state_or_ut,
            d.canonical_name as district,
            s.lgd_code::text as state_lgd_code,
            d.lgd_code::text as district_lgd_code,
            count(v.id)::bigint as lgd_village_count
          from geography_states s
          join geography_districts d on d.state_id = s.id
          left join geography_villages v
            on v.district_id = d.id
           and v.is_active = true
          where {where_sql}
          group by s.id, d.id, s.canonical_name, d.canonical_name, s.lgd_code, d.lgd_code
        ),
        pin_by_district as (
          select
            v.district_id,
            count(distinct vpl.geography_village_id)::bigint as pin_linked_village_count,
            count(*)::bigint as pin_link_count
          from geography_village_pin_links vpl
          join geography_villages v on v.id = vpl.geography_village_id
          where vpl.is_active = true
            and vpl.match_status = 'MATCHED'
          group by v.district_id
        ),
        demo_by_district as (
          select
            v.district_id,
            count(*)::bigint as demographic_profile_row_count,
            count(*) filter (
              where p.review_status = 'APPROVED_FOR_PROMOTION'
                and p.promotion_status = 'PROMOTED'
                and p.is_active = true
            )::bigint as demographic_active_promoted_count,
            count(*) filter (where p.review_status = 'BLOCKED')::bigint as demographic_blocked_count,
            count(*) filter (
              where p.review_status = 'APPROVED_FOR_PROMOTION'
                and p.promotion_status = 'NOT_PROMOTED'
                and p.is_active = false
            )::bigint as demographic_remaining_eligible_count
          from geography_village_demographic_profiles p
          join geography_villages v on v.id = p.village_id
          where p.source_system = :source_system
            and p.source_version = :source_version
          group by v.district_id
        ),
        boundary_candidate_keys as (
          select
            c.id,
            coalesce(d_code.id, d_name.id) as district_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status
          from geography_boundary_crosswalk_candidates c
          left join geography_boundary_source_features sf on sf.id = c.source_feature_id
          left join geography_districts d_code
            on d_code.lgd_code::text = c.proposed_district_lgd_code::text
          left join geography_states s_code
            on s_code.id = d_code.state_id
           and s_code.lgd_code::text = c.proposed_state_lgd_code::text
          left join geography_states s_name
            on lower(trim(s_name.canonical_name)) = lower(trim(sf.source_state_name))
          left join geography_districts d_name
            on d_name.state_id = s_name.id
           and lower(trim(d_name.canonical_name)) = lower(trim(sf.source_district_name))
          where coalesce(d_code.id, d_name.id) is not null
        ),
        boundary_by_district as (
          select
            district_id,
            count(*)::bigint as boundary_candidate_count,
            count(*) filter (where candidate_bucket = 'DIRECT_VLCODE_MATCH')::bigint as boundary_direct_vlcode_match_count,
            count(*) filter (where review_status = 'AUTO_CANDIDATE')::bigint as boundary_auto_candidate_count,
            count(*) filter (where review_status = 'MANUAL_REVIEW')::bigint as boundary_manual_review_count,
            count(*) filter (where review_status = 'BLOCKED')::bigint as boundary_blocked_count,
            count(*) filter (where promotion_status = 'PROMOTED')::bigint as boundary_promoted_candidate_count
          from boundary_candidate_keys
          group by district_id
        ),
        runtime_by_district as (
          select
            district_id,
            count(*)::bigint as boundary_runtime_crosswalk_count,
            count(distinct runtime_feature_id)::bigint as boundary_runtime_feature_count
          from geography_boundary_runtime_crosswalks
          where is_active = true
          group by district_id
        ),
        project_boundary_by_district as (
          select
            v.district_id,
            count(*)::bigint as project_boundary_match_count
          from geography_boundary_project_matches pm
          join geography_villages v on v.id = pm.village_id
          where pm.is_active = true
          group by v.district_id
        ),
        climate_mapping_districts as (
          select distinct m.id, d.id as district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_states s on s.lgd_code::text = m.state_lgd_code::text
          join geography_districts d
            on d.state_id = s.id
           and d.lgd_code::text = m.district_lgd_code::text
          where m.is_active = true
            and m.district_lgd_code is not null

          union

          select distinct m.id, v.district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_villages v on v.lgd_code::text = m.village_lgd_code::text
          join geography_districts d on d.id = v.district_id
          join geography_states s on s.id = d.state_id
          where m.is_active = true
            and m.village_lgd_code is not null
            and (m.state_lgd_code is null or s.lgd_code::text = m.state_lgd_code::text)

          union

          select distinct m.id, d.id as district_id, m.region_code
          from geography_climate_region_mappings m
          join geography_states s on s.lgd_code::text = m.state_lgd_code::text
          join geography_districts d on d.state_id = s.id
          where m.is_active = true
            and m.district_lgd_code is null
            and m.village_lgd_code is null
            and m.scope_level = 'STATE'
        ),
        climate_by_district as (
          select
            cmd.district_id,
            count(distinct cmd.id)::bigint as climate_mapping_count,
            count(distinct cmd.region_code)::bigint as climate_region_count,
            count(distinct r.id)::bigint as crop_climate_rule_count
          from climate_mapping_districts cmd
          left join crop_climate_suitability_rules r
            on r.region_code = cmd.region_code
           and r.is_active = true
          group by cmd.district_id
        )
        select
          b.state_or_ut,
          b.district,
          b.state_lgd_code,
          b.district_lgd_code,
          b.lgd_village_count,

          coalesce(pin.pin_linked_village_count, 0) as pin_linked_village_count,
          coalesce(pin.pin_link_count, 0) as pin_link_count,

          coalesce(demo.demographic_profile_row_count, 0) as demographic_profile_row_count,
          coalesce(demo.demographic_active_promoted_count, 0) as demographic_active_promoted_count,
          coalesce(demo.demographic_blocked_count, 0) as demographic_blocked_count,
          coalesce(demo.demographic_remaining_eligible_count, 0) as demographic_remaining_eligible_count,

          coalesce(boundary.boundary_candidate_count, 0) as boundary_candidate_count,
          coalesce(boundary.boundary_direct_vlcode_match_count, 0) as boundary_direct_vlcode_match_count,
          coalesce(boundary.boundary_auto_candidate_count, 0) as boundary_auto_candidate_count,
          coalesce(boundary.boundary_manual_review_count, 0) as boundary_manual_review_count,
          coalesce(boundary.boundary_blocked_count, 0) as boundary_blocked_count,
          coalesce(boundary.boundary_promoted_candidate_count, 0) as boundary_promoted_candidate_count,

          coalesce(runtime.boundary_runtime_crosswalk_count, 0) as boundary_runtime_crosswalk_count,
          coalesce(runtime.boundary_runtime_feature_count, 0) as boundary_runtime_feature_count,

          coalesce(project_boundary.project_boundary_match_count, 0) as project_boundary_match_count,

          coalesce(climate.climate_mapping_count, 0) as climate_mapping_count,
          coalesce(climate.climate_region_count, 0) as climate_region_count,
          coalesce(climate.crop_climate_rule_count, 0) as crop_climate_rule_count

        from base b
        left join pin_by_district pin on pin.district_id = b.district_id
        left join demo_by_district demo on demo.district_id = b.district_id
        left join boundary_by_district boundary on boundary.district_id = b.district_id
        left join runtime_by_district runtime on runtime.district_id = b.district_id
        left join project_boundary_by_district project_boundary on project_boundary.district_id = b.district_id
        left join climate_by_district climate on climate.district_id = b.district_id
        order by b.state_or_ut, b.district
        limit :limit
    """

    rows = [dict(row) for row in db.execute(text(sql), params).mappings()]
    int_fields = [key for key in rows[0].keys() if key.endswith("_count")] if rows else []

    normalized = []
    for row in rows:
        clean = dict(row)
        for field in int_fields:
            clean[field] = int(clean[field] or 0)

        clean["lgd_runtime_ready"] = True
        clean["pin_code_runtime_ready"] = clean["pin_linked_village_count"] > 0
        clean["demographic_admin_ready"] = clean["demographic_active_promoted_count"] > 0
        clean["demographic_android_enabled"] = False
        clean["boundary_admin_review_ready"] = clean["boundary_candidate_count"] > 0
        clean["boundary_runtime_ready"] = False
        clean["boundary_runtime_pilot_present"] = clean["boundary_runtime_feature_count"] > 0
        clean["project_boundary_matching_ready"] = clean["project_boundary_match_count"] > 0
        clean["climate_admin_review_ready"] = clean["climate_mapping_count"] > 0
        clean["climate_runtime_ready"] = clean["climate_mapping_count"] > 0 and clean["crop_climate_rule_count"] > 0
        clean["soi_direct_join_safe"] = False
        clean["bharatlas_operational_review_source"] = True
        normalized.append(clean)

    summary: dict[str, Any] = {"state_district_row_count": len(normalized)}
    for key in int_fields:
        summary[key] = sum(row[key] for row in normalized)

    raw_totals_sql = """
        select
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as raw_boundary_candidate_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'AUTO_CANDIDATE') as raw_boundary_auto_candidate_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'MANUAL_REVIEW') as raw_boundary_manual_review_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where review_status = 'BLOCKED') as raw_boundary_blocked_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where candidate_bucket = 'DIRECT_VLCODE_MATCH') as raw_boundary_direct_vlcode_match_count,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as raw_boundary_promoted_candidate_count,
          (select count(*)::bigint from geography_village_demographic_profiles where source_system = :source_system and source_version = :source_version) as raw_demographic_profile_row_count,
          (select count(*)::bigint from geography_village_demographic_profiles where source_system = :source_system and source_version = :source_version and review_status = 'APPROVED_FOR_PROMOTION' and promotion_status = 'PROMOTED' and is_active = true) as raw_demographic_active_promoted_count,
          (select count(*)::bigint from geography_village_pin_links where is_active = true and match_status = 'MATCHED') as raw_pin_link_count,
          (select count(distinct geography_village_id)::bigint from geography_village_pin_links where is_active = true and match_status = 'MATCHED') as raw_pin_linked_village_count,
          (select count(*)::bigint from geography_climate_regions where is_active = true) as raw_active_climate_region_count,
          (select count(distinct region_system)::bigint from geography_climate_regions where is_active = true) as raw_active_region_system_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true) as raw_active_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'STATE') as raw_state_scope_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'DISTRICT') as raw_district_scope_climate_mapping_count,
          (select count(*)::bigint from geography_climate_region_mappings where is_active = true and scope_level = 'VILLAGE') as raw_village_scope_climate_mapping_count,
          (select count(*)::bigint from crop_climate_suitability_rules where is_active = true) as raw_active_crop_climate_rule_count,
          (select count(distinct crop_code)::bigint from crop_climate_suitability_rules where is_active = true) as raw_crops_with_climate_rule_count,
          (select count(*)::bigint from crops where is_active = true) as raw_active_crop_count,
          (select count(*)::bigint from crop_climate_suitability_overrides where is_active = true) as raw_active_crop_climate_override_count,
          (
            select count(*)::bigint
            from geography_climate_regions r
            where r.is_active = true
              and not exists (
                select 1
                from crop_climate_suitability_rules rule
                where rule.region_code = r.region_code
                  and rule.is_active = true
              )
          ) as raw_regions_without_active_rules_count,
          (
            select count(*)::bigint
            from crops c
            where c.is_active = true
              and not exists (
                select 1
                from crop_climate_suitability_rules rule
                where rule.crop_code = c.code
                  and rule.is_active = true
              )
          ) as raw_active_crops_without_climate_rules_count
    """
    raw_totals = {
        key: int(value or 0)
        for key, value in dict(db.execute(text(raw_totals_sql), params).mappings().one()).items()
    }

    gap_accounting = {
        "boundary_candidate_raw_count": raw_totals["raw_boundary_candidate_count"],
        "boundary_candidate_matrix_count": summary["boundary_candidate_count"],
        "boundary_candidate_outside_state_district_matrix_count": max(raw_totals["raw_boundary_candidate_count"] - summary["boundary_candidate_count"], 0),
        "boundary_auto_candidate_raw_count": raw_totals["raw_boundary_auto_candidate_count"],
        "boundary_auto_candidate_matrix_count": summary["boundary_auto_candidate_count"],
        "boundary_manual_review_raw_count": raw_totals["raw_boundary_manual_review_count"],
        "boundary_manual_review_matrix_count": summary["boundary_manual_review_count"],
        "boundary_blocked_raw_count": raw_totals["raw_boundary_blocked_count"],
        "boundary_blocked_matrix_count": summary["boundary_blocked_count"],
        "boundary_direct_vlcode_match_raw_count": raw_totals["raw_boundary_direct_vlcode_match_count"],
        "boundary_direct_vlcode_match_matrix_count": summary["boundary_direct_vlcode_match_count"],
        "boundary_promoted_candidate_raw_count": raw_totals["raw_boundary_promoted_candidate_count"],
        "boundary_promoted_candidate_matrix_count": summary["boundary_promoted_candidate_count"],
        "demographic_profile_raw_count": raw_totals["raw_demographic_profile_row_count"],
        "demographic_profile_matrix_count": summary["demographic_profile_row_count"],
        "demographic_profile_outside_state_district_matrix_count": max(raw_totals["raw_demographic_profile_row_count"] - summary["demographic_profile_row_count"], 0),
        "demographic_active_promoted_raw_count": raw_totals["raw_demographic_active_promoted_count"],
        "demographic_active_promoted_matrix_count": summary["demographic_active_promoted_count"],
        "pin_link_raw_count": raw_totals["raw_pin_link_count"],
        "pin_link_matrix_count": summary["pin_link_count"],
        "pin_link_outside_state_district_matrix_count": max(raw_totals["raw_pin_link_count"] - summary["pin_link_count"], 0),
        "pin_linked_village_raw_count": raw_totals["raw_pin_linked_village_count"],
        "pin_linked_village_matrix_count": summary["pin_linked_village_count"],
    }

    districts_with_climate_mapping = sum(1 for row in normalized if row["climate_mapping_count"] > 0)
    districts_with_crop_climate_rules = sum(1 for row in normalized if row["crop_climate_rule_count"] > 0)
    districts_without_climate_mapping = len(normalized) - districts_with_climate_mapping
    districts_without_crop_climate_rules = len(normalized) - districts_with_crop_climate_rules

    climate_readiness = {
        "active_climate_region_count": raw_totals["raw_active_climate_region_count"],
        "active_region_system_count": raw_totals["raw_active_region_system_count"],
        "active_climate_mapping_count": raw_totals["raw_active_climate_mapping_count"],
        "state_scope_mapping_count": raw_totals["raw_state_scope_climate_mapping_count"],
        "district_scope_mapping_count": raw_totals["raw_district_scope_climate_mapping_count"],
        "village_scope_mapping_count": raw_totals["raw_village_scope_climate_mapping_count"],
        "active_crop_climate_rule_count": raw_totals["raw_active_crop_climate_rule_count"],
        "active_crop_count": raw_totals["raw_active_crop_count"],
        "crops_with_climate_rule_count": raw_totals["raw_crops_with_climate_rule_count"],
        "active_crops_without_climate_rules_count": raw_totals["raw_active_crops_without_climate_rules_count"],
        "active_crop_climate_override_count": raw_totals["raw_active_crop_climate_override_count"],
        "regions_without_active_rules_count": raw_totals["raw_regions_without_active_rules_count"],
        "districts_with_climate_mapping": districts_with_climate_mapping,
        "districts_without_climate_mapping": districts_without_climate_mapping,
        "districts_with_crop_climate_rules": districts_with_crop_climate_rules,
        "districts_without_crop_climate_rules": districts_without_crop_climate_rules,
        "climate_mapping_district_coverage_ratio": round(districts_with_climate_mapping / len(normalized), 6) if normalized else 0.0,
        "crop_climate_rule_district_coverage_ratio": round(districts_with_crop_climate_rules / len(normalized), 6) if normalized else 0.0,
        "ready_for_admin_review": raw_totals["raw_active_climate_mapping_count"] > 0,
        "ready_for_runtime_enablement": (
            districts_without_climate_mapping == 0
            and districts_without_crop_climate_rules == 0
            and raw_totals["raw_regions_without_active_rules_count"] == 0
            and raw_totals["raw_active_crops_without_climate_rules_count"] == 0
        ),
        "ready_for_android_behavior_change": False,
    }

    project_boundary_readiness = _build_project_boundary_readiness_rollup(db)
    boundary_geometry_validation_readiness = _build_boundary_geometry_validation_readiness_rollup(db, state_or_ut, district)
    boundary_geometry_repair_classification = _build_boundary_geometry_repair_classification_rollup(db, state_or_ut, district)
    boundary_geometry_repair_events = _build_boundary_geometry_repair_event_rollup(db, state_or_ut, district)
    selected_boundary_runtime_promotion_readiness = _build_selected_boundary_runtime_promotion_readiness_rollup(db, state_or_ut, district)
    external_api_readiness = _build_external_api_readiness_rollup(db)

    return {
        "schema_version": "geography_layer_readiness_matrix.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": len(normalized) > 0,
        "mode": "READ_ONLY_STATE_DISTRICT_GEOGRAPHY_LAYER_READINESS_MATRIX",
        "filters": {
            "state_or_ut": state_or_ut,
            "district": district,
            "limit": limit,
        },
        "summary": summary,
        "gap_accounting": gap_accounting,
        "climate_readiness": climate_readiness,
        "project_boundary_readiness": project_boundary_readiness,
        "boundary_geometry_validation_readiness": boundary_geometry_validation_readiness,
        "boundary_geometry_repair_classification": boundary_geometry_repair_classification,
        "boundary_geometry_repair_events": boundary_geometry_repair_events,
        "selected_boundary_runtime_promotion_readiness": selected_boundary_runtime_promotion_readiness,
        "external_api_readiness": external_api_readiness,
        "rows": normalized,
        "source_posture": {
            "lgd_is_canonical_runtime_identity": True,
            "village_pin_codes_android_ready": True,
            "nwdp_demographic_android_enabled": False,
            "nwdp_boundary_runtime_lookup_enabled": False,
            "soi_direct_lgd_join_safe": False,
            "bharatlas_operational_review_source": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "lgd_geography_overwritten": False,
            "nwdp_demographic_android_enabled": False,
            "nwdp_boundary_runtime_lookup_enabled": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
        },
        "recommended_next_steps": [
            "Use this read-only endpoint to power the admin geography layer readiness page.",
            "Prioritize boundary outside-matrix gaps before broad runtime boundary promotion.",
            "Use boundary geometry validation readiness to separate invalid geometry repair work from runtime promotion work.",
            "Use boundary geometry repair classification to split validation, re-import, runtime-eligibility, crosswalk review, and exclusion work.",
            "Keep selected boundary runtime promotion blocked until source geometry is validated and marked runtime eligible.",
            "Keep external provider execution blocked until credentials, live-execution policy, rate-limit, cost, scheduler, and failure-audit guardrails are reviewed.",
            "Implement project boundary matching only through dry-run, explicit apply flag, audit output, and rollback/supersession plan.",
            "Keep NWDP demographic and NWDP boundary data disabled for Android unless explicitly changed later.",
        ],
    }


# --- Response Schemas ---

class StateResponse(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    census_name: Optional[str] = None

    class Config:
        from_attributes = True


class DistrictResponse(BaseModel):
    id: UUID
    lgd_code: str
    state_id: UUID
    canonical_name: str
    census_name: Optional[str] = None

    class Config:
        from_attributes = True


class BlockResponse(BaseModel):
    id: UUID
    lgd_code: str
    district_id: UUID
    canonical_name: str

    class Config:
        from_attributes = True


class VillageResponse(BaseModel):
    id: UUID
    lgd_code: str
    block_id: UUID
    district_id: UUID
    canonical_name: str
    census_name: Optional[str] = None
    pin_codes: Optional[list[str]] = None

    class Config:
        from_attributes = True


class VillageSearchResult(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    block_id: UUID
    block_name: str
    district_id: UUID
    district_name: str
    state_id: UUID
    state_name: str
    pin_codes: Optional[list[str]] = None
    similarity: float
    match_type: str

    class Config:
        from_attributes = True


class PinCodeVillageResponse(BaseModel):
    id: UUID
    lgd_code: str
    canonical_name: str
    block_id: UUID
    block_name: str
    district_id: UUID
    district_name: str
    state_id: UUID
    state_name: str
    pin_codes: Optional[list[str]] = None

    class Config:
        from_attributes = True


class PinCodePostalReferenceResponse(BaseModel):
    office_name: str
    office_type: Optional[str] = None
    delivery_status: Optional[str] = None
    postal_district_name: Optional[str] = None
    postal_state_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PinCodeLookupResponse(BaseModel):
    schema_version: str = "pin_code_lookup.v1"
    pin_code: str
    is_valid_postal_pin: bool
    has_lgd_village_candidates: bool
    status_reason: str
    message: str
    village_candidate_count: int
    postal_reference_count: int
    village_candidates: list[PinCodeVillageResponse]
    postal_references: list[PinCodePostalReferenceResponse]


class PaginatedResponse(BaseModel):
    items: list
    total: int
    offset: int
    limit: int


class CoreLgdMappingReviewResponse(BaseModel):
    schema_version: str
    mode: str
    filters: dict
    summary: dict
    decision_counts: list[dict]
    state_counts: list[dict]
    region_system_counts: list[dict]
    items: list[dict]
    total: int
    offset: int
    limit: int
    governance: dict



class CoreLgdMappingReviewSummaryResponse(BaseModel):
    schema_version: str = "core_lgd_mapping_review_summary_admin.v1"
    mode: str = "READ_ONLY_ADMIN_SUMMARY"
    db_writes_made: bool = False
    external_calls_made: bool = False
    active_promoted: dict
    inactive_review_queue: dict
    fallbacks: dict
    readiness: dict


class CoreLgdMappingReviewDecisionRequest(BaseModel):
    review_status: str = Field(..., pattern="^(MANUAL_REVIEW|APPROVED_FOR_PROMOTION|REJECTED)$")
    review_notes: str = Field(..., min_length=3, max_length=1000)


class NwdpBoundaryBatchListResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    filters: dict
    summary: dict
    items: list[dict]
    total: int
    offset: int
    limit: int


class NwdpBoundaryBatchDetailResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    batch: dict
    audit_evidence: dict
    candidate_summary: dict


class NwdpBoundaryCandidateListResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    filters: dict
    summary: dict
    items: list[dict]
    total: int
    offset: int
    limit: int


class NwdpBoundaryCandidateDetailResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    candidate: dict
    source_feature: dict
    proposed_match: dict
    audit_evidence: dict
    review_history: list[dict]
    allowed_review_decisions: list[str]


class NwdpBoundaryRuntimePromotionDryRunResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    filters: dict
    summary: dict
    eligibility_counts: list[dict]
    exclusion_counts: list[dict]
    promotable_samples: list[dict]
    excluded_samples: list[dict]
    readiness: dict


class NwdpBoundaryRuntimePilotInspectionResponse(BaseModel):
    schema_version: str
    mode: str
    governance: dict
    db_writes_attempted: bool
    runtime_tables_written: bool
    runtime_spatial_matching_changed: bool
    android_behavior_changed: bool
    inspection: dict
    readiness: dict



class NwdpDemographicProfileReviewRequest(BaseModel):
    review_status: str = Field(..., pattern="^(MANUAL_REVIEW|APPROVED_FOR_PROMOTION|REJECTED|BLOCKED)$")
    reviewer_decision: str = Field(..., pattern="^(MARK_MANUAL_REVIEW|APPROVE_FOR_PROMOTION|REJECT_PROFILE|BLOCK_PROFILE)$")
    reviewer_notes: str
    evidence_summary: Optional[Dict[str, Any]] = None

class NwdpBoundaryCandidateReviewRequest(BaseModel):
    reviewer_decision: str = Field(
        ...,
        pattern="^(KEEP_PENDING|ACCEPT_DIRECT_CODE_MATCH|ACCEPT_REVIEWED_NAME_MATCH|MARK_REFERENCE_ONLY|REJECT_SOURCE_MISMATCH|REJECT_SPECIAL_FEATURE|BLOCK_PENDING_SOURCE_REVIEW)$",
    )
    review_status: str = Field(
        ...,
        pattern="^(MANUAL_REVIEW|APPROVED_FOR_PROMOTION|REFERENCE_ONLY|REJECTED|BLOCKED)$",
    )
    reviewer_notes: str = Field("", max_length=2000)
    evidence_summary: dict = Field(default_factory=dict)


# --- Endpoints ---

def _nwdp_boundary_governance(db_write_scope: str = "NONE") -> dict:
    return {
        "read_only_runtime": True,
        "promotion_supported": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "db_write_scope": db_write_scope,
        "claim_boundary": "NWDP boundary review endpoints expose inactive staging rows only and do not enable runtime point-in-polygon.",
    }


def _jsonish(value):
    return value if value is not None else {}



def _nwdp_boundary_state_wise_match_summary(db: Session) -> dict:
    state_rows = db.execute(text("""
        with batch_scope as (
          select id, state_or_ut
          from geography_boundary_import_batches
          where source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
        ),
        feature_totals as (
          select
            import_batch_id,
            count(*)::bigint as source_features,
            count(*) filter (where is_active = true)::bigint as active_source_features
          from geography_boundary_source_features
          where import_batch_id in (select id from batch_scope)
          group by import_batch_id
        ),
        candidate_totals as (
          select
            import_batch_id,
            count(*)::bigint as candidates,
            count(*) filter (where is_active = true)::bigint as active_candidates,
            count(*) filter (where promotion_status <> 'NOT_PROMOTED')::bigint as promoted_candidates,
            count(*) filter (
              where candidate_bucket = 'DIRECT_VLCODE_MATCH'
                and review_status = 'AUTO_CANDIDATE'
                and is_active = false
                and promotion_status = 'NOT_PROMOTED'
            )::bigint as future_match_ready_candidates,
            count(*) filter (
              where review_status = 'MANUAL_REVIEW'
                and is_active = false
                and promotion_status = 'NOT_PROMOTED'
            )::bigint as manual_review_candidates,
            count(*) filter (
              where review_status = 'BLOCKED'
                and is_active = false
                and promotion_status = 'NOT_PROMOTED'
            )::bigint as blocked_candidates
          from geography_boundary_crosswalk_candidates
          where import_batch_id in (select id from batch_scope)
          group by import_batch_id
        )
        select
          b.state_or_ut,
          count(distinct b.id)::bigint as batches,
          coalesce(sum(f.source_features), 0)::bigint as source_features,
          coalesce(sum(c.candidates), 0)::bigint as candidates,
          coalesce(sum(f.active_source_features), 0)::bigint as active_source_features,
          coalesce(sum(c.active_candidates), 0)::bigint as active_candidates,
          coalesce(sum(c.promoted_candidates), 0)::bigint as promoted_candidates,
          coalesce(sum(c.future_match_ready_candidates), 0)::bigint as future_match_ready_candidates,
          coalesce(sum(c.manual_review_candidates), 0)::bigint as manual_review_candidates,
          coalesce(sum(c.blocked_candidates), 0)::bigint as blocked_candidates
        from batch_scope b
        left join feature_totals f on f.import_batch_id = b.id
        left join candidate_totals c on c.import_batch_id = b.id
        group by b.state_or_ut
        order by b.state_or_ut
    """)).mappings().all()

    bucket_rows = db.execute(text("""
        select b.state_or_ut, c.candidate_bucket, count(*)::bigint as count
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
        group by b.state_or_ut, c.candidate_bucket
        order by b.state_or_ut, c.candidate_bucket
    """)).mappings().all()

    review_rows = db.execute(text("""
        select b.state_or_ut, c.review_status, count(*)::bigint as count
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
        group by b.state_or_ut, c.review_status
        order by b.state_or_ut, c.review_status
    """)).mappings().all()

    by_state = {}
    for row in state_rows:
        item = {
            "state_or_ut": row["state_or_ut"],
            "batches": int(row["batches"] or 0),
            "source_features": int(row["source_features"] or 0),
            "candidates": int(row["candidates"] or 0),
            "active_source_features": int(row["active_source_features"] or 0),
            "active_candidates": int(row["active_candidates"] or 0),
            "promoted_candidates": int(row["promoted_candidates"] or 0),
            "future_match_ready_candidates": int(row["future_match_ready_candidates"] or 0),
            "manual_review_candidates": int(row["manual_review_candidates"] or 0),
            "blocked_candidates": int(row["blocked_candidates"] or 0),
            "candidate_bucket_counts": {},
            "review_status_counts": {},
            "future_project_matching_allowed_now": False,
            "ready_for_future_project_matching_design": True,
        }
        by_state[item["state_or_ut"]] = item

    for row in bucket_rows:
        if row["state_or_ut"] in by_state:
            by_state[row["state_or_ut"]]["candidate_bucket_counts"][row["candidate_bucket"] or ""] = int(row["count"] or 0)

    for row in review_rows:
        if row["state_or_ut"] in by_state:
            by_state[row["state_or_ut"]]["review_status_counts"][row["review_status"] or ""] = int(row["count"] or 0)

    states = list(by_state.values())
    totals = {
        "state_count": len(states),
        "source_features": sum(item["source_features"] for item in states),
        "candidates": sum(item["candidates"] for item in states),
        "active_source_features": sum(item["active_source_features"] for item in states),
        "active_candidates": sum(item["active_candidates"] for item in states),
        "promoted_candidates": sum(item["promoted_candidates"] for item in states),
        "future_match_ready_candidates": sum(item["future_match_ready_candidates"] for item in states),
        "manual_review_candidates": sum(item["manual_review_candidates"] for item in states),
        "blocked_candidates": sum(item["blocked_candidates"] for item in states),
    }
    healthy = (
        totals["state_count"] == 36
        and totals["source_features"] == 654285
        and totals["candidates"] == 654285
        and totals["active_source_features"] == 0
        and totals["active_candidates"] == 0
        and totals["promoted_candidates"] == 0
    )
    return {"healthy": healthy, "totals": totals, "states": states}

NWDP_BOUNDARY_RUNTIME_TABLES = [
    "geography_boundary_runtime_sets",
    "geography_boundary_runtime_features",
    "geography_boundary_runtime_crosswalks",
    "geography_boundary_runtime_promotion_events",
]


def _nwdp_boundary_runtime_pilot_inspection(db: Session, limit: int) -> dict:
    runtime_counts = {
        table: int(db.execute(text(f"select count(*) from {table}")).scalar() or 0)
        for table in NWDP_BOUNDARY_RUNTIME_TABLES
    }
    runtime_active_counts = {
        table: int(db.execute(text(f"select count(*) from {table} where is_active = true")).scalar() or 0)
        for table in NWDP_BOUNDARY_RUNTIME_TABLES
    }
    runtime_sets = [dict(row) for row in db.execute(text("""
        select id::text as runtime_set_id, status, activation_status, is_active,
               source_system, state_or_ut, source_format
        from geography_boundary_runtime_sets
        order by created_at, id
    """)).mappings().all()]
    promotion_events = [dict(row) for row in db.execute(text("""
        select id::text as promotion_event_id, runtime_set_id::text,
               source_import_batch_id::text, promotion_mode, promotion_status,
               is_active, candidate_count, runtime_feature_count,
               runtime_crosswalk_count, promoted_by
        from geography_boundary_runtime_promotion_events
        order by created_at, id
    """)).mappings().all()]
    crosswalks = [dict(row) for row in db.execute(text("""
        select
          rw.id::text as runtime_crosswalk_id,
          rw.runtime_set_id::text,
          rw.runtime_feature_id::text,
          rw.source_candidate_id::text as candidate_id,
          rw.runtime_scope,
          rw.village_id::text,
          rw.village_lgd_code,
          rw.confidence,
          rw.reviewer_decision,
          rw.is_active as runtime_crosswalk_active,
          rf.is_active as runtime_feature_active,
          rf.geometry_validation_status,
          rf.geometry_hash,
          rf.bbox_wgs84,
          rf.centroid_wgs84,
          c.source_feature_index,
          c.review_status,
          c.promotion_status,
          c.is_active as staging_candidate_active,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_vlcode
        from geography_boundary_runtime_crosswalks rw
        join geography_boundary_runtime_features rf on rf.id = rw.runtime_feature_id
        join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        order by c.source_feature_index
        limit :limit
    """), {"limit": limit}).mappings().all()]
    staging_guardrails = dict(db.execute(text("""
        select
          count(*) as linked_candidate_count,
          sum(case when c.is_active = false then 1 else 0 end) as inactive_count,
          sum(case when c.promotion_status = 'NOT_PROMOTED' then 1 else 0 end) as not_promoted_count,
          sum(case when c.review_status = 'APPROVED_FOR_PROMOTION' then 1 else 0 end) as approved_count,
          sum(case when c.reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH' then 1 else 0 end) as accepted_direct_count
        from geography_boundary_runtime_crosswalks rw
        join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
    """)).mappings().one())

    return {
        "runtime_counts": runtime_counts,
        "runtime_active_counts": runtime_active_counts,
        "runtime_sets": runtime_sets,
        "promotion_events": promotion_events,
        "staging_guardrails": staging_guardrails,
        "crosswalks": crosswalks,
    }



@router.get("/nwdp-boundary-state-wise-match-summary")
def get_nwdp_boundary_state_wise_match_summary(
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
) -> dict:
    summary = _nwdp_boundary_state_wise_match_summary(db)
    return {
        "schema_version": "nwdp_boundary_admin_state_wise_match_summary.v1",
        "claim_boundary": "Read-only admin summary over inactive staging rows. It does not activate candidates, promote candidates, write runtime tables, enable point-in-polygon matching, change lookup behavior, or change Android behavior.",
        "governance": _nwdp_boundary_governance(),
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "lookup_api_enabled": False,
        "android_behavior_changed": False,
        "readiness": {
            "ready_for_admin_state_wise_review_reporting": summary["healthy"],
            "ready_for_future_project_matching_design": summary["healthy"],
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        **summary,
    }



def _nwdp_boundary_project_matching_eligible_candidates(
    db: Session,
    state_or_ut: str | None,
    village_id: UUID | None,
    limit: int,
) -> dict:
    params = {
        "state_or_ut": state_or_ut,
        "village_id": str(village_id) if village_id else None,
        "limit": limit,
    }

    where_scope = """
      and (:state_or_ut is not null or :village_id is not null)
      and (:state_or_ut is null or b.state_or_ut = :state_or_ut)
      and (:village_id is null or c.proposed_village_id::text = :village_id)
    """

    total = int(db.execute(text(f"""
        select count(*)::bigint
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and f.geometry_validation_status = 'VALIDATED'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.is_active = false
          and c.promotion_status = 'NOT_PROMOTED'
          and c.proposed_village_id is not null
          {where_scope}
    """), params).scalar() or 0)

    items = [dict(row) for row in db.execute(text(f"""
        select
          b.state_or_ut,
          b.id::text as import_batch_id,
          c.id::text as candidate_id,
          c.source_feature_id::text,
          c.source_feature_index,
          c.candidate_bucket,
          c.confidence,
          c.review_status,
          c.promotion_status,
          c.proposed_scope,
          c.proposed_village_id::text,
          c.proposed_village_lgd_code,
          f.source_stcode,
          f.source_dtcode,
          f.source_sdcode,
          f.source_bkcode,
          f.source_vlcode,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.geometry_validation_status
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and f.geometry_validation_status = 'VALIDATED'
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.is_active = false
          and c.promotion_status = 'NOT_PROMOTED'
          and c.proposed_village_id is not null
          {where_scope}
        order by b.state_or_ut, f.source_feature_index
        limit :limit
    """), params).mappings().all()]

    return {
        "total": total,
        "returned": len(items),
        "items": items,
    }



@router.get("/nwdp-boundary-project-matching/eligible-candidates")
def list_nwdp_boundary_project_matching_eligible_candidates(
    state_or_ut: Optional[str] = Query(None),
    village_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
) -> dict:
    if state_or_ut is None and village_id is None:
        raise HTTPException(status_code=400, detail="state_or_ut or village_id is required")

    result = _nwdp_boundary_project_matching_eligible_candidates(db, state_or_ut, village_id, limit)
    return {
        "schema_version": "nwdp_boundary_project_matching_eligible_candidates.v1",
        "mode": "READ_ONLY_PROJECT_MATCHING_ELIGIBLE_CANDIDATES",
        "claim_boundary": "Read-only admin/project matching candidate read model. It returns inactive DIRECT_VLCODE_MATCH AUTO_CANDIDATE rows backed by VALIDATED source geometry only. It excludes manual review and blocked candidates and does not activate candidates, promote candidates, write runtime tables, enable lookup behavior, or change Android behavior.",
        "governance": _nwdp_boundary_governance(),
        "filters": {
            "state_or_ut": state_or_ut,
            "village_id": str(village_id) if village_id else None,
            "limit": limit,
        },
        "summary": {
            "eligible_candidate_count": result["total"],
            "returned_count": result["returned"],
            "manual_review_excluded": True,
            "blocked_excluded": True,
            "non_validated_geometry_excluded": True,
            "required_geometry_validation_status": "VALIDATED",
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_admin_project_matching_read": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "items": result["items"],
    }


def _nwdp_boundary_project_matching_project_preview(
    db: Session,
    project_id: UUID,
    limit: int,
) -> dict:
    project = db.execute(text("""
        select id::text as project_id, tenant_id, name, status, geography_scope
        from projects
        where id = :project_id
    """), {"project_id": str(project_id)}).mappings().first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_villages_sql = """
        select e.project_id, f.village_id
        from farmer_project_enrollments e
        join farmers f on f.id = e.farmer_id
        where e.is_active = true
          and f.is_active = true
          and f.village_id is not null
          and e.project_id = :project_id

        union

        select f.project_id, f.village_id
        from farmers f
        where f.is_active = true
          and f.project_id = :project_id
          and f.village_id is not null

        union

        select p.project_id, p.village_id
        from parcels p
        where p.is_active = true
          and p.project_id = :project_id
          and p.village_id is not null

        union

        select e.project_id, p.village_id
        from farmer_project_enrollments e
        join parcels p on p.farmer_id = e.farmer_id
        where e.is_active = true
          and p.is_active = true
          and e.project_id = :project_id
          and p.village_id is not null
    """

    scope = project.get("geography_scope") or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except Exception:
            scope = {}
    if not isinstance(scope, dict):
        scope = {}

    scope_sql, scope_params, _scope_sources = (
        _build_project_boundary_scope_village_sql(scope)
    )
    if scope_sql:
        project_villages_sql += f"""
            union

            select cast(:project_id as uuid) as project_id,
                   scoped.village_id
            from (
                {scope_sql}
            ) scoped
        """

    params = {
        "project_id": str(project_id),
        "limit": limit,
        **scope_params,
    }

    totals = db.execute(text(f"""
        with project_villages as (
            {project_villages_sql}
        ),
        eligible as (
            select
              c.id,
              c.proposed_village_id
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and f.geometry_validation_status = 'VALIDATED'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
        ),
        review_backlog as (
            select
              c.id,
              c.proposed_village_id,
              c.review_status
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.proposed_village_id is not null
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
        )
        select
          count(distinct pv.village_id)::bigint as project_village_count,
          count(distinct eligible.proposed_village_id)::bigint as villages_with_eligible_boundary,
          count(distinct pv.village_id) - count(distinct eligible.proposed_village_id) as villages_without_eligible_boundary,
          count(distinct eligible.id)::bigint as eligible_candidate_count,
          count(distinct review_backlog.id) filter (where review_backlog.review_status = 'MANUAL_REVIEW')::bigint as manual_review_candidate_count,
          count(distinct review_backlog.id) filter (where review_backlog.review_status = 'BLOCKED')::bigint as blocked_candidate_count
        from project_villages pv
        left join eligible on eligible.proposed_village_id = pv.village_id
        left join review_backlog on review_backlog.proposed_village_id = pv.village_id
    """), params).mappings().one()

    items = db.execute(text(f"""
        with project_villages as (
            {project_villages_sql}
        ),
        eligible as (
            select
              b.state_or_ut,
              c.id::text as candidate_id,
              c.proposed_village_id,
              c.proposed_village_lgd_code,
              c.source_feature_index,
              c.candidate_bucket,
              c.review_status,
              c.promotion_status,
              f.source_vlcode,
              f.source_district_name,
              f.source_subdistrict_name,
              f.source_village_name,
              f.geometry_validation_status
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and f.geometry_validation_status = 'VALIDATED'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
        )
        select
          pv.village_id::text,
          gv.lgd_code as village_lgd_code,
          gv.canonical_name as village_name,
          eligible.state_or_ut,
          count(eligible.candidate_id)::bigint as eligible_candidate_count,
          min(eligible.candidate_id) as sample_candidate_id,
          min(eligible.source_feature_index) as sample_source_feature_index,
          min(eligible.source_vlcode) as sample_source_vlcode,
          min(eligible.source_district_name) as sample_source_district_name,
          min(eligible.source_subdistrict_name) as sample_source_subdistrict_name,
          min(eligible.source_village_name) as sample_source_village_name
        from project_villages pv
        join geography_villages gv on gv.id = pv.village_id
        left join eligible on eligible.proposed_village_id = pv.village_id
        group by pv.village_id, gv.lgd_code, gv.canonical_name, eligible.state_or_ut
        order by eligible.state_or_ut nulls last, gv.canonical_name
        limit :limit
    """), params).mappings().all()

    summary = dict(totals)
    project_village_count = int(summary.get("project_village_count") or 0)
    eligible_villages = int(summary.get("villages_with_eligible_boundary") or 0)

    return {
        "project": dict(project),
        "summary": {
            **summary,
            "coverage_ratio": (eligible_villages / project_village_count) if project_village_count else 0,
            "manual_review_excluded_from_matching": True,
            "blocked_excluded_from_matching": True,
            "non_validated_geometry_excluded_from_matching": True,
            "required_geometry_validation_status": "VALIDATED",
        },
        "items": [dict(row) for row in items],
    }


@router.get("/project-geography-readiness")
def get_project_geography_readiness(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
) -> dict:
    """Return set-based geography and boundary readiness for project cards."""
    rows = db.execute(text("""
        with project_scope as (
            select
              p.id as project_id,
              p.name as project_name,
              p.status as project_status,
              scope_code.value as village_lgd_code
            from projects p
            left join lateral jsonb_array_elements_text(
              case
                when jsonb_typeof(
                  coalesce(p.geography_scope, '{}'::jsonb)
                  -> 'village_lgd_codes'
                ) = 'array'
                then p.geography_scope -> 'village_lgd_codes'
                else '[]'::jsonb
              end
            ) scope_code(value) on true
            where p.tenant_id = :tenant_id
              and p.is_active = true
        ),
        resolved as (
            select
              ps.project_id,
              ps.village_lgd_code,
              v.id as village_id,
              s.canonical_name as state_name,
              d.canonical_name as district_name
            from project_scope ps
            join geography_villages v
              on v.lgd_code = ps.village_lgd_code
             and v.is_active = true
            join geography_blocks b
              on b.id = v.block_id
             and b.is_active = true
            join geography_districts d
              on d.id = v.district_id
             and d.is_active = true
            join geography_states s
              on s.id = d.state_id
             and s.is_active = true
        ),
        eligible as (
            select distinct
              c.id as candidate_id,
              c.proposed_village_id as village_id
            from geography_boundary_import_batches batch
            join geography_boundary_crosswalk_candidates c
              on c.import_batch_id = batch.id
            join geography_boundary_source_features feature
              on feature.id = c.source_feature_id
            where batch.source_system =
                    'NWDP_GSI_VILLAGE_BOUNDARY'
              and feature.geometry_validation_status = 'VALIDATED'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.promotion_status = 'NOT_PROMOTED'
              and c.is_active = false
              and c.proposed_village_id is not null
        )
        select
          ps.project_id::text,
          min(ps.project_name) as project_name,
          min(ps.project_status) as project_status,
          count(distinct ps.village_lgd_code)
            filter (where ps.village_lgd_code is not null)
            ::bigint as scoped_village_code_count,
          count(distinct r.village_id)
            ::bigint as resolved_village_count,
          count(distinct r.village_id)
            filter (where e.village_id is not null)
            ::bigint as villages_with_eligible_boundary,
          (
            count(distinct r.village_id)
            - count(distinct r.village_id)
              filter (where e.village_id is not null)
          )::bigint as villages_without_eligible_boundary,
          count(distinct e.candidate_id)
            ::bigint as eligible_candidate_count,
          array_remove(
            array_agg(distinct r.state_name),
            null
          ) as state_names,
          array_remove(
            array_agg(
              distinct r.district_name || ', ' || r.state_name
            ),
            null
          ) as district_names
        from project_scope ps
        left join resolved r
          on r.project_id = ps.project_id
         and r.village_lgd_code = ps.village_lgd_code
        left join eligible e
          on e.village_id = r.village_id
        group by ps.project_id
        order by min(ps.project_name), ps.project_id
        limit :limit
    """), {
        "tenant_id": x_tenant_id,
        "limit": limit,
    }).mappings().all()

    items = []
    for raw_row in rows:
        row = dict(raw_row)
        scoped = int(row["scoped_village_code_count"] or 0)
        resolved = int(row["resolved_village_count"] or 0)
        covered = int(row["villages_with_eligible_boundary"] or 0)
        missing = int(row["villages_without_eligible_boundary"] or 0)

        items.append({
            **row,
            "scoped_village_code_count": scoped,
            "resolved_village_count": resolved,
            "unresolved_village_code_count": max(scoped - resolved, 0),
            "villages_with_eligible_boundary": covered,
            "villages_without_eligible_boundary": missing,
            "eligible_candidate_count": int(
                row["eligible_candidate_count"] or 0
            ),
            "coverage_ratio": covered / resolved if resolved else 0,
            "state_names": sorted(row["state_names"] or []),
            "district_names": sorted(row["district_names"] or []),
        })

    return {
        "schema_version": "project_geography_readiness.v1",
        "tenant_id": x_tenant_id,
        "project_count": len(items),
        "items": items,
        "guardrails": {
            "db_writes_attempted": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }



@router.get("/nwdp-boundary-project-matching/project-preview")
def get_nwdp_boundary_project_matching_project_preview(
    project_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
) -> dict:
    result = _nwdp_boundary_project_matching_project_preview(db, project_id, limit)
    return {
        "schema_version": "nwdp_boundary_project_matching_project_preview.v1",
        "mode": "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW",
        "claim_boundary": "Read-only project-scoped NWDP boundary coverage preview. It inspects inactive direct-code candidates backed by VALIDATED source geometry for project villages only. It does not activate candidates, promote candidates, write runtime tables, enable lookup behavior, or change Android behavior.",
        "governance": _nwdp_boundary_governance(),
        **result,
        "guardrails": {
            "db_writes_attempted": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_admin_project_matching_preview": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }



@router.get("/boundary-runtime-pilot/inspection", response_model=NwdpBoundaryRuntimePilotInspectionResponse)
def get_nwdp_boundary_runtime_pilot_inspection(
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    inspection = _nwdp_boundary_runtime_pilot_inspection(db, limit)
    return {
        "schema_version": "nwdp_boundary_runtime_pilot_inspection.v1",
        "mode": "READ_ONLY_RUNTIME_PILOT_INSPECTION",
        "governance": _nwdp_boundary_governance(),
        "db_writes_attempted": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "inspection": inspection,
        "readiness": {
            "runtime_rows_available_for_review": inspection["runtime_counts"] == {
                "geography_boundary_runtime_sets": 1,
                "geography_boundary_runtime_features": 10,
                "geography_boundary_runtime_crosswalks": 10,
                "geography_boundary_runtime_promotion_events": 1,
            },
            "runtime_rows_active": any(value > 0 for value in inspection["runtime_active_counts"].values()),
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
            "lookup_api_enabled": False,
        },
    }


@router.get("/boundary-runtime-promotion/dry-run", response_model=NwdpBoundaryRuntimePromotionDryRunResponse)
def get_nwdp_boundary_runtime_promotion_dry_run(
    state_or_ut: Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    import_batch_id: Optional[UUID] = Query(None),
    candidate_bucket: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    proposed_scope: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    where = ["c.is_active = false", "c.promotion_status = 'NOT_PROMOTED'"]
    params = {"limit": limit}

    if state_or_ut:
        where.append("b.state_or_ut = :state_or_ut")
        params["state_or_ut"] = state_or_ut
    if source_system:
        where.append("b.source_system = :source_system")
        params["source_system"] = source_system
    if import_batch_id:
        where.append("c.import_batch_id = :import_batch_id")
        params["import_batch_id"] = str(import_batch_id)
    if candidate_bucket:
        where.append("c.candidate_bucket = :candidate_bucket")
        params["candidate_bucket"] = candidate_bucket
    if review_status:
        where.append("c.review_status = :review_status")
        params["review_status"] = review_status
    if proposed_scope:
        where.append("c.proposed_scope = :proposed_scope")
        params["proposed_scope"] = proposed_scope

    where_sql = " and ".join(where)

    base_sql = f"""
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        where {where_sql}
    """

    total = db.execute(text(f"select count(*) {base_sql}"), params).scalar() or 0

    eligibility_rows = db.execute(text(f"""
        select
          case
            when c.review_status <> 'APPROVED_FOR_PROMOTION' then 'NOT_REVIEW_APPROVED'
            when c.reviewer_decision not in ('ACCEPT_DIRECT_CODE_MATCH', 'ACCEPT_REVIEWED_NAME_MATCH') then 'REVIEW_DECISION_NOT_PROMOTABLE'
            when c.candidate_bucket in ('SPECIAL_REFERENCE_FEATURE', 'DISTRICT_SCOPED_AMBIGUOUS', 'PARENT_SCOPED_NAME_AMBIGUOUS', 'PARENT_MATCH_VILLAGE_UNRESOLVED') then 'BUCKET_NOT_PROMOTABLE'
            when c.proposed_scope not in ('village', 'village_review') then 'SCOPE_NOT_RUNTIME_ELIGIBLE'
            when c.proposed_village_id is null then 'MISSING_PROPOSED_VILLAGE'
            when f.geometry_validation_status not in ('VALID', 'VALIDATED') then 'GEOMETRY_NOT_VALIDATED'
            else 'PROMOTABLE'
          end as eligibility,
          count(*) as count
        {base_sql}
        group by eligibility
        order by eligibility
    """), params).mappings().all()

    promotable_count = sum(int(row["count"]) for row in eligibility_rows if row["eligibility"] == "PROMOTABLE")
    excluded_count = total - promotable_count

    sample_select = f"""
        select
          c.id::text as candidate_id,
          c.import_batch_id::text as batch_id,
          c.source_feature_index,
          c.candidate_bucket,
          c.review_status,
          c.reviewer_decision,
          c.promotion_status,
          c.proposed_scope,
          c.proposed_village_lgd_code,
          c.proposed_village_id::text,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_village_name,
          f.source_vlcode,
          f.geometry_validation_status,
          case
            when c.review_status <> 'APPROVED_FOR_PROMOTION' then 'NOT_REVIEW_APPROVED'
            when c.reviewer_decision not in ('ACCEPT_DIRECT_CODE_MATCH', 'ACCEPT_REVIEWED_NAME_MATCH') then 'REVIEW_DECISION_NOT_PROMOTABLE'
            when c.candidate_bucket in ('SPECIAL_REFERENCE_FEATURE', 'DISTRICT_SCOPED_AMBIGUOUS', 'PARENT_SCOPED_NAME_AMBIGUOUS', 'PARENT_MATCH_VILLAGE_UNRESOLVED') then 'BUCKET_NOT_PROMOTABLE'
            when c.proposed_scope not in ('village', 'village_review') then 'SCOPE_NOT_RUNTIME_ELIGIBLE'
            when c.proposed_village_id is null then 'MISSING_PROPOSED_VILLAGE'
            when f.geometry_validation_status not in ('VALID', 'VALIDATED') then 'GEOMETRY_NOT_VALIDATED'
            else 'PROMOTABLE'
          end as eligibility
        {base_sql}
    """

    promotable_samples = db.execute(text(f"""
        {sample_select}
        and c.review_status = 'APPROVED_FOR_PROMOTION'
        and c.reviewer_decision in ('ACCEPT_DIRECT_CODE_MATCH', 'ACCEPT_REVIEWED_NAME_MATCH')
        and c.candidate_bucket not in ('SPECIAL_REFERENCE_FEATURE', 'DISTRICT_SCOPED_AMBIGUOUS', 'PARENT_SCOPED_NAME_AMBIGUOUS', 'PARENT_MATCH_VILLAGE_UNRESOLVED')
        and c.proposed_scope in ('village', 'village_review')
        and c.proposed_village_id is not null
        and f.geometry_validation_status in ('VALID', 'VALIDATED')
        order by c.source_feature_index
        limit :limit
    """), params).mappings().all()

    excluded_samples = db.execute(text(f"""
        select * from ({sample_select}) q
        where eligibility <> 'PROMOTABLE'
        order by source_feature_index
        limit :limit
    """), params).mappings().all()

    return {
        "schema_version": "nwdp_boundary_runtime_promotion_dry_run.v1",
        "mode": "DRY_RUN_READ_ONLY",
        "governance": _nwdp_boundary_governance(),
        "filters": {
            "state_or_ut": state_or_ut,
            "source_system": source_system,
            "import_batch_id": str(import_batch_id) if import_batch_id else None,
            "candidate_bucket": candidate_bucket,
            "review_status": review_status,
            "proposed_scope": proposed_scope,
            "limit": limit,
        },
        "summary": {
            "candidate_count": total,
            "promotable_candidate_count": promotable_count,
            "excluded_candidate_count": excluded_count,
            "db_writes_attempted": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
        },
        "eligibility_counts": [dict(row) for row in eligibility_rows],
        "exclusion_counts": [dict(row) for row in eligibility_rows if row["eligibility"] != "PROMOTABLE"],
        "promotable_samples": [dict(row) for row in promotable_samples],
        "excluded_samples": [dict(row) for row in excluded_samples],
        "readiness": {
            "safe_read_only": True,
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
            "runtime_tables_required": True,
            "promotion_supported_by_this_endpoint": False,
        },
    }



class ProjectBoundaryAssignmentRequest(BaseModel):
    candidate_id: UUID
    rollback_token: str = Field(min_length=8, max_length=80)
    reason: str = Field(min_length=3, max_length=500)
    supersede_existing: bool = False


def _project_boundary_assignment_payload(db: Session, match_id: UUID | str) -> dict:
    row = db.execute(text("""
        select
          pm.id::text as match_id,
          pm.tenant_id,
          pm.project_id::text,
          pm.village_id::text,
          pm.boundary_candidate_id::text,
          pm.source_system,
          pm.match_source,
          pm.match_status,
          pm.applied_by,
          pm.applied_at,
          pm.rolled_back_by,
          pm.rolled_back_at,
          pm.rollback_token,
          pm.metadata,
          pm.is_active,
          pm.created_at,
          pm.updated_at,
          sf.geometry_validation_status
        from geography_boundary_project_matches pm
        join geography_boundary_crosswalk_candidates c
          on c.id = pm.boundary_candidate_id
        join geography_boundary_source_features sf
          on sf.id = c.source_feature_id
        where pm.id = :match_id
    """), {"match_id": str(match_id)}).mappings().one()
    return dict(row)


def _project_contains_village(
    db: Session,
    project_id: UUID,
    village_id: UUID,
) -> bool:
    directly_linked = bool(db.execute(text("""
        select exists (
          select 1
          from farmer_project_enrollments e
          join farmers f on f.id = e.farmer_id
          where e.project_id = :project_id
            and e.is_active = true
            and f.is_active = true
            and f.village_id = :village_id

          union

          select 1
          from farmers f
          where f.project_id = :project_id
            and f.is_active = true
            and f.village_id = :village_id

          union

          select 1
          from parcels p
          where p.project_id = :project_id
            and p.is_active = true
            and p.village_id = :village_id

          union

          select 1
          from farmer_project_enrollments e
          join parcels p on p.farmer_id = e.farmer_id
          where e.project_id = :project_id
            and e.is_active = true
            and p.is_active = true
            and p.village_id = :village_id
        )
    """), {
        "project_id": str(project_id),
        "village_id": str(village_id),
    }).scalar())

    if directly_linked:
        return True

    project = db.execute(text("""
        select geography_scope
        from projects
        where id = :project_id
    """), {"project_id": str(project_id)}).mappings().first()
    if not project:
        return False

    scope = project.get("geography_scope") or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except Exception:
            scope = {}
    if not isinstance(scope, dict):
        return False

    scope_sql, scope_params, _sources = (
        _build_project_boundary_scope_village_sql(scope)
    )
    if not scope_sql:
        return False

    return bool(db.execute(text(f"""
        select exists (
          select 1
          from (
            {scope_sql}
          ) scope_villages
          where scope_villages.village_id = :assigned_village_id
        )
    """), {
        **scope_params,
        "assigned_village_id": str(village_id),
    }).scalar())


def _project_boundary_assignment_guardrails(written: bool) -> dict:
    return {
        "db_writes_attempted": written,
        "project_matching_records_written": written,
        "candidate_activation_changed": False,
        "candidate_promotion_changed": False,
        "source_runtime_eligibility_changed": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "lookup_api_enabled": False,
        "lgd_geography_overwritten": False,
        "android_behavior_changed": False,
    }


@router.get(
    "/nwdp-boundary-project-matching/projects/{project_id}/assignments"
)
def list_nwdp_boundary_project_assignments(
    project_id: UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(AdminPermission.VIEW, project_scoped=True)
    ),
):
    where_active = "" if include_inactive else "and pm.is_active = true"
    rows = db.execute(text(f"""
        select
          pm.id::text as match_id,
          pm.tenant_id,
          pm.project_id::text,
          pm.village_id::text,
          pm.boundary_candidate_id::text,
          pm.source_system,
          pm.match_source,
          pm.match_status,
          pm.applied_by,
          pm.applied_at,
          pm.rolled_back_by,
          pm.rolled_back_at,
          pm.rollback_token,
          pm.metadata,
          pm.is_active,
          pm.created_at,
          pm.updated_at,
          sf.geometry_validation_status
        from geography_boundary_project_matches pm
        join geography_boundary_crosswalk_candidates c
          on c.id = pm.boundary_candidate_id
        join geography_boundary_source_features sf
          on sf.id = c.source_feature_id
        where pm.project_id = :project_id
          and pm.tenant_id = :tenant_id
          {where_active}
        order by pm.is_active desc, pm.created_at desc
    """), {
        "project_id": str(project_id),
        "tenant_id": x_tenant_id,
    }).mappings().all()

    items = [dict(row) for row in rows]
    return {
        "schema_version": "nwdp_boundary_project_assignments.v1",
        "mode": "PROJECT_SCOPED_BOUNDARY_ASSIGNMENTS",
        "project_id": str(project_id),
        "tenant_id": x_tenant_id,
        "active_count": sum(1 for row in items if row["is_active"]),
        "count": len(items),
        "items": items,
        "guardrails": _project_boundary_assignment_guardrails(False),
    }


@router.put(
    "/nwdp-boundary-project-matching/projects/{project_id}/villages/{village_id}"
)
def assign_nwdp_boundary_to_project_village(
    project_id: UUID,
    village_id: UUID,
    body: ProjectBoundaryAssignmentRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.PROJECT_EDIT,
            project_scoped=True,
        )
    ),
):
    if not _project_contains_village(db, project_id, village_id):
        raise HTTPException(
            status_code=409,
            detail="VILLAGE_NOT_IN_PROJECT_SCOPE",
        )

    candidate = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.proposed_village_id::text as village_id,
          c.proposed_village_lgd_code,
          c.candidate_bucket,
          c.review_status,
          c.promotion_status,
          c.is_active as candidate_is_active,
          b.source_system,
          b.state_or_ut,
          sf.geometry_validation_status,
          sf.eligible_for_runtime_after_promotion
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        join geography_boundary_source_features sf on sf.id = c.source_feature_id
        where c.id = :candidate_id
    """), {"candidate_id": str(body.candidate_id)}).mappings().first()

    if not candidate:
        raise HTTPException(status_code=404, detail="Boundary candidate not found")

    eligible = (
        candidate["source_system"] == "NWDP_GSI_VILLAGE_BOUNDARY"
        and candidate["village_id"] == str(village_id)
        and candidate["candidate_bucket"] == "DIRECT_VLCODE_MATCH"
        and candidate["review_status"] == "AUTO_CANDIDATE"
        and candidate["promotion_status"] == "NOT_PROMOTED"
        and candidate["candidate_is_active"] is False
        and candidate["geometry_validation_status"] == "VALIDATED"
    )
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail="BOUNDARY_CANDIDATE_NOT_ASSIGNABLE",
        )

    existing = db.execute(text("""
        select id::text, boundary_candidate_id::text, rollback_token
        from geography_boundary_project_matches
        where tenant_id = :tenant_id
          and project_id = :project_id
          and village_id = :village_id
          and source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and is_active = true
        for update
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
    }).mappings().first()

    if existing and existing["boundary_candidate_id"] == str(body.candidate_id):
        return {
            "schema_version": "nwdp_boundary_project_assignment.v1",
            "action": "IDEMPOTENT_NO_OP",
            "assignment": _project_boundary_assignment_payload(
                db, existing["id"]
            ),
            "guardrails": _project_boundary_assignment_guardrails(False),
        }

    if existing and not body.supersede_existing:
        raise HTTPException(
            status_code=409,
            detail="ACTIVE_PROJECT_VILLAGE_BOUNDARY_MATCH_EXISTS",
        )

    actor = str(principal.user_id)

    if existing:
        db.execute(text("""
            update geography_boundary_project_matches
            set
              is_active = false,
              match_status = 'ROLLED_BACK',
              rolled_back_by = :actor,
              rolled_back_at = now(),
              rollback_report = jsonb_build_object(
                'reason', 'EXPLICIT_SUPERSESSION',
                'superseded_by_candidate_id', :candidate_id,
                'actor', :actor
              ),
              updated_at = now()
            where id = :match_id
        """), {
            "actor": actor,
            "candidate_id": str(body.candidate_id),
            "match_id": existing["id"],
        })

    match_id = uuid4()
    metadata = {
        "reason": body.reason,
        "assignment_source": "admin_project_boundary_api",
        "geometry_validation_status": "VALIDATED",
        "runtime_eligibility_changed": False,
    }
    apply_report = {
        "schema_version": "nwdp_boundary_project_assignment.v1",
        "project_id": str(project_id),
        "village_id": str(village_id),
        "candidate_id": str(body.candidate_id),
        "applied_by": actor,
        "superseded_existing": bool(existing),
    }

    db.execute(text("""
        insert into geography_boundary_project_matches (
          id, tenant_id, project_id, village_id, boundary_candidate_id,
          source_system, match_source, match_status, applied_by, applied_at,
          rollback_token, dry_run_report, apply_report, rollback_report,
          metadata, is_active, created_at, updated_at, version
        )
        values (
          :id, :tenant_id, :project_id, :village_id, :candidate_id,
          'NWDP_GSI_VILLAGE_BOUNDARY', 'ADMIN_PROJECT_MATCHING', 'APPLIED',
          :actor, now(), :rollback_token, '{}'::jsonb,
          cast(:apply_report as jsonb), '{}'::jsonb,
          cast(:metadata as jsonb), true, now(), now(), 'v1.0'
        )
    """), {
        "id": str(match_id),
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
        "candidate_id": str(body.candidate_id),
        "actor": actor,
        "rollback_token": body.rollback_token,
        "apply_report": json.dumps(apply_report),
        "metadata": json.dumps(metadata),
    })
    db.commit()

    return {
        "schema_version": "nwdp_boundary_project_assignment.v1",
        "action": "SUPERSEDED_AND_APPLIED" if existing else "APPLIED",
        "assignment": _project_boundary_assignment_payload(db, match_id),
        "guardrails": _project_boundary_assignment_guardrails(True),
    }


@router.delete(
    "/nwdp-boundary-project-matching/projects/{project_id}/villages/{village_id}"
)
def unassign_nwdp_boundary_from_project_village(
    project_id: UUID,
    village_id: UUID,
    rollback_token: str = Query(min_length=8, max_length=80),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(
            AdminPermission.PROJECT_EDIT,
            project_scoped=True,
        )
    ),
):
    existing = db.execute(text("""
        select id::text, rollback_token
        from geography_boundary_project_matches
        where tenant_id = :tenant_id
          and project_id = :project_id
          and village_id = :village_id
          and source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
          and is_active = true
        for update
    """), {
        "tenant_id": x_tenant_id,
        "project_id": str(project_id),
        "village_id": str(village_id),
    }).mappings().first()

    if not existing:
        rolled_back = db.execute(text("""
            select id::text
            from geography_boundary_project_matches
            where tenant_id = :tenant_id
              and project_id = :project_id
              and village_id = :village_id
              and source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and rollback_token = :rollback_token
              and match_status = 'ROLLED_BACK'
            order by rolled_back_at desc nulls last
            limit 1
        """), {
            "tenant_id": x_tenant_id,
            "project_id": str(project_id),
            "village_id": str(village_id),
            "rollback_token": rollback_token,
        }).mappings().first()

        if not rolled_back:
            raise HTTPException(
                status_code=404,
                detail="ACTIVE_PROJECT_BOUNDARY_ASSIGNMENT_NOT_FOUND",
            )
        return {
            "schema_version": "nwdp_boundary_project_assignment.v1",
            "action": "IDEMPOTENT_ROLLBACK_NO_OP",
            "assignment": _project_boundary_assignment_payload(
                db, rolled_back["id"]
            ),
            "guardrails": _project_boundary_assignment_guardrails(False),
        }

    if existing["rollback_token"] != rollback_token:
        raise HTTPException(
            status_code=409,
            detail="ROLLBACK_TOKEN_MISMATCH",
        )

    actor = str(principal.user_id)
    db.execute(text("""
        update geography_boundary_project_matches
        set
          is_active = false,
          match_status = 'ROLLED_BACK',
          rolled_back_by = :actor,
          rolled_back_at = now(),
          rollback_report = jsonb_build_object(
            'reason', 'ADMIN_PROJECT_UNASSIGNMENT',
            'rollback_token', :rollback_token,
            'actor', :actor
          ),
          updated_at = now()
        where id = :match_id
    """), {
        "actor": actor,
        "rollback_token": rollback_token,
        "match_id": existing["id"],
    })
    db.commit()

    return {
        "schema_version": "nwdp_boundary_project_assignment.v1",
        "action": "ROLLED_BACK",
        "assignment": _project_boundary_assignment_payload(
            db, existing["id"]
        ),
        "guardrails": _project_boundary_assignment_guardrails(True),
    }


@router.post("/nwdp-boundary-project-matching/apply")
def apply_nwdp_boundary_project_matching_disabled(
    project_id: UUID,
    rollback_token: str | None = Query(default=None),
    dry_run_confirmed: bool = Query(default=False),
    admin_confirmation: bool = Query(default=False),
    feature_flag_enabled: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Disabled contract endpoint for future guarded project matching apply."""
    project = db.execute(
        text("""
            select id, tenant_id, name, status
            from projects
            where id = :project_id
              and is_active = true
        """),
        {"project_id": str(project_id)},
    ).mappings().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    detail = {
        "schema_version": "nwdp_boundary_project_matching_apply_disabled.v1",
        "mode": "PROJECT_MATCHING_APPLY_NOT_IMPLEMENTED",
        "claim_boundary": (
            "Disabled contract endpoint only. It validates the future apply gates and returns "
            "the required guardrails, but does not write project matching records, activate "
            "candidates, promote candidates, write runtime tables, enable lookup APIs, or "
            "change Android behavior."
        ),
        "governance": _nwdp_boundary_governance(db_write_scope="NONE"),
        "project": {
            "project_id": str(project["id"]),
            "tenant_id": project["tenant_id"],
            "name": project["name"],
            "status": project["status"],
        },
        "required_gates": {
            "feature_flag_enabled": feature_flag_enabled,
            "dry_run_confirmed": dry_run_confirmed,
            "admin_confirmation": admin_confirmation,
            "rollback_token_present": bool(rollback_token),
            "all_gates_present": bool(
                feature_flag_enabled and dry_run_confirmed and admin_confirmation and rollback_token
            ),
        },
        "candidate_selection_policy": {
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "candidate_bucket": "DIRECT_VLCODE_MATCH",
            "review_status": "AUTO_CANDIDATE",
            "required_is_active": False,
            "required_promotion_status": "NOT_PROMOTED",
            "requires_proposed_village_id": True,
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
            "non_direct_candidates_excluded": True,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "project_matching_records_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_apply_contract_review": True,
            "ready_for_project_matching_apply": False,
            "ready_for_runtime_spatial_matching": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }
    raise HTTPException(status_code=501, detail=detail)



@router.get("/layer-readiness")
def get_geography_layer_readiness(
    state_or_ut: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    limit: int = Query(5000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only admin geography layer readiness matrix.

    This endpoint does not import rows, promote candidates, activate runtime
    lookup, call external APIs, or change Android behavior.
    """

    return _build_geography_layer_readiness_matrix(
        db=db,
        state_or_ut=state_or_ut,
        district=district,
        limit=limit,
    )


@router.get("/nwdp-demographic-profiles/filter-options")
def get_nwdp_demographic_profile_filter_options(
    state_or_ut: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only state/district options for the NWDP demographic profile explorer."""

    state_rows = db.execute(
        text(
            """
            SELECT
                source_state_name AS state_or_ut,
                COUNT(*)::bigint AS profile_row_count,
                COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
                COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count
            FROM geography_village_demographic_profiles
            GROUP BY source_state_name
            ORDER BY source_state_name NULLS LAST
            """
        )
    ).mappings().all()

    district_rows = db.execute(
        text(
            """
            SELECT
                source_state_name AS state_or_ut,
                source_district_name AS district,
                COUNT(*)::bigint AS profile_row_count,
                COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
                COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count
            FROM geography_village_demographic_profiles
            WHERE (:state_or_ut IS NULL OR source_state_name = :state_or_ut)
            GROUP BY source_state_name, source_district_name
            ORDER BY source_state_name NULLS LAST, source_district_name NULLS LAST
            """
        ),
        {"state_or_ut": state_or_ut},
    ).mappings().all()

    return {
        "schema_version": "nwdp_demographic_profile_filter_options.v1",
        "mode": "read_only_filter_options",
        "healthy": True,
        "filters": {"state_or_ut": state_or_ut},
        "states": [
            {key: (int(value) if key.endswith("_count") else value) for key, value in row.items()}
            for row in state_rows
        ],
        "districts": [
            {key: (int(value) if key.endswith("_count") else value) for key, value in row.items()}
            for row in district_rows
        ],
        "guardrails": {
            "db_writes_attempted": False,
            "profiles_promoted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }


@router.get("/nwdp-demographic-profiles/preview")
def preview_nwdp_demographic_profiles(
    state_or_ut: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    promotion_status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    source_vlcode: Optional[str] = Query(None),
    village_name: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only admin preview for NWDP demographic profile rows.

    The endpoint intentionally mirrors the boundary review admin style: summary
    counts, review-status breakdowns, filters, and state/district grouping. It
    does not import, promote, activate, or expose runtime/Android behavior.
    """

    filters = {
        "state_or_ut": state_or_ut,
        "district": district,
        "review_status": review_status,
        "promotion_status": promotion_status,
        "is_active": is_active,
        "source_vlcode": source_vlcode,
        "village_name": village_name,
        "offset": offset,
        "limit": limit,
    }

    where_parts = []
    params = {"limit": limit, "offset": offset}

    if state_or_ut:
        where_parts.append("source_state_name = :state_or_ut")
        params["state_or_ut"] = state_or_ut

    if district:
        where_parts.append("source_district_name = :district")
        params["district"] = district

    if review_status:
        where_parts.append("review_status = :review_status")
        params["review_status"] = review_status

    if promotion_status:
        where_parts.append("promotion_status = :promotion_status")
        params["promotion_status"] = promotion_status

    if is_active is not None:
        where_parts.append("is_active = :is_active")
        params["is_active"] = is_active

    if source_vlcode:
        where_parts.append("source_vlcode = :source_vlcode")
        params["source_vlcode"] = source_vlcode

    if village_name:
        where_parts.append("source_village_name ILIKE :village_name")
        params["village_name"] = f"%{village_name}%"

    where_sql = " AND ".join(where_parts) if where_parts else "TRUE"

    counts = db.execute(
        text(
            f"""
            SELECT
                COUNT(*)::bigint AS profile_row_count,
                COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
                COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count,
                COUNT(*) FILTER (WHERE promotion_status = 'NOT_PROMOTED')::bigint AS not_promoted_profile_row_count,
                COUNT(*) FILTER (WHERE review_status = 'AUTO_CANDIDATE')::bigint AS auto_candidate_count,
                COUNT(*) FILTER (WHERE review_status = 'MANUAL_REVIEW')::bigint AS manual_review_count,
                COUNT(*) FILTER (WHERE review_status = 'APPROVED_FOR_PROMOTION')::bigint AS approved_for_promotion_count,
                COUNT(*) FILTER (WHERE review_status = 'REJECTED')::bigint AS rejected_count,
                COUNT(*) FILTER (WHERE review_status = 'BLOCKED')::bigint AS blocked_count
            FROM geography_village_demographic_profiles
            WHERE {where_sql}
            """
        ),
        params,
    ).mappings().one()

    summary = {
        key: int(counts[key] or 0)
        for key in (
            "profile_row_count",
            "active_profile_row_count",
            "promoted_profile_row_count",
            "not_promoted_profile_row_count",
            "auto_candidate_count",
            "manual_review_count",
            "approved_for_promotion_count",
            "rejected_count",
            "blocked_count",
        )
    }

    state_district_rows = db.execute(
        text(
            f"""
            SELECT
                source_state_name AS state_or_ut,
                source_district_name AS district,
                COUNT(*)::bigint AS profile_row_count,
                COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
                COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count,
                COUNT(*) FILTER (WHERE review_status = 'AUTO_CANDIDATE')::bigint AS auto_candidate_count,
                COUNT(*) FILTER (WHERE review_status = 'MANUAL_REVIEW')::bigint AS manual_review_count,
                COUNT(*) FILTER (WHERE review_status = 'APPROVED_FOR_PROMOTION')::bigint AS approved_for_promotion_count,
                COUNT(*) FILTER (WHERE review_status = 'REJECTED')::bigint AS rejected_count,
                COUNT(*) FILTER (WHERE review_status = 'BLOCKED')::bigint AS blocked_count
            FROM geography_village_demographic_profiles
            WHERE {where_sql}
            GROUP BY source_state_name, source_district_name
            ORDER BY source_state_name NULLS LAST, source_district_name NULLS LAST
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    preview_rows = db.execute(
        text(
            f"""
            SELECT
                id::text AS profile_id,
                village_id::text AS village_id,
                source_state_name AS state_or_ut,
                source_district_name AS district,
                source_subdistrict_name,
                source_village_name,
                source_vlcode,
                source_system,
                source_version,
                total_population,
                total_households,
                rural_urban,
                review_status,
                promotion_status,
                is_active
            FROM geography_village_demographic_profiles
            WHERE {where_sql}
            ORDER BY is_active DESC, source_state_name NULLS LAST, source_district_name NULLS LAST, source_village_name NULLS LAST
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    enabled = summary["profile_row_count"] > 0
    reason = None if enabled else "NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED"

    return {
        "schema_version": "nwdp_demographic_profiles_admin_preview.v1",
        "mode": "read_only_admin_preview",
        "healthy": True,
        "enabled": enabled,
        "reason": reason,
        "claim_boundary": (
            "Admin preview is read-only. It summarizes imported inactive/active "
            "demographic profile rows for review, but does not import rows, "
            "promote profiles, enable runtime lookup, or change Android behavior."
        ),
        "target_table": "geography_village_demographic_profiles",
        "future_preview_fields": [
            "state_or_ut",
            "district",
            "source_subdistrict_name",
            "source_village_name",
            "source_vlcode",
            "source_system",
            "source_version",
            "total_population",
            "total_households",
            "rural_urban",
            "review_status",
            "promotion_status",
            "is_active",
        ],
        "filters": filters,
        "profile_row_count": summary["profile_row_count"],
        "active_profile_row_count": summary["active_profile_row_count"],
        "promoted_profile_row_count": summary["promoted_profile_row_count"],
        "summary": summary,
        "approved_vs_manual_review": {
            "approved_for_promotion_count": summary["approved_for_promotion_count"],
            "manual_review_count": summary["manual_review_count"],
        },
        "state_district_summary": [
            {
                key: (int(value) if key.endswith("_count") else value)
                for key, value in row.items()
            }
            for row in state_district_rows
        ],
        "items": [dict(row) for row in preview_rows],
        "readiness": {
            "ready_for_profile_apply": False,
            "ready_for_runtime_lookup": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "profiles_promoted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
        },
    }


@router.get("/nwdp-boundary-batches", response_model=NwdpBoundaryBatchListResponse)
def list_nwdp_boundary_batches(
    state_or_ut: Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    where = ["1=1"]
    params = {"offset": offset, "limit": limit}

    if state_or_ut:
        where.append("b.state_or_ut = :state_or_ut")
        params["state_or_ut"] = state_or_ut
    if source_system:
        where.append("b.source_system = :source_system")
        params["source_system"] = source_system
    if status:
        where.append("b.status = :status")
        params["status"] = status
    if review_status:
        where.append("b.review_status = :review_status")
        params["review_status"] = review_status

    where_sql = " and ".join(where)

    total = db.execute(text(f"""
        select count(*)
        from geography_boundary_import_batches b
        where {where_sql}
    """), params).scalar() or 0

    rows = db.execute(text(f"""
        select
          b.id::text as batch_id,
          b.source_system,
          b.source_dataset,
          b.source_producer_agency,
          b.state_or_ut,
          b.source_format,
          b.source_crs,
          b.source_epsg,
          b.target_crs,
          b.source_file_sha256,
          b.status,
          b.review_status,
          b.is_active,
          b.created_at,
          b.reviewed_at,
          coalesce(sf.feature_count, 0) as feature_count,
          coalesce(cc.candidate_count, 0) as candidate_count,
          coalesce(cc.auto_candidate_count, 0) as auto_candidate_count,
          coalesce(cc.manual_review_count, 0) as manual_review_count,
          coalesce(cc.blocked_count, 0) as blocked_count
        from geography_boundary_import_batches b
        left join (
          select import_batch_id, count(*) as feature_count
          from geography_boundary_source_features
          group by import_batch_id
        ) sf on sf.import_batch_id = b.id
        left join (
          select
            import_batch_id,
            count(*) as candidate_count,
            sum(case when review_status = 'AUTO_CANDIDATE' then 1 else 0 end) as auto_candidate_count,
            sum(case when review_status = 'MANUAL_REVIEW' then 1 else 0 end) as manual_review_count,
            sum(case when review_status = 'BLOCKED' then 1 else 0 end) as blocked_count
          from geography_boundary_crosswalk_candidates
          group by import_batch_id
        ) cc on cc.import_batch_id = b.id
        where {where_sql}
        order by b.created_at desc
        offset :offset limit :limit
    """), params).mappings().all()

    items = [dict(row) for row in rows]

    return {
        "schema_version": "nwdp_boundary_admin_batches.v1",
        "mode": "READ_ONLY_ADMIN_REVIEW",
        "governance": _nwdp_boundary_governance(),
        "filters": {
            "state_or_ut": state_or_ut,
            "source_system": source_system,
            "status": status,
            "review_status": review_status,
        },
        "summary": {
            "total_batches": total,
            "runtime_spatial_matching_changed": False,
            "android_behavior_changed": False,
        },
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/nwdp-boundary-batches/{batch_id}", response_model=NwdpBoundaryBatchDetailResponse)
def get_nwdp_boundary_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    batch = db.execute(text("""
        select
          id::text as batch_id,
          source_system,
          source_dataset,
          source_producer_agency,
          state_or_ut,
          source_format,
          source_resource_url,
          source_download_url,
          source_file_sha256,
          source_file_size_bytes,
          source_crs,
          source_epsg,
          target_crs,
          status,
          review_status,
          is_active,
          reviewed_at,
          review_notes,
          created_at,
          manifest_audit,
          geometry_audit,
          crosswalk_audit,
          metadata
        from geography_boundary_import_batches
        where id = :batch_id
    """), {"batch_id": str(batch_id)}).mappings().first()

    if not batch:
        raise HTTPException(status_code=404, detail="NWDP boundary batch not found")

    summary = db.execute(text("""
        select
          count(*) as candidate_count,
          sum(case when review_status = 'AUTO_CANDIDATE' then 1 else 0 end) as auto_candidate_count,
          sum(case when review_status = 'MANUAL_REVIEW' then 1 else 0 end) as manual_review_count,
          sum(case when review_status = 'BLOCKED' then 1 else 0 end) as blocked_count,
          sum(case when is_active then 1 else 0 end) as active_candidate_count,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidate_count
        from geography_boundary_crosswalk_candidates
        where import_batch_id = :batch_id
    """), {"batch_id": str(batch_id)}).mappings().one()

    row = dict(batch)
    audit_evidence = {
        "manifest_audit": _jsonish(row.pop("manifest_audit")),
        "geometry_audit": _jsonish(row.pop("geometry_audit")),
        "crosswalk_audit": _jsonish(row.pop("crosswalk_audit")),
        "metadata": _jsonish(row.pop("metadata")),
    }

    return {
        "schema_version": "nwdp_boundary_admin_batch_detail.v1",
        "mode": "READ_ONLY_ADMIN_REVIEW",
        "governance": _nwdp_boundary_governance(),
        "batch": row,
        "audit_evidence": audit_evidence,
        "candidate_summary": dict(summary),
    }


@router.get("/nwdp-boundary-batches/{batch_id}/candidates", response_model=NwdpBoundaryCandidateListResponse)
def list_nwdp_boundary_candidates(
    batch_id: UUID,
    candidate_bucket: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    promotion_status: Optional[str] = Query(None),
    proposed_scope: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    subdistrict: Optional[str] = Query(None),
    block: Optional[str] = Query(None),
    vlcode: Optional[str] = Query(None),
    backend_village_lgd_code: Optional[str] = Query(None),
    parent_mismatch_only: bool = Query(False),
    unresolved_only: bool = Query(False),
    special_reference_only: bool = Query(False),
    has_review_history: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    if not db.execute(text("select 1 from geography_boundary_import_batches where id = :batch_id"), {"batch_id": str(batch_id)}).first():
        raise HTTPException(status_code=404, detail="NWDP boundary batch not found")

    where = ["c.import_batch_id = :batch_id"]
    params = {"batch_id": str(batch_id), "offset": offset, "limit": limit}

    if candidate_bucket:
        where.append("c.candidate_bucket = :candidate_bucket")
        params["candidate_bucket"] = candidate_bucket
    if review_status:
        where.append("c.review_status = :review_status")
        params["review_status"] = review_status
    if promotion_status:
        where.append("c.promotion_status = :promotion_status")
        params["promotion_status"] = promotion_status
    if proposed_scope:
        where.append("c.proposed_scope = :proposed_scope")
        params["proposed_scope"] = proposed_scope
    if district:
        where.append("f.source_district_name ilike :district")
        params["district"] = f"%{district}%"
    if subdistrict:
        where.append("f.source_subdistrict_name ilike :subdistrict")
        params["subdistrict"] = f"%{subdistrict}%"
    if block:
        where.append("f.source_block_name ilike :block")
        params["block"] = f"%{block}%"
    if vlcode:
        where.append("f.source_vlcode = :vlcode")
        params["vlcode"] = vlcode
    if backend_village_lgd_code:
        where.append("c.proposed_village_lgd_code = :backend_village_lgd_code")
        params["backend_village_lgd_code"] = backend_village_lgd_code
    if parent_mismatch_only:
        where.append("c.candidate_bucket = 'DIRECT_VLCODE_PARENT_MISMATCH'")
    if unresolved_only:
        where.append("c.candidate_bucket in ('PARENT_MATCH_VILLAGE_UNRESOLVED', 'DISTRICT_SCOPED_AMBIGUOUS')")
    if special_reference_only:
        where.append("c.candidate_bucket = 'SPECIAL_REFERENCE_FEATURE'")
    if has_review_history is True:
        where.append("jsonb_array_length(coalesce(c.metadata->'review_history', '[]'::jsonb)) > 0")
    elif has_review_history is False:
        where.append("jsonb_array_length(coalesce(c.metadata->'review_history', '[]'::jsonb)) = 0")

    where_sql = " and ".join(where)

    total = db.execute(text(f"""
        select count(*)
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where {where_sql}
    """), params).scalar() or 0

    rows = db.execute(text(f"""
        select
          c.id::text as candidate_id,
          c.source_feature_id::text,
          c.source_feature_index,
          c.candidate_bucket,
          c.confidence,
          c.review_status,
          c.promotion_status,
          c.proposed_scope,
          c.source_codes,
          c.source_names,
          c.proposed_state_lgd_code,
          c.proposed_district_lgd_code,
          c.proposed_block_lgd_code,
          c.proposed_village_lgd_code,
          c.proposed_state_id::text,
          c.proposed_district_id::text,
          c.proposed_block_id::text,
          c.proposed_village_id::text,
          c.match_evidence,
          c.updated_at,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_vlcode
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where {where_sql}
        order by c.source_feature_index
        offset :offset limit :limit
    """), params).mappings().all()

    summary = db.execute(text("""
        select
          count(*) as total,
          sum(case when review_status = 'AUTO_CANDIDATE' then 1 else 0 end) as auto_candidate_count,
          sum(case when review_status = 'MANUAL_REVIEW' then 1 else 0 end) as manual_review_count,
          sum(case when review_status = 'BLOCKED' then 1 else 0 end) as blocked_count,
          sum(case when is_active then 1 else 0 end) as active_candidate_count,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidate_count
        from geography_boundary_crosswalk_candidates
        where import_batch_id = :batch_id
    """), {"batch_id": str(batch_id)}).mappings().one()

    return {
        "schema_version": "nwdp_boundary_admin_candidates.v1",
        "mode": "READ_ONLY_ADMIN_REVIEW",
        "governance": _nwdp_boundary_governance(),
        "filters": {
            "candidate_bucket": candidate_bucket,
            "review_status": review_status,
            "promotion_status": promotion_status,
            "proposed_scope": proposed_scope,
            "district": district,
            "subdistrict": subdistrict,
            "block": block,
            "vlcode": vlcode,
            "backend_village_lgd_code": backend_village_lgd_code,
            "parent_mismatch_only": parent_mismatch_only,
            "unresolved_only": unresolved_only,
            "special_reference_only": special_reference_only,
          "has_review_history": has_review_history,
        },
        "summary": {**dict(summary), "runtime_spatial_matching_changed": False},
        "items": [dict(row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }



@router.get("/nwdp-boundary-batches/{batch_id}/candidates/export.csv")
def export_nwdp_boundary_candidates_csv(
    batch_id: UUID,
    candidate_bucket: str | None = Query(None),
    review_status: str | None = Query(None),
    promotion_status: str | None = Query(None),
    proposed_scope: str | None = Query(None),
    district: str | None = Query(None),
    subdistrict: str | None = Query(None),
    block: str | None = Query(None),
    vlcode: str | None = Query(None),
    backend_village_lgd_code: str | None = Query(None),
    parent_mismatch_only: bool = Query(False),
    unresolved_only: bool = Query(False),
    special_reference_only: bool = Query(False),
    has_review_history: bool | None = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    if not db.execute(text("select 1 from geography_boundary_import_batches where id = :batch_id"), {"batch_id": str(batch_id)}).first():
        raise HTTPException(status_code=404, detail="NWDP boundary batch not found")

    where = ["c.import_batch_id = :batch_id"]
    params = {"batch_id": str(batch_id), "limit": limit}

    if candidate_bucket:
        where.append("c.candidate_bucket = :candidate_bucket")
        params["candidate_bucket"] = candidate_bucket
    if review_status:
        where.append("c.review_status = :review_status")
        params["review_status"] = review_status
    if promotion_status:
        where.append("c.promotion_status = :promotion_status")
        params["promotion_status"] = promotion_status
    if proposed_scope:
        where.append("c.proposed_scope = :proposed_scope")
        params["proposed_scope"] = proposed_scope
    if district:
        where.append("f.source_district_name ilike :district")
        params["district"] = f"%{district}%"
    if subdistrict:
        where.append("f.source_subdistrict_name ilike :subdistrict")
        params["subdistrict"] = f"%{subdistrict}%"
    if block:
        where.append("f.source_block_name ilike :block")
        params["block"] = f"%{block}%"
    if vlcode:
        where.append("f.source_vlcode = :vlcode")
        params["vlcode"] = vlcode
    if backend_village_lgd_code:
        where.append("c.proposed_village_lgd_code = :backend_village_lgd_code")
        params["backend_village_lgd_code"] = backend_village_lgd_code
    if parent_mismatch_only:
        where.append("c.candidate_bucket = 'DIRECT_VLCODE_PARENT_MISMATCH'")
    if unresolved_only:
        where.append("c.candidate_bucket in ('PARENT_MATCH_VILLAGE_UNRESOLVED', 'DISTRICT_SCOPED_AMBIGUOUS')")
    if special_reference_only:
        where.append("c.candidate_bucket = 'SPECIAL_REFERENCE_FEATURE'")
    if has_review_history is True:
        where.append("jsonb_array_length(coalesce(c.metadata->'review_history', '[]'::jsonb)) > 0")
    elif has_review_history is False:
        where.append("jsonb_array_length(coalesce(c.metadata->'review_history', '[]'::jsonb)) = 0")

    where_sql = " and ".join(where)

    rows = db.execute(text(f"""
        select
          c.source_feature_index,
          c.candidate_bucket,
          c.confidence,
          c.review_status,
          c.reviewer_decision,
          c.promotion_status,
          c.proposed_scope,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_vlcode,
          c.proposed_village_lgd_code,
          c.proposed_village_id::text,
          jsonb_array_length(coalesce(c.metadata->'review_history', '[]'::jsonb)) as review_history_count,
          c.is_active
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where {where_sql}
        order by c.source_feature_index
        limit :limit
    """), params).mappings().all()

    output = io.StringIO()
    fieldnames = [
        "source_feature_index", "candidate_bucket", "confidence", "review_status",
        "reviewer_decision", "promotion_status", "proposed_scope",
        "source_district_name", "source_subdistrict_name", "source_block_name",
        "source_village_name", "source_vlcode", "proposed_village_lgd_code",
        "proposed_village_id", "review_history_count", "is_active",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})

    output.seek(0)
    headers = {
        "Content-Disposition": "attachment; filename=nwdp-boundary-candidates.csv",
        "X-NWDP-Boundary-Export-Mode": "READ_ONLY_ADMIN_REVIEW",
        "X-NWDP-Boundary-Runtime-Spatial-Matching-Changed": "false",
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@router.get("/nwdp-boundary-candidates/{candidate_id}", response_model=NwdpBoundaryCandidateDetailResponse)
def get_nwdp_boundary_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    row = db.execute(text("""
        select
          c.id::text as candidate_id,
          c.import_batch_id::text as batch_id,
          c.source_feature_id::text,
          c.source_feature_index,
          c.candidate_bucket,
          c.confidence,
          c.review_status,
          c.proposed_scope,
          c.proposed_state_id::text,
          c.proposed_district_id::text,
          c.proposed_block_id::text,
          c.proposed_village_id::text,
          c.proposed_state_lgd_code,
          c.proposed_district_lgd_code,
          c.proposed_block_lgd_code,
          c.proposed_village_lgd_code,
          c.source_codes,
          c.source_names,
          c.match_evidence,
          c.reviewer_decision,
          c.reviewer_id,
          c.reviewed_at,
          c.reviewer_notes,
          c.promotion_status,
          c.is_active,
          c.metadata as candidate_metadata,
          f.source_stcode,
          f.source_dtcode,
          f.source_sdcode,
          f.source_bkcode,
          f.source_vlcode,
          f.source_state_name,
          f.source_district_name,
          f.source_subdistrict_name,
          f.source_block_name,
          f.source_village_name,
          f.source_agency,
          f.feature_category,
          f.source_properties,
          f.source_geometry_hash,
          f.source_bbox,
          f.transformed_bbox,
          f.transformed_centroid,
          f.geometry_validation_status,
          b.manifest_audit,
          b.geometry_audit,
          b.crosswalk_audit
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features f on f.id = c.source_feature_id
        join geography_boundary_import_batches b on b.id = c.import_batch_id
        where c.id = :candidate_id
    """), {"candidate_id": str(candidate_id)}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="NWDP boundary candidate not found")

    data = dict(row)
    candidate = {
        key: data.get(key)
        for key in [
            "candidate_id", "batch_id", "source_feature_id", "source_feature_index",
            "candidate_bucket", "confidence", "review_status", "proposed_scope",
            "reviewer_decision", "reviewer_id", "reviewed_at", "reviewer_notes",
            "promotion_status", "is_active",
        ]
    }
    source_feature = {
        key: data.get(key)
        for key in [
            "source_stcode", "source_dtcode", "source_sdcode", "source_bkcode", "source_vlcode",
            "source_state_name", "source_district_name", "source_subdistrict_name",
            "source_block_name", "source_village_name", "source_agency", "feature_category",
            "source_properties", "source_geometry_hash", "source_bbox", "transformed_bbox",
            "transformed_centroid", "geometry_validation_status",
        ]
    }
    proposed_match = {
        key: data.get(key)
        for key in [
            "proposed_state_id", "proposed_district_id", "proposed_block_id", "proposed_village_id",
            "proposed_state_lgd_code", "proposed_district_lgd_code",
            "proposed_block_lgd_code", "proposed_village_lgd_code",
            "source_codes", "source_names", "match_evidence",
        ]
    }

    return {
        "schema_version": "nwdp_boundary_admin_candidate_detail.v1",
        "mode": "READ_ONLY_ADMIN_REVIEW",
        "governance": _nwdp_boundary_governance(),
        "candidate": candidate,
        "source_feature": source_feature,
        "proposed_match": proposed_match,
        "audit_evidence": {
            "manifest_audit": _jsonish(data.get("manifest_audit")),
            "geometry_audit": _jsonish(data.get("geometry_audit")),
            "crosswalk_audit": _jsonish(data.get("crosswalk_audit")),
        },
        "review_history": list((data.get("candidate_metadata") or {}).get("review_history") or []),
        "allowed_review_decisions": [
            "KEEP_PENDING",
            "ACCEPT_DIRECT_CODE_MATCH",
            "ACCEPT_REVIEWED_NAME_MATCH",
            "MARK_REFERENCE_ONLY",
            "REJECT_SOURCE_MISMATCH",
            "REJECT_SPECIAL_FEATURE",
            "BLOCK_PENDING_SOURCE_REVIEW",
        ],
    }


@router.patch("/nwdp-boundary-candidates/{candidate_id}/review")
def update_nwdp_boundary_candidate_review(
    candidate_id: UUID,
    payload: NwdpBoundaryCandidateReviewRequest,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.EDIT)),
):
    row = db.execute(text("""
        select
          id::text as candidate_id,
          candidate_bucket,
          review_status,
          reviewer_decision,
          promotion_status,
          is_active,
          metadata
        from geography_boundary_crosswalk_candidates
        where id = :candidate_id
    """), {"candidate_id": str(candidate_id)}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="NWDP boundary candidate not found")

    if row["is_active"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ACTIVE_BOUNDARY_CANDIDATE_NOT_REVIEW_EDITABLE",
                "message": "Active candidates cannot be changed through the review endpoint.",
            },
        )

    if row["promotion_status"] != "NOT_PROMOTED":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "PROMOTED_BOUNDARY_CANDIDATE_NOT_REVIEW_EDITABLE",
                "message": "Promoted candidates require a separate supersession workflow.",
            },
        )

    notes = (payload.reviewer_notes or "").strip()
    if payload.reviewer_decision != "KEEP_PENDING" and len(notes) < 3:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "REVIEW_NOTES_REQUIRED",
                "message": "Reviewer notes are required for non-pending NWDP boundary decisions.",
            },
        )

    if row["candidate_bucket"] == "SPECIAL_REFERENCE_FEATURE" and payload.review_status == "APPROVED_FOR_PROMOTION":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "SPECIAL_REFERENCE_FEATURE_CANNOT_BE_APPROVED_FOR_PROMOTION",
                "message": "Special/reference features may be marked reference-only, rejected, or blocked, but not approved for promotion.",
            },
        )

    if payload.reviewer_decision == "MARK_REFERENCE_ONLY" and payload.review_status != "REFERENCE_ONLY":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "REFERENCE_ONLY_STATUS_REQUIRED",
                "message": "MARK_REFERENCE_ONLY requires review_status=REFERENCE_ONLY.",
            },
        )

    if payload.reviewer_decision == "REJECT_SPECIAL_FEATURE" and payload.review_status != "REJECTED":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "REJECTED_STATUS_REQUIRED",
                "message": "REJECT_SPECIAL_FEATURE requires review_status=REJECTED.",
            },
        )

    previous_status = row["review_status"]
    previous_decision = row["reviewer_decision"]
    metadata = dict(row["metadata"] or {})
    history = list(metadata.get("review_history") or [])
    event = {
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "changed_by": str(principal.user_id),
        "from_review_status": previous_status,
        "to_review_status": payload.review_status,
        "from_reviewer_decision": previous_decision,
        "to_reviewer_decision": payload.reviewer_decision,
        "reviewer_notes": notes,
        "evidence_summary": payload.evidence_summary,
        "action": "NWDP_BOUNDARY_REVIEW_METADATA_ONLY_NO_ACTIVATION",
    }
    history.append(event)
    metadata["review_history"] = history
    metadata["latest_review_event"] = event
    metadata["review_guardrail"] = {
        "is_active_remains_false": True,
        "promotion_status_remains_not_promoted": True,
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
    }

    db.execute(text("""
        update geography_boundary_crosswalk_candidates
        set
          review_status = :review_status,
          reviewer_decision = :reviewer_decision,
          reviewer_id = :reviewer_id,
          reviewed_at = :reviewed_at,
          reviewer_notes = :reviewer_notes,
          metadata = cast(:metadata as jsonb),
          updated_at = :updated_at
        where id = :candidate_id
          and is_active = false
          and promotion_status = 'NOT_PROMOTED'
    """), {
        "candidate_id": str(candidate_id),
        "review_status": payload.review_status,
        "reviewer_decision": payload.reviewer_decision,
        "reviewer_id": str(principal.user_id),
        "reviewed_at": datetime.now(timezone.utc),
        "reviewer_notes": notes,
        "metadata": json.dumps(metadata),
        "updated_at": datetime.now(timezone.utc),
    })
    db.commit()

    return {
        "schema_version": "nwdp_boundary_admin_candidate_review.v1",
        "candidate_id": str(candidate_id),
        "previous_review_status": previous_status,
        "review_status": payload.review_status,
        "previous_reviewer_decision": previous_decision,
        "reviewer_decision": payload.reviewer_decision,
        "is_active": False,
        "promotion_status": "NOT_PROMOTED",
        "runtime_spatial_matching_changed": False,
        "android_behavior_changed": False,
        "promotion_supported": False,
        "latest_review_event": event,
    }




@router.get("/nwdp-demographic-profiles/promotion/dry-run")
def get_nwdp_demographic_profile_promotion_dry_run(
    state_or_ut: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only dry-run for future NWDP demographic profile promotion.

    This endpoint only counts/samples inactive NOT_PROMOTED profile rows that
    have already been approved for promotion by admin review. It does not
    promote, activate, enable runtime lookup, or change Android behavior.
    """

    filters = {
        "state_or_ut": state_or_ut,
        "district": district,
        "limit": limit,
    }

    where_parts = [
        "review_status = 'APPROVED_FOR_PROMOTION'",
        "promotion_status = 'NOT_PROMOTED'",
        "is_active = false",
        "source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'",
    ]
    params = {"limit": limit}

    if state_or_ut:
        where_parts.append("source_state_name = :state_or_ut")
        params["state_or_ut"] = state_or_ut

    if district:
        where_parts.append("source_district_name = :district")
        params["district"] = district

    where_sql = " AND ".join(where_parts)

    summary = db.execute(text(f"""
        SELECT
          COUNT(*)::bigint AS eligible_profile_row_count,
          COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
          COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count,
          COUNT(*) FILTER (WHERE review_status = 'APPROVED_FOR_PROMOTION')::bigint AS approved_for_promotion_count
        FROM geography_village_demographic_profiles
        WHERE {where_sql}
    """), params).mappings().one()

    state_district_rows = db.execute(text(f"""
        SELECT
          source_state_name AS state_or_ut,
          source_district_name AS district,
          COUNT(*)::bigint AS eligible_profile_row_count,
          COUNT(*) FILTER (WHERE review_status = 'APPROVED_FOR_PROMOTION')::bigint AS approved_for_promotion_count,
          COUNT(*) FILTER (WHERE is_active = TRUE)::bigint AS active_profile_row_count,
          COUNT(*) FILTER (WHERE promotion_status = 'PROMOTED')::bigint AS promoted_profile_row_count
        FROM geography_village_demographic_profiles
        WHERE {where_sql}
        GROUP BY source_state_name, source_district_name
        ORDER BY source_state_name NULLS LAST, source_district_name NULLS LAST
        LIMIT :limit
    """), params).mappings().all()

    sample_rows = db.execute(text(f"""
        SELECT
          id::text AS profile_id,
          village_id::text AS village_id,
          source_state_name AS state_or_ut,
          source_district_name AS district,
          source_subdistrict_name,
          source_village_name,
          source_vlcode,
          total_population,
          total_households,
          rural_urban,
          review_status,
          promotion_status,
          is_active
        FROM geography_village_demographic_profiles
        WHERE {where_sql}
        ORDER BY source_state_name NULLS LAST, source_district_name NULLS LAST, source_village_name NULLS LAST
        LIMIT :limit
    """), params).mappings().all()

    summary = {key: int(value or 0) for key, value in summary.items()}
    eligible = summary["eligible_profile_row_count"]

    return {
        "schema_version": "nwdp_demographic_profile_promotion_dry_run.v1",
        "mode": "read_only_promotion_dry_run",
        "healthy": True,
        "enabled": eligible > 0,
        "reason": None if eligible > 0 else "NO_APPROVED_INACTIVE_NOT_PROMOTED_DEMOGRAPHIC_PROFILES",
        "claim_boundary": (
            "Promotion dry-run is read-only. It reports inactive, not-promoted "
            "NWDP demographic profile rows that have been approved by admin "
            "review, but does not promote profiles, activate rows, enable "
            "runtime lookup, or change Android behavior."
        ),
        "filters": filters,
        "selection_policy": {
            "required_source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "required_review_status": "APPROVED_FOR_PROMOTION",
            "required_promotion_status": "NOT_PROMOTED",
            "required_is_active": False,
            "state_or_district_scope_recommended": True,
        },
        "summary": summary,
        "state_district_summary": [
            {
                key: (int(value or 0) if key.endswith("_count") else value)
                for key, value in row.items()
            }
            for row in state_district_rows
        ],
        "items": [dict(row) for row in sample_rows],
        "readiness": {
            "ready_for_profile_promotion_apply": False,
            "ready_for_profile_activation": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "ready_for_official_census_import": False,
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
    }


@router.patch("/nwdp-demographic-profiles/{profile_id}/review")
def update_nwdp_demographic_profile_review(
    profile_id: UUID,
    payload: NwdpDemographicProfileReviewRequest,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Admin review update for inactive NWDP demographic profile rows.

    This endpoint mirrors the guarded boundary candidate review style. It only
    updates review metadata/status; it does not promote, activate, enable runtime
    lookup, or change Android behavior.
    """

    row = db.execute(text("""
        select
          id::text as profile_id,
          review_status,
          promotion_status,
          is_active,
          source_system,
          source_version,
          source_state_name,
          source_district_name,
          source_village_name,
          source_vlcode,
          match_evidence
        from geography_village_demographic_profiles
        where id = :profile_id
    """), {"profile_id": str(profile_id)}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="NWDP demographic profile not found")

    if row["is_active"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ACTIVE_DEMOGRAPHIC_PROFILE_NOT_REVIEW_EDITABLE",
                "message": "Active demographic profile rows cannot be changed through the review endpoint.",
            },
        )

    if row["promotion_status"] != "NOT_PROMOTED":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "PROMOTED_DEMOGRAPHIC_PROFILE_NOT_REVIEW_EDITABLE",
                "message": "Promoted demographic profiles require a separate supersession workflow.",
            },
        )

    if row["source_system"] != "NWDP_GSI_VILLAGE_BOUNDARY":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "NON_NWDP_DEMOGRAPHIC_PROFILE_NOT_REVIEW_EDITABLE",
                "message": "Only NWDP-derived demographic profile rows are editable through this endpoint.",
            },
        )

    expected = {
        "MARK_MANUAL_REVIEW": "MANUAL_REVIEW",
        "APPROVE_FOR_PROMOTION": "APPROVED_FOR_PROMOTION",
        "REJECT_PROFILE": "REJECTED",
        "BLOCK_PROFILE": "BLOCKED",
    }
    if expected[payload.reviewer_decision] != payload.review_status:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "REVIEW_DECISION_STATUS_MISMATCH",
                "message": "Reviewer decision must match the requested demographic profile review status.",
            },
        )

    notes = (payload.reviewer_notes or "").strip()
    if len(notes) < 3:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "REVIEW_NOTES_REQUIRED",
                "message": "Reviewer notes are required for NWDP demographic profile review changes.",
            },
        )

    previous_status = row["review_status"]
    previous_evidence = row["match_evidence"]
    metadata = dict(previous_evidence or {})
    history = list(metadata.get("review_history") or [])

    event = {
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "changed_by": str(principal.user_id),
        "from_review_status": previous_status,
        "to_review_status": payload.review_status,
        "reviewer_decision": payload.reviewer_decision,
        "reviewer_notes": notes,
        "evidence_summary": payload.evidence_summary,
        "action": "NWDP_DEMOGRAPHIC_PROFILE_REVIEW_METADATA_ONLY_NO_PROMOTION",
    }

    history.append(event)
    metadata["review_history"] = history
    metadata["latest_review_event"] = event
    metadata["review_guardrail"] = {
        "is_active_remains_false": True,
        "promotion_status_remains_not_promoted": True,
        "runtime_lookup_changed": False,
        "android_behavior_changed": False,
        "official_census_claimed_imported": False,
    }

    db.execute(text("""
        update geography_village_demographic_profiles
        set
          review_status = :review_status,
          match_evidence = cast(:match_evidence as jsonb),
          updated_at = :updated_at
        where id = :profile_id
          and is_active = false
          and promotion_status = 'NOT_PROMOTED'
          and source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
    """), {
        "profile_id": str(profile_id),
        "review_status": payload.review_status,
        "match_evidence": json.dumps(metadata),
        "updated_at": datetime.now(timezone.utc),
    })
    db.commit()

    return {
        "schema_version": "nwdp_demographic_profile_admin_review.v1",
        "profile_id": str(profile_id),
        "previous_review_status": previous_status,
        "review_status": payload.review_status,
        "reviewer_decision": payload.reviewer_decision,
        "is_active": False,
        "promotion_status": "NOT_PROMOTED",
        "profile_review_status_changed": True,
        "profiles_promoted": False,
        "profile_rows_activated": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "official_census_claimed_imported": False,
        "promotion_supported": False,
        "latest_review_event": event,
    }


@router.get("/hierarchy-profile")
def geography_hierarchy_profile():
    return {
        'schema_version': 'geography_hierarchy_profile.v1',
        'mode': 'INDIA_COMPATIBILITY_CURRENT_TABLES',
        'default_country_code': 'IN',
        'canonical_source': {
            'source_system': 'LGD',
            'name': 'Local Government Directory',
            'role': 'canonical_government_hierarchy_for_india',
        },
        'supporting_sources': [
            {'source_system': 'CENSUS', 'role': 'reference_names_codes_aliases'},
            {'source_system': 'PIN_CODE', 'role': 'postal_code_to_locality_candidates'},
        ],
        'levels': [
            {'level_code': 'COUNTRY', 'label': {'en': 'Country'}, 'source_field': 'country_code', 'required': True, 'endpoint': None},
            {'level_code': 'STATE', 'label': {'en': 'State / Union Territory'}, 'source_field': 'state_id', 'required': True, 'endpoint': '/api/v1/master-data/geography/states'},
            {'level_code': 'DISTRICT', 'label': {'en': 'District'}, 'source_field': 'district_id', 'required': True, 'endpoint': '/api/v1/master-data/geography/districts?state_id={state_id}'},
            {'level_code': 'SUB_DISTRICT', 'label': {'en': 'Block / Tehsil / Taluk'}, 'source_field': 'block_id', 'required': False, 'endpoint': '/api/v1/master-data/geography/blocks?district_id={district_id}'},
            {'level_code': 'LOCALITY', 'label': {'en': 'Village / Town / Locality'}, 'source_field': 'village_id', 'required': True, 'endpoint': '/api/v1/master-data/geography/villages?block_id={block_id}'},
            {'level_code': 'POSTAL_CODE', 'label': {'en': 'PIN / Postal code'}, 'source_field': 'pin_code', 'required': False, 'endpoint': '/api/v1/master-data/geography/villages/by-pin-code?pin_code={pin_code}'},
        ],
        'global_model_target': {
            'entity_table': 'geo_entity',
            'alias_table': 'geo_entity_alias',
            'postal_code_table': 'geo_entity_postal_code',
            'admin_level_profile_table': 'geo_admin_level_profile',
            'import_batch_table': 'geo_import_batch',
            'status': 'ROADMAP_NOT_MIGRATED',
        },
        'governance': {
            'canonical_government_fields_editable': False,
            'admin_editable_fields': ['aliases', 'translations', 'display_labels', 'postal_code_associations', 'operational_groupings', 'expires_at', 'is_active'],
            'canonical_corrections_require_verified_import': True,
            'physical_delete_allowed': False,
        },
        'android_guidance': {
            'do_not_hardcode_fixed_level_count': True,
            'render_levels_from_backend_profile': True,
            'india_current_flow_supported': True,
            'offline_cache_key': 'country_code:IN/geography_profile:v1',
        },
    }



@router.get(
    "/core-lgd-mapping-review",
    response_model=CoreLgdMappingReviewResponse,
)
def core_lgd_mapping_review(
    state_lgd_code: Optional[str] = Query(None, description="Optional state LGD code filter"),
    district_lgd_code: Optional[str] = Query(None, description="Optional district LGD code filter"),
    region_system: Optional[str] = Query(None, description="Optional CoRE region system filter"),
    promotion_decision: Optional[str] = Query(None, description="Optional review decision bucket filter"),
    review_status: Optional[str] = Query(None, description="Optional candidate review status filter"),
    search: Optional[str] = Query(None, min_length=2, description="Optional district/state/region search"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only admin report for inactive CoRE/LGD polygon-derived mapping candidates."""
    base_sql = """
        with fallback as (
          select
            m.state_lgd_code,
            m.district_lgd_code,
            count(*) as active_fallback_count,
            string_agg(m.region_code, ' | ' order by m.region_code) as active_fallback_region_codes,
            string_agg(coalesce(r.region_name, m.region_code), ' | ' order by m.region_code) as active_fallback_region_names,
            string_agg(coalesce(r.region_system, 'UNKNOWN'), ' | ' order by m.region_code) as active_fallback_region_systems,
            string_agg(m.confidence, ' | ' order by m.region_code) as active_fallback_confidences
          from geography_climate_region_mappings m
          left join geography_climate_regions r on r.id = m.region_id
          where m.is_active is true
            and m.confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
          group by m.state_lgd_code, m.district_lgd_code
        ),
        poly as (
          select
            m.id as poly_mapping_id,
            m.region_id as poly_region_id,
            m.state_lgd_code,
            m.district_lgd_code,
            m.region_code as poly_region_code,
            m.confidence as poly_confidence,
            m.review_status as poly_review_status,
            m.is_active as poly_is_active,
          m.version as poly_version,
            r.region_name as poly_region_name,
            r.region_system as poly_region_system,
            m.metadata ->> 'state_name' as state_name,
            m.metadata ->> 'district_name' as district_name,
            m.metadata ->> 'region_class_name' as poly_region_class_name,
            m.metadata ->> 'region_class_code' as poly_region_class_code,
            nullif(m.metadata ->> 'overlap_percent_of_district', '')::numeric as overlap_percent_of_district,
            m.metadata ->> 'crosswalk_category' as crosswalk_category,
            coalesce(nullif(m.metadata ->> 'low_overlap_bucket', ''), 'NOT_LOW_OVERLAP') as low_overlap_bucket
          from geography_climate_region_mappings m
          left join geography_climate_regions r on r.id = m.region_id          where (
            (m.confidence = 'POLY_REV' and m.is_active is false)
            or (m.confidence = 'POLY_APPR' and m.is_active is true and m.review_status = 'PROMOTED')
          )
        ),
        reviewed as (
          select
            poly.*,
            fallback.active_fallback_count,
            fallback.active_fallback_region_codes,
            fallback.active_fallback_region_names,
            fallback.active_fallback_region_systems,
            fallback.active_fallback_confidences,
            case
              when poly.poly_confidence = 'POLY_APPR' and poly.poly_is_active is true
                then 'PROMOTED_ACTIVE'
              when coalesce(poly.low_overlap_bucket, 'NOT_LOW_OVERLAP') in ('SOURCE_VERSION_DRIFT', 'SOURCE_VERSION_CONFLICT')
                then 'BLOCKED_SOURCE_VERSION'
              when coalesce(poly.crosswalk_category, '') in ('BHARATLAS_ONLY', 'STATE_CODE_MISMATCH', 'UNSET')
                then 'BLOCKED_CROSSWALK'
              when coalesce(poly.low_overlap_bucket, 'NOT_LOW_OVERLAP') <> 'NOT_LOW_OVERLAP'
                then 'MANUAL_REVIEW_LOW_OVERLAP'
              when poly.overlap_percent_of_district < 80
                then 'MANUAL_REVIEW_LOW_OVERLAP'
              when poly.state_lgd_code in ('29', '27', '3') and fallback.active_fallback_count is not null
                then 'PILOT_REVIEW_REPLACES_FALLBACK'
              when poly.state_lgd_code in ('29', '27', '3')
                then 'PILOT_REVIEW_NEW_MAPPING'
              when fallback.active_fallback_count is not null
                then 'GENERAL_REVIEW_REPLACES_FALLBACK'
              else 'GENERAL_REVIEW_NEW_MAPPING'
            end as promotion_decision
          from poly
          left join fallback
            on fallback.state_lgd_code is not distinct from poly.state_lgd_code
           and fallback.district_lgd_code is not distinct from poly.district_lgd_code
        )
    """

    where_clauses = []
    params = {"offset": offset, "limit": limit}
    if state_lgd_code:
        where_clauses.append("state_lgd_code = :state_lgd_code")
        params["state_lgd_code"] = state_lgd_code.strip()
    if district_lgd_code:
        where_clauses.append("district_lgd_code = :district_lgd_code")
        params["district_lgd_code"] = district_lgd_code.strip()
    if region_system:
        where_clauses.append("poly_region_system = :region_system")
        params["region_system"] = region_system.strip()
    if promotion_decision:
        where_clauses.append("promotion_decision = :promotion_decision")
        params["promotion_decision"] = promotion_decision.strip()
    if review_status:
        where_clauses.append("poly_review_status = :review_status")
        params["review_status"] = review_status.strip()
    if search:
        where_clauses.append("(district_name ilike :search or state_name ilike :search or poly_region_name ilike :search or poly_region_code ilike :search)")
        params["search"] = f"%{search.strip()}%"

    where_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""

    items = db.execute(text(f"""
        {base_sql}
        select
          poly_mapping_id::text,
          poly_region_id::text,
          state_lgd_code,
          state_name,
          district_lgd_code,
          district_name,
          poly_region_system,
          poly_region_code,
          poly_region_name,
          poly_review_status,
          poly_confidence,
          poly_is_active,
          poly_version,
          poly_region_class_code,
          poly_region_class_name,
          overlap_percent_of_district,
          crosswalk_category,
          low_overlap_bucket,
          active_fallback_count,
          active_fallback_region_codes,
          active_fallback_region_names,
          active_fallback_region_systems,
          active_fallback_confidences,
          promotion_decision
        from reviewed
        {where_sql}
        order by state_lgd_code, district_lgd_code, poly_region_system, poly_region_code
        offset :offset
        limit :limit
    """), params).mappings().all()

    total = db.execute(text(f"{base_sql} select count(*) from reviewed {where_sql}"), params).scalar_one()

    decision_counts = db.execute(text(f"""
        {base_sql}
        select promotion_decision, count(*) as count
        from reviewed
        {where_sql}
        group by promotion_decision
        order by promotion_decision
    """), params).mappings().all()

    state_counts = db.execute(text(f"""
        {base_sql}
        select state_lgd_code, state_name, count(*) as count
        from reviewed
        {where_sql}
        group by state_lgd_code, state_name
        order by state_lgd_code
    """), params).mappings().all()

    region_system_counts = db.execute(text(f"""
        {base_sql}
        select poly_region_system as region_system, count(*) as count
        from reviewed
        {where_sql}
        group by poly_region_system
        order by poly_region_system
    """), params).mappings().all()

    return {
        "schema_version": "core_lgd_mapping_review_admin.v1",
        "mode": "READ_ONLY_ADMIN_REVIEW",
        "filters": {
            "state_lgd_code": state_lgd_code,
            "district_lgd_code": district_lgd_code,
            "region_system": region_system,
            "promotion_decision": promotion_decision,
            "review_status": review_status,
            "search": search,
        },
        "summary": {
            "total": total,
            "offset": offset,
            "limit": limit,
            "land_intelligence_behavior_changed": False,
            "source_confidence": "POLY_REV/POLY_APPR",
            "source_rows_active": review_status == "PROMOTED",
        },
        "decision_counts": [dict(row) for row in decision_counts],
        "state_counts": [dict(row) for row in state_counts],
        "region_system_counts": [dict(row) for row in region_system_counts],
        "items": [dict(row) for row in items],
        "total": total,
        "offset": offset,
        "limit": limit,
        "governance": {
            "read_only": True,
            "promotion_supported": False,
            "promotion_requires_separate_review_workflow": True,
            "android_maestro_required": False,
        },
    }






@router.get("/core-lgd-mapping-review/summary")
def get_core_lgd_mapping_review_summary(
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only admin summary for inactive review queue and active promoted CoRE/LGD mappings."""
    active_total = db.execute(text("""
        select
          count(*)::int as mapping_rows,
          count(distinct state_lgd_code || '/' || district_lgd_code)::int as districts,
          count(distinct state_lgd_code)::int as states,
          count(distinct region_code)::int as region_codes
        from geography_climate_region_mappings
        where confidence = 'POLY_APPR'
          and review_status = 'PROMOTED'
          and version = 'clap_v1'
          and is_active is true
          and scope_level = 'DISTRICT'
    """)).mappings().first()

    active_by_state = [
        dict(row)
        for row in db.execute(text("""
            select
              state_lgd_code,
              coalesce(max(metadata ->> 'state_name'), state_lgd_code) as state_name,
              count(distinct district_lgd_code)::int as active_districts,
              count(*)::int as active_mapping_rows
            from geography_climate_region_mappings
            where confidence = 'POLY_APPR'
              and review_status = 'PROMOTED'
              and version = 'clap_v1'
              and is_active is true
              and scope_level = 'DISTRICT'
            group by state_lgd_code
            order by state_lgd_code
        """)).mappings()
    ]

    queue_total = db.execute(text("""
        select
          count(*)::int as mapping_rows,
          count(distinct state_lgd_code || '/' || district_lgd_code)::int as districts
        from geography_climate_region_mappings
        where confidence = 'POLY_REV'
          and is_active is false
          and scope_level = 'DISTRICT'
    """)).mappings().first()

    queue_status_counts = [
        dict(row)
        for row in db.execute(text("""
            select
              review_status,
              count(*)::int as mapping_rows,
              count(distinct state_lgd_code || '/' || district_lgd_code)::int as districts
            from geography_climate_region_mappings
            where confidence = 'POLY_REV'
              and is_active is false
              and scope_level = 'DISTRICT'
            group by review_status
            order by review_status
        """)).mappings()
    ]

    fallback_counts = [
        dict(row)
        for row in db.execute(text("""
            select
              confidence,
              is_active,
              count(*)::int as mapping_rows
            from geography_climate_region_mappings
            where confidence in ('LOCAL_DEMO_DISTRICT_FALLBACK', 'LOCAL_DEMO_SEED')
            group by confidence, is_active
            order by confidence, is_active
        """)).mappings()
    ]

    active_fallback_rows = sum(
        row["mapping_rows"]
        for row in fallback_counts
        if row["is_active"] is True
    )
    inactive_superseded_fallback_rows = sum(
        row["mapping_rows"]
        for row in fallback_counts
        if row["confidence"] == "LOCAL_DEMO_DISTRICT_FALLBACK" and row["is_active"] is False
    )

    return {
        "schema_version": "core_lgd_mapping_review_summary_admin.v1",
        "mode": "READ_ONLY_ADMIN_SUMMARY",
        "db_writes_made": False,
        "external_calls_made": False,
        "active_promoted": {
            "confidence": "POLY_APPR",
            "review_status": "PROMOTED",
            "version": "clap_v1",
            "mapping_rows": active_total["mapping_rows"] if active_total else 0,
            "districts": active_total["districts"] if active_total else 0,
            "states": active_total["states"] if active_total else 0,
            "region_codes": active_total["region_codes"] if active_total else 0,
            "by_state": active_by_state,
        },
        "inactive_review_queue": {
            "confidence": "POLY_REV",
            "mapping_rows": queue_total["mapping_rows"] if queue_total else 0,
            "districts": queue_total["districts"] if queue_total else 0,
            "review_status_counts": queue_status_counts,
        },
        "fallbacks": {
            "active_fallback_rows": active_fallback_rows,
            "inactive_superseded_fallback_rows": inactive_superseded_fallback_rows,
            "counts": fallback_counts,
        },
        "readiness": {
            "safe_read_only": True,
            "active_promoted_rows_present": bool(active_total and active_total["mapping_rows"]),
            "manual_review_queue_present": bool(queue_total and queue_total["mapping_rows"]),
        },
    }


@router.patch("/core-lgd-mapping-review/{mapping_id}/review")
def update_core_lgd_mapping_review_decision(
    mapping_id: UUID,
    payload: CoreLgdMappingReviewDecisionRequest,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.EDIT)),
):
    """Set review decision for an inactive POLY_REV candidate without activation."""
    row = db.execute(text("""
        select
          id::text,
          region_code,
          state_lgd_code,
          district_lgd_code,
          review_status,
          is_active,
          confidence,
          metadata
        from geography_climate_region_mappings
        where id = :mapping_id
          and confidence = 'POLY_REV'
    """), {"mapping_id": str(mapping_id)}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="POLY_REV mapping candidate not found")

    if row["is_active"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ACTIVE_MAPPING_NOT_REVIEW_EDITABLE",
                "message": "Active mappings cannot be changed through the review-decision endpoint.",
            },
        )

    previous_status = row["review_status"]
    metadata = dict(row["metadata"] or {})
    history = list(metadata.get("review_decision_history") or [])
    event = {
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "changed_by": str(principal.user_id),
        "from_status": previous_status,
        "to_status": payload.review_status,
        "review_notes": payload.review_notes,
        "action": "REVIEW_DECISION_ONLY_NO_ACTIVATION",
    }
    history.append(event)
    metadata["review_decision_history"] = history
    metadata["latest_review_decision"] = event
    metadata["promotion_guardrail"] = {
        "is_active_remains_false": True,
        "land_intelligence_behavior_changed": False,
        "activation_requires_separate_workflow": True,
    }

    db.execute(text("""
        update geography_climate_region_mappings
        set
          review_status = :review_status,
          metadata = cast(:metadata as jsonb),
          updated_at = :updated_at
        where id = :mapping_id
          and confidence = 'POLY_REV'
          and is_active is false
    """), {
        "mapping_id": str(mapping_id),
        "review_status": payload.review_status,
        "metadata": json.dumps(metadata),
        "updated_at": datetime.now(timezone.utc),
    })
    db.commit()

    return {
        "schema_version": "core_lgd_mapping_review_decision.v1",
        "mapping_id": str(mapping_id),
        "previous_review_status": previous_status,
        "review_status": payload.review_status,
        "is_active": False,
        "land_intelligence_behavior_changed": False,
        "promotion_supported": False,
        "activation_requires_separate_workflow": True,
        "latest_review_decision": event,
    }



@router.get(
    "/projects/{project_id}/activation-preflight"
)
def get_project_geography_activation_preflight(
    project_id: UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal=Depends(
        require_admin_permission(AdminPermission.VIEW)
    ),
) -> dict:
    """Return read-only geography readiness before project activation."""
    preview = _nwdp_boundary_project_matching_project_preview(
        db,
        project_id,
        500,
    )
    project = preview["project"]

    if project["tenant_id"] != x_tenant_id:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    raw_scope = project.get("geography_scope") or {}
    if isinstance(raw_scope, str):
        try:
            raw_scope = json.loads(raw_scope)
        except Exception:
            raw_scope = {}
    if not isinstance(raw_scope, dict):
        raw_scope = {}

    raw_codes = raw_scope.get("village_lgd_codes") or []
    if not isinstance(raw_codes, list):
        raw_codes = []

    configured_codes = sorted({
        str(code).strip()
        for code in raw_codes
        if str(code).strip()
    })

    source_summary = preview["summary"]
    resolved_count = int(
        source_summary.get("project_village_count") or 0
    )
    eligible_count = int(
        source_summary.get(
            "villages_with_eligible_boundary",
        ) or 0
    )
    missing_count = int(
        source_summary.get(
            "villages_without_eligible_boundary",
        ) or 0
    )
    eligible_candidate_count = int(
        source_summary.get("eligible_candidate_count") or 0
    )
    manual_review_candidate_count = int(
        source_summary.get(
            "manual_review_candidate_count",
        ) or 0
    )
    blocked_candidate_count = int(
        source_summary.get("blocked_candidate_count") or 0
    )
    unresolved_count = max(
        len(configured_codes) - resolved_count,
        0,
    )

    blockers = []

    if project["status"] != "PLANNED":
        blockers.append({
            "code": "PROJECT_NOT_PLANNED",
            "count": 1,
            "message": (
                "Only a PLANNED project can be evaluated "
                "for activation."
            ),
        })

    if not configured_codes:
        blockers.append({
            "code": "EMPTY_GEOGRAPHY_SCOPE",
            "count": 1,
            "message": (
                "Configure at least one canonical village "
                "before activation."
            ),
        })

    if unresolved_count:
        blockers.append({
            "code": "UNRESOLVED_VILLAGE_CODES",
            "count": unresolved_count,
            "message": (
                f"{unresolved_count} configured village LGD "
                "codes do not resolve to active canonical villages."
            ),
        })

    if missing_count:
        blockers.append({
            "code": "MISSING_ELIGIBLE_BOUNDARIES",
            "count": missing_count,
            "message": (
                f"{missing_count} project villages do not have "
                "an eligible validated boundary candidate."
            ),
        })

    if blocked_candidate_count:
        blockers.append({
            "code": "BLOCKED_BOUNDARY_CANDIDATES",
            "count": blocked_candidate_count,
            "message": (
                f"{blocked_candidate_count} blocked boundary "
                "candidates require review."
            ),
        })

    if manual_review_candidate_count:
        blockers.append({
            "code": "MANUAL_BOUNDARY_REVIEW_REQUIRED",
            "count": manual_review_candidate_count,
            "message": (
                f"{manual_review_candidate_count} boundary "
                "candidates require manual review."
            ),
        })

    can_activate_geography = (
        project["status"] == "PLANNED"
        and bool(configured_codes)
        and unresolved_count == 0
        and missing_count == 0
        and blocked_candidate_count == 0
        and manual_review_candidate_count == 0
    )

    return {
        "schema_version": (
            "project_geography_activation_preflight.v1"
        ),
        "mode": "READ_ONLY_PROJECT_ACTIVATION_PREFLIGHT",
        "project": {
            "id": project["project_id"],
            "tenant_id": project["tenant_id"],
            "name": project["name"],
            "status": project["status"],
        },
        "summary": {
            "configured_village_code_count": len(
                configured_codes
            ),
            "resolved_village_count": resolved_count,
            "unresolved_village_code_count": unresolved_count,
            "villages_with_eligible_boundary": eligible_count,
            "villages_without_eligible_boundary": missing_count,
            "eligible_candidate_count": (
                eligible_candidate_count
            ),
            "manual_review_candidate_count": (
                manual_review_candidate_count
            ),
            "blocked_candidate_count": (
                blocked_candidate_count
            ),
            "coverage_ratio": (
                eligible_count / resolved_count
                if resolved_count
                else 0
            ),
        },
        "decision": {
            "can_activate_geography": can_activate_geography,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "advisory_only": True,
            "project_status_changed": False,
        },
        "policy": {
            "required_project_status": "PLANNED",
            "requires_non_empty_canonical_scope": True,
            "maximum_village_count": 500,
            "requires_all_codes_resolved": True,
            "requires_all_villages_to_have_eligible_boundary": (
                True
            ),
            "required_geometry_validation_status": "VALIDATED",
            "required_candidate_bucket": (
                "DIRECT_VLCODE_MATCH"
            ),
            "required_review_status": "AUTO_CANDIDATE",
            "manual_review_candidates_excluded": True,
            "blocked_candidates_excluded": True,
        },
        "links": {
            "project_scope": f"/projects#{project_id}",
            "scope_history": f"/projects#{project_id}",
            "boundary_review": (
                f"/nwdp-boundary-review?"
                f"project_id={project_id}"
            ),
        },
        "guardrails": {
            "database_writes_attempted": False,
            "project_status_changed": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "items": preview["items"],
    }



@router.get("/states", response_model=list[StateResponse])
def list_states(
    db: Session = Depends(get_db),
):
    """List all active states."""
    return (
        db.query(GeographyState)
        .filter(GeographyState.is_active == True)
        .order_by(GeographyState.canonical_name)
        .all()
    )


@router.get("/districts", response_model=list[DistrictResponse])
def list_districts(
    state_id: UUID = Query(..., description="Filter by state UUID"),
    db: Session = Depends(get_db),
):
    """List districts for a given state."""
    return (
        db.query(GeographyDistrict)
        .filter(
            GeographyDistrict.state_id == state_id,
            GeographyDistrict.is_active == True,
        )
        .order_by(GeographyDistrict.canonical_name)
        .all()
    )



@router.get("/villages/bulk-selection-preview")
def preview_village_bulk_selection(
    district_id: Optional[UUID] = Query(None),
    block_id: Optional[UUID] = Query(None),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
    principal=Depends(
        require_admin_permission(AdminPermission.VIEW)
    ),
) -> dict:
    """Preview canonical villages under one district or block."""
    if (district_id is None) == (block_id is None):
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide exactly one of district_id or block_id"
            ),
        )

    if block_id is not None:
        scope = db.execute(text("""
            select
              'BLOCK'::text as scope_type,
              block.id::text as scope_id,
              block.lgd_code::text as scope_lgd_code,
              block.canonical_name as scope_name,
              district.id::text as district_id,
              district.canonical_name as district_name,
              state.id::text as state_id,
              state.canonical_name as state_name
            from geography_blocks block
            join geography_districts district
              on district.id = block.district_id
             and district.is_active = true
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            where block.id = :scope_id
              and block.is_active = true
        """), {"scope_id": str(block_id)}).mappings().first()
        village_filter = "village.block_id = :scope_id"
        scope_id = str(block_id)
    else:
        scope = db.execute(text("""
            select
              'DISTRICT'::text as scope_type,
              district.id::text as scope_id,
              district.lgd_code::text as scope_lgd_code,
              district.canonical_name as scope_name,
              district.id::text as district_id,
              district.canonical_name as district_name,
              state.id::text as state_id,
              state.canonical_name as state_name
            from geography_districts district
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            where district.id = :scope_id
              and district.is_active = true
        """), {"scope_id": str(district_id)}).mappings().first()
        village_filter = "village.district_id = :scope_id"
        scope_id = str(district_id)

    if not scope:
        raise HTTPException(404, "Geography scope not found")

    rows = db.execute(text(f"""
        with scoped_villages as (
            select
              village.id as village_id,
              village.lgd_code::text as village_lgd_code,
              village.canonical_name as village_name,
              block.id as block_id,
              block.lgd_code::text as block_lgd_code,
              block.canonical_name as block_name,
              district.id as district_id,
              district.canonical_name as district_name,
              state.id as state_id,
              state.canonical_name as state_name
            from geography_villages village
            join geography_blocks block
              on block.id = village.block_id
             and block.is_active = true
            join geography_districts district
              on district.id = village.district_id
             and district.is_active = true
            join geography_states state
              on state.id = district.state_id
             and state.is_active = true
            where {village_filter}
              and village.is_active = true
              and village.lgd_code is not null
        ),
        candidate_status as (
            select
              candidate.proposed_village_id as village_id,
              bool_or(
                batch.source_system =
                  'NWDP_GSI_VILLAGE_BOUNDARY'
                and feature.geometry_validation_status =
                  'VALIDATED'
                and candidate.candidate_bucket =
                  'DIRECT_VLCODE_MATCH'
                and candidate.review_status =
                  'AUTO_CANDIDATE'
                and candidate.promotion_status =
                  'NOT_PROMOTED'
                and candidate.is_active = false
              ) as has_eligible_boundary,
              bool_or(
                batch.source_system =
                  'NWDP_GSI_VILLAGE_BOUNDARY'
                and candidate.review_status = 'BLOCKED'
                and candidate.promotion_status =
                  'NOT_PROMOTED'
                and candidate.is_active = false
              ) as has_blocked_candidate
            from geography_boundary_crosswalk_candidates candidate
            join geography_boundary_import_batches batch
              on batch.id = candidate.import_batch_id
            join geography_boundary_source_features feature
              on feature.id = candidate.source_feature_id
            join scoped_villages scoped
              on scoped.village_id =
                candidate.proposed_village_id
            group by candidate.proposed_village_id
        ),
        classified as (
            select
              scoped.*,
              case
                when coalesce(
                  status.has_eligible_boundary,
                  false
                )
                then 'ELIGIBLE'
                when coalesce(
                  status.has_blocked_candidate,
                  false
                )
                then 'BLOCKED'
                else 'MISSING'
              end as boundary_status
            from scoped_villages scoped
            left join candidate_status status
              on status.village_id = scoped.village_id
        )
        select
          village_id::text,
          village_lgd_code,
          village_name,
          block_id::text,
          block_lgd_code,
          block_name,
          district_id::text,
          district_name,
          state_id::text,
          state_name,
          boundary_status,
          count(*) over ()::bigint as total_village_count,
          count(*) filter (
            where boundary_status = 'ELIGIBLE'
          ) over ()::bigint as eligible_village_count,
          count(*) filter (
            where boundary_status = 'MISSING'
          ) over ()::bigint as missing_village_count,
          count(*) filter (
            where boundary_status = 'BLOCKED'
          ) over ()::bigint as blocked_village_count
        from classified
        order by village_name, village_lgd_code
        limit :limit
    """), {
        "scope_id": scope_id,
        "limit": limit,
    }).mappings().all()

    total = int(
        rows[0]["total_village_count"]
        if rows else 0
    )
    eligible = int(
        rows[0]["eligible_village_count"]
        if rows else 0
    )
    missing = int(
        rows[0]["missing_village_count"]
        if rows else 0
    )
    blocked = int(
        rows[0]["blocked_village_count"]
        if rows else 0
    )

    items = [
        {
            "village_id": row["village_id"],
            "village_lgd_code": row["village_lgd_code"],
            "village_name": row["village_name"],
            "block_id": row["block_id"],
            "block_lgd_code": row["block_lgd_code"],
            "block_name": row["block_name"],
            "district_id": row["district_id"],
            "district_name": row["district_name"],
            "state_id": row["state_id"],
            "state_name": row["state_name"],
            "boundary_status": row["boundary_status"],
        }
        for row in rows
    ]

    return {
        "schema_version":
            "geography_village_bulk_selection_preview.v1",
        "mode": "READ_ONLY_CANONICAL_VILLAGE_BULK_PREVIEW",
        "scope": dict(scope),
        "summary": {
            "total_village_count": total,
            "returned_village_count": len(items),
            "eligible_village_count": eligible,
            "missing_village_count": missing,
            "blocked_village_count": blocked,
            "selection_limit": 500,
            "scope_within_selection_limit": total <= 500,
            "can_select_entire_scope": total <= 500,
        },
        "items": items,
        "guardrails": {
            "database_write_performed": False,
            "results_truncated": len(items) < total,
            "oversized_scope_rejected": total > 500,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
    }


@router.get("/blocks", response_model=list[BlockResponse])
def list_blocks(
    district_id: UUID = Query(..., description="Filter by district UUID"),
    db: Session = Depends(get_db),
):
    """List blocks/sub-districts for a given district."""
    return (
        db.query(GeographyBlock)
        .filter(
            GeographyBlock.district_id == district_id,
            GeographyBlock.is_active == True,
        )
        .order_by(GeographyBlock.canonical_name)
        .all()
    )


@router.get("/villages", response_model=list[VillageResponse])
def list_villages(
    block_id: Optional[UUID] = Query(None, description="Filter by block UUID"),
    district_id: Optional[UUID] = Query(None, description="Filter by district UUID (district-wide search)"),
    search: Optional[str] = Query(None, min_length=2, description="Filter by name (ILIKE)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """List villages for a given block or district.

    Supports two modes:
    - block_id: villages in a specific block (original behavior)
    - district_id: ALL villages in a district (for district-wide caching)

    Limit raised to 5000 to support full district download for offline cache.
    Azamgarh has ~14K villages — use pagination for large districts.
    """
    if not block_id and not district_id:
        raise HTTPException(400, "Either block_id or district_id is required")

    query = db.query(GeographyVillage).filter(GeographyVillage.is_active == True)

    if block_id:
        query = query.filter(GeographyVillage.block_id == block_id)
    elif district_id:
        query = query.filter(GeographyVillage.district_id == district_id)

    if search:
        query = query.filter(
            GeographyVillage.canonical_name.ilike(f"%{search}%")
        )
    return (
        query
        .order_by(GeographyVillage.canonical_name)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get(
    "/villages/by-lgd-codes",
    response_model=list[PinCodeVillageResponse],
)
def villages_by_lgd_codes(
    lgd_codes: str = Query(
        ...,
        min_length=1,
        description="Comma-separated canonical village LGD codes",
    ),
    db: Session = Depends(get_db),
):
    """Resolve saved village LGD codes to their canonical hierarchy labels."""
    requested_codes = list(dict.fromkeys(
        code.strip()
        for code in lgd_codes.split(",")
        if code.strip()
    ))

    if not requested_codes:
        raise HTTPException(400, "At least one village LGD code is required")
    if len(requested_codes) > 500:
        raise HTTPException(400, "At most 500 village LGD codes may be resolved")
    if any(not code.isdigit() for code in requested_codes):
        raise HTTPException(
            400,
            "Village LGD codes must contain digits only",
        )

    rows = (
        db.query(
            GeographyVillage,
            GeographyBlock.canonical_name.label("block_name"),
            GeographyDistrict.canonical_name.label("district_name"),
            GeographyState.id.label("state_id"),
            GeographyState.canonical_name.label("state_name"),
        )
        .join(
            GeographyBlock,
            GeographyBlock.id == GeographyVillage.block_id,
        )
        .join(
            GeographyDistrict,
            GeographyDistrict.id == GeographyVillage.district_id,
        )
        .join(
            GeographyState,
            GeographyState.id == GeographyDistrict.state_id,
        )
        .filter(
            GeographyVillage.lgd_code.in_(requested_codes),
            GeographyVillage.is_active == True,
            GeographyBlock.is_active == True,
            GeographyDistrict.is_active == True,
            GeographyState.is_active == True,
        )
        .all()
    )

    rows_by_code = {
        row.GeographyVillage.lgd_code: row
        for row in rows
    }

    return [
        PinCodeVillageResponse(
            id=rows_by_code[code].GeographyVillage.id,
            lgd_code=rows_by_code[code].GeographyVillage.lgd_code,
            canonical_name=(
                rows_by_code[code].GeographyVillage.canonical_name
            ),
            block_id=rows_by_code[code].GeographyVillage.block_id,
            block_name=rows_by_code[code].block_name,
            district_id=rows_by_code[code].GeographyVillage.district_id,
            district_name=rows_by_code[code].district_name,
            state_id=rows_by_code[code].state_id,
            state_name=rows_by_code[code].state_name,
            pin_codes=rows_by_code[code].GeographyVillage.pin_codes,
        )
        for code in requested_codes
        if code in rows_by_code
    ]



@router.get("/villages/by-pin-code", response_model=PinCodeLookupResponse)
def villages_by_pin_code(
    pin_code: str = Query(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$", description="Indian 6-digit PIN code"),
    district_id: Optional[UUID] = Query(None, description="Optionally narrow LGD village candidates to a selected district"),
    limit: int = Query(100, ge=1, le=500),
    postal_limit: int = Query(25, ge=0, le=100, description="Maximum postal reference rows to include"),
    db: Session = Depends(get_db),
):
    """Return guardrail-friendly PIN lookup details for Android.

    PIN is postal identity, not village identity. Some valid postal PINs have
    LGD village candidates; some valid postal PINs are urban/core postal areas
    with no rural LGD village mapping. Android should render that distinction
    and should not treat an empty village list as an invalid PIN.
    """
    postal_count = (
        db.query(func.count(GeographyPostalReference.id))
        .filter(
            GeographyPostalReference.pin_code == pin_code,
            GeographyPostalReference.is_active == True,
        )
        .scalar()
        or 0
    )

    postal_rows = (
        db.query(GeographyPostalReference)
        .filter(
            GeographyPostalReference.pin_code == pin_code,
            GeographyPostalReference.is_active == True,
        )
        .order_by(
            GeographyPostalReference.postal_state_name,
            GeographyPostalReference.postal_district_name,
            GeographyPostalReference.office_name,
        )
        .limit(postal_limit)
        .all()
        if postal_limit > 0
        else []
    )

    candidate_query = (
        db.query(
            GeographyVillage,
            GeographyBlock.canonical_name.label("block_name"),
            GeographyDistrict.canonical_name.label("district_name"),
            GeographyState.id.label("state_id"),
            GeographyState.canonical_name.label("state_name"),
        )
        .join(GeographyVillagePinLink, GeographyVillagePinLink.geography_village_id == GeographyVillage.id)
        .join(GeographyBlock, GeographyBlock.id == GeographyVillage.block_id)
        .join(GeographyDistrict, GeographyDistrict.id == GeographyVillage.district_id)
        .join(GeographyState, GeographyState.id == GeographyDistrict.state_id)
        .filter(
            GeographyVillagePinLink.pin_code == pin_code,
            GeographyVillagePinLink.is_active == True,
            GeographyVillagePinLink.match_status == "MATCHED",
            GeographyVillage.is_active == True,
            GeographyBlock.is_active == True,
            GeographyDistrict.is_active == True,
            GeographyState.is_active == True,
        )
    )

    if district_id:
        candidate_query = candidate_query.filter(GeographyVillage.district_id == district_id)

    candidate_count = candidate_query.count()

    rows = (
        candidate_query
        .order_by(GeographyState.canonical_name, GeographyDistrict.canonical_name, GeographyBlock.canonical_name, GeographyVillage.canonical_name)
        .limit(limit)
        .all()
    )

    village_candidates = [
        PinCodeVillageResponse(
            id=row.GeographyVillage.id,
            lgd_code=row.GeographyVillage.lgd_code,
            canonical_name=row.GeographyVillage.canonical_name,
            block_id=row.GeographyVillage.block_id,
            block_name=row.block_name,
            district_id=row.GeographyVillage.district_id,
            district_name=row.district_name,
            state_id=row.state_id,
            state_name=row.state_name,
            pin_codes=row.GeographyVillage.pin_codes,
        )
        for row in rows
    ]

    postal_references = [
        PinCodePostalReferenceResponse(
            office_name=row.office_name,
            office_type=row.office_type,
            delivery_status=row.delivery_status,
            postal_district_name=row.postal_district_name,
            postal_state_name=row.postal_state_name,
            latitude=float(row.latitude) if row.latitude is not None else None,
            longitude=float(row.longitude) if row.longitude is not None else None,
        )
        for row in postal_rows
    ]

    if candidate_count > 0:
        status_reason = "LGD_VILLAGE_CANDIDATES_FOUND"
        message = "PIN code is valid and LGD village candidates are available."
    elif postal_count > 0:
        status_reason = "VALID_POSTAL_PIN_NO_LGD_VILLAGES"
        message = "PIN code is valid in India Post data, but no LGD rural village candidates are mapped to it."
    else:
        status_reason = "PIN_NOT_FOUND"
        message = "PIN code was not found in the active postal or LGD village-PIN reference data."

    return PinCodeLookupResponse(
        pin_code=pin_code,
        is_valid_postal_pin=postal_count > 0,
        has_lgd_village_candidates=candidate_count > 0,
        status_reason=status_reason,
        message=message,
        village_candidate_count=candidate_count,
        postal_reference_count=postal_count,
        village_candidates=village_candidates,
        postal_references=postal_references,
    )


@router.get("/villages/search", response_model=list[VillageSearchResult])
def search_villages(
    q: str = Query(..., min_length=2, description="Fuzzy search query"),
    district_id: Optional[UUID] = Query(None, description="Scope search to a district"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fuzzy search villages by name using pg_trgm.

    Returns results ranked by similarity score.
    Optionally scoped to a district for faster, more relevant results.
    Designed for mobile offline-cache miss scenarios.
    """
    if district_id:
        results = db.execute(
            text("""
                SELECT
                    v.id,
                    v.lgd_code,
                    v.canonical_name,
                    v.pin_codes,
                    v.block_id,
                    b.canonical_name as block_name,
                    v.district_id,
                    d.canonical_name as district_name,
                    s.id as state_id,
                    s.canonical_name as state_name,
                    similarity(v.canonical_name, :query) as sim,
                    case
                      when v.lgd_code = :query then 'EXACT_LGD'
                      when lower(v.canonical_name) = lower(:query)
                        then 'EXACT_NAME'
                      when v.canonical_name ilike :prefix_query
                        then 'PREFIX_NAME'
                      when v.canonical_name ilike :substring_query
                        then 'SUBSTRING_NAME'
                      else 'FUZZY_NAME'
                    end as match_type
                FROM geography_villages v
                JOIN geography_blocks b ON b.id = v.block_id
                JOIN geography_districts d ON d.id = v.district_id
                JOIN geography_states s ON s.id = d.state_id
                WHERE (
                    v.lgd_code = :query
                    OR v.canonical_name % :query
                    OR v.canonical_name ilike :substring_query
                )
                AND v.district_id = :district_id
                AND v.is_active = true
                AND b.is_active = true
                AND d.is_active = true
                AND s.is_active = true
                ORDER BY
                  case
                    when v.lgd_code = :query then 0
                    when lower(v.canonical_name) = lower(:query) then 1
                    when v.canonical_name ilike :prefix_query then 2
                    when v.canonical_name ilike :substring_query then 3
                    else 4
                  end,
                  sim desc,
                  v.canonical_name,
                  v.lgd_code
                LIMIT :limit
            """),
            {
                "query": q,
                "prefix_query": f"{q}%",
                "substring_query": f"%{q}%",
                "limit": limit,
                "district_id": str(district_id),
            },
        ).fetchall()
    else:
        results = db.execute(
            text("""
                SELECT
                    v.id,
                    v.lgd_code,
                    v.canonical_name,
                    v.pin_codes,
                    v.block_id,
                    b.canonical_name as block_name,
                    v.district_id,
                    d.canonical_name as district_name,
                    s.id as state_id,
                    s.canonical_name as state_name,
                    similarity(v.canonical_name, :query) as sim,
                    case
                      when v.lgd_code = :query then 'EXACT_LGD'
                      when lower(v.canonical_name) = lower(:query)
                        then 'EXACT_NAME'
                      when v.canonical_name ilike :prefix_query
                        then 'PREFIX_NAME'
                      when v.canonical_name ilike :substring_query
                        then 'SUBSTRING_NAME'
                      else 'FUZZY_NAME'
                    end as match_type
                FROM geography_villages v
                JOIN geography_blocks b ON b.id = v.block_id
                JOIN geography_districts d ON d.id = v.district_id
                JOIN geography_states s ON s.id = d.state_id
                WHERE (
                    v.lgd_code = :query
                    OR v.canonical_name % :query
                    OR v.canonical_name ilike :substring_query
                )
                AND v.is_active = true
                AND b.is_active = true
                AND d.is_active = true
                AND s.is_active = true
                ORDER BY
                  case
                    when v.lgd_code = :query then 0
                    when lower(v.canonical_name) = lower(:query) then 1
                    when v.canonical_name ilike :prefix_query then 2
                    when v.canonical_name ilike :substring_query then 3
                    else 4
                  end,
                  sim desc,
                  v.canonical_name,
                  v.lgd_code
                LIMIT :limit
            """),
            {
                "query": q,
                "prefix_query": f"{q}%",
                "substring_query": f"%{q}%",
                "limit": limit,
            },
        ).fetchall()

    return [
        VillageSearchResult(
            id=r.id,
            lgd_code=r.lgd_code,
            canonical_name=r.canonical_name,
            block_id=r.block_id,
            block_name=r.block_name,
            district_id=r.district_id,
            district_name=r.district_name,
            state_id=r.state_id,
            state_name=r.state_name,
            pin_codes=r.pin_codes,
            similarity=round(r.sim, 3),
            match_type=r.match_type,
        )
        for r in results
    ]
