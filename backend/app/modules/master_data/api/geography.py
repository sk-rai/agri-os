"""Geography cascade API endpoints.

GET /api/v1/master-data/geography/states
GET /api/v1/master-data/geography/districts?state_id=
GET /api/v1/master-data/geography/blocks?district_id=
GET /api/v1/master-data/geography/villages?block_id=  (block-scoped)
GET /api/v1/master-data/geography/villages?district_id=  (district-wide, for offline cache)
GET /api/v1/master-data/geography/villages/search?q=&district_id=  (fuzzy, optionally scoped)
"""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.admin_auth import AdminPermission, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.models import (
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
    GeographyPostalReference,
    GeographyVillagePinLink,
)

router = APIRouter(prefix="/geography", tags=["geography"])


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
    block_name: str
    district_name: str
    pin_codes: Optional[list[str]] = None
    similarity: float

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
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
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
          f.source_village_name
        from geography_boundary_import_batches b
        join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
        join geography_boundary_source_features f on f.id = c.source_feature_id
        where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
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
        "claim_boundary": "Read-only admin/project matching candidate read model. It returns inactive DIRECT_VLCODE_MATCH AUTO_CANDIDATE rows only. It excludes manual review and blocked candidates and does not activate candidates, promote candidates, write runtime tables, enable lookup behavior, or change Android behavior.",
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

    params = {"project_id": str(project_id), "limit": limit}

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
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
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
              f.source_village_name
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            join geography_boundary_source_features f on f.id = c.source_feature_id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
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
        },
        "items": [dict(row) for row in items],
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
        "claim_boundary": "Read-only project-scoped NWDP boundary coverage preview. It inspects inactive direct-code candidates for project villages only. It does not activate candidates, promote candidates, write runtime tables, enable lookup behavior, or change Android behavior.",
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
                    b.canonical_name as block_name,
                    d.canonical_name as district_name,
                    similarity(v.canonical_name, :query) as sim
                FROM geography_villages v
                JOIN geography_blocks b ON b.id = v.block_id
                JOIN geography_districts d ON d.id = v.district_id
                WHERE v.canonical_name % :query
                AND v.district_id = :district_id
                AND v.is_active = true
                ORDER BY sim DESC
                LIMIT :limit
            """),
            {"query": q, "limit": limit, "district_id": str(district_id)},
        ).fetchall()
    else:
        results = db.execute(
            text("""
                SELECT
                    v.id,
                    v.lgd_code,
                    v.canonical_name,
                    v.pin_codes,
                    b.canonical_name as block_name,
                    d.canonical_name as district_name,
                    similarity(v.canonical_name, :query) as sim
                FROM geography_villages v
                JOIN geography_blocks b ON b.id = v.block_id
                JOIN geography_districts d ON d.id = v.district_id
                WHERE v.canonical_name % :query
                AND v.is_active = true
                ORDER BY sim DESC
                LIMIT :limit
            """),
            {"query": q, "limit": limit},
        ).fetchall()

    return [
        VillageSearchResult(
            id=r.id,
            lgd_code=r.lgd_code,
            canonical_name=r.canonical_name,
            block_name=r.block_name,
            district_name=r.district_name,
            pin_codes=r.pin_codes,
            similarity=round(r.sim, 3),
        )
        for r in results
    ]
