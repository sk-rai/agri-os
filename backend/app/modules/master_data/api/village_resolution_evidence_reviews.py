"""Reusable, snapshot-linked two-session review of canonical village evidence."""
import json
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, require_admin_permission
from app.core.database import get_db

router = APIRouter(prefix="/geography/village-resolution/reviews", tags=["geography"])

PRIMARY_DECISIONS = {"ACCEPT_FOR_SECOND_REVIEW", "REJECT", "HOLD"}
SECOND_DECISIONS = {"APPROVE", "REJECT", "HOLD"}


class PrimaryEvidenceReview(BaseModel):
    evidence_item_id: UUID
    decision: str
    notes: str = Field(min_length=8, max_length=1000)


class SecondEvidenceReview(BaseModel):
    decision: str
    notes: str = Field(min_length=8, max_length=1000)
    confirmation_phrase: str


def _guardrails() -> dict:
    return {
        "canonical_geography_changed": False,
        "pin_links_changed": False,
        "runtime_changed": False,
        "android_changed": False,
        "automatic_application_authorized": False,
    }


def _active_item(db: Session, item_id: UUID):
    return db.execute(text("""
      select item.id::text evidence_item_id, item.snapshot_id::text snapshot_id,
             item.village_id::text village_id,
             item.source_feature_id::text source_feature_id,
             item.disposition, item.best_match_rank, item.best_match_basis,
             item.source_collision, item.review_eligibility,
             item.prior_candidate_evidence,
             village.lgd_code::text village_lgd_code,
             village.canonical_name village_name
      from geography_village_resolution_evidence_items item
      join geography_village_resolution_evidence_snapshots snapshot
        on snapshot.id=item.snapshot_id and snapshot.is_active=true
      join geography_villages village on village.id=item.village_id
      where item.id=:item
    """), {"item": str(item_id)}).mappings().first()


@router.get("")
def list_reviews(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _principal=Depends(require_admin_permission(AdminPermission.VIEW)),
):
    normalized = status.upper() if status else None
    allowed = {"PENDING_SECOND_REVIEW", "APPROVED", "REJECTED", "HELD"}
    if normalized and normalized not in allowed:
        raise HTTPException(400, {"code": "INVALID_EVIDENCE_REVIEW_STATUS"})
    rows = db.execute(text("""
      select review.id::text review_id, review.snapshot_id::text snapshot_id,
             review.evidence_item_id::text evidence_item_id,
             review.village_id::text village_id,
             village.lgd_code::text village_lgd_code,
             village.canonical_name village_name,
             review.source_feature_id::text source_feature_id,
             review.status, review.primary_decision,
             review.primary_reviewer_id::text primary_reviewer_id,
             review.primary_notes, review.second_decision,
             review.second_reviewer_id::text second_reviewer_id,
             review.second_notes, review.created_at, review.updated_at,
             item.disposition, item.best_match_rank, item.best_match_basis,
             item.source_collision, item.review_eligibility,
             count(*) over()::bigint filtered_total,
             coalesce((
               select jsonb_agg(jsonb_build_object(
                 'event_id', event.id::text, 'action', event.action,
                 'actor_id', event.actor_id::text, 'notes', event.notes,
                 'evidence', event.evidence, 'created_at', event.created_at
               ) order by event.created_at)
               from geography_village_resolution_evidence_review_events event
               where event.review_id=review.id
             ), '[]'::jsonb) events
      from geography_village_resolution_evidence_reviews review
      join geography_village_resolution_evidence_snapshots snapshot
        on snapshot.id=review.snapshot_id and snapshot.is_active=true
      join geography_village_resolution_evidence_items item
        on item.id=review.evidence_item_id
      join geography_villages village on village.id=review.village_id
      where (:status is null or review.status=:status)
      order by review.updated_at desc, review.id
      limit :limit offset :offset
    """), {"status": normalized, "limit": limit, "offset": offset}).mappings().all()
    total = int(rows[0]["filtered_total"]) if rows else 0
    return {
        "schema_version": "village_resolution_evidence_review_queue.v1",
        "mode": "REVIEW_ONLY_NO_APPLY",
        "pagination": {
            "limit": limit, "offset": offset, "filtered_total": total,
            "has_more": offset + len(rows) < total,
        },
        "items": [dict(row) for row in rows],
        "guardrails": _guardrails(),
    }


@router.post("")
def create_primary_review(
    body: PrimaryEvidenceReview,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.EDIT)),
):
    decision = body.decision.upper()
    if decision not in PRIMARY_DECISIONS:
        raise HTTPException(400, {
            "code": "INVALID_PRIMARY_EVIDENCE_DECISION",
            "allowed": sorted(PRIMARY_DECISIONS),
        })
    item = _active_item(db, body.evidence_item_id)
    if not item:
        raise HTTPException(404, {"code": "ACTIVE_EVIDENCE_ITEM_NOT_FOUND"})
    if item["source_collision"] or item["review_eligibility"] != "TWO_SESSION_REVIEW_ELIGIBLE":
        raise HTTPException(409, {"code": "EVIDENCE_ITEM_NOT_TWO_SESSION_ELIGIBLE"})
    if not item["source_feature_id"]:
        raise HTTPException(409, {"code": "EVIDENCE_ITEM_SOURCE_FEATURE_REQUIRED"})
    existing = db.execute(text("""
      select id::text from geography_village_resolution_evidence_reviews
      where snapshot_id=:snapshot and evidence_item_id=:item
    """), {"snapshot": item["snapshot_id"], "item": item["evidence_item_id"]}).scalar()
    if existing:
        raise HTTPException(409, {
            "code": "EVIDENCE_ITEM_ALREADY_REVIEWED", "review_id": existing,
        })
    status = {
        "ACCEPT_FOR_SECOND_REVIEW": "PENDING_SECOND_REVIEW",
        "REJECT": "REJECTED", "HOLD": "HELD",
    }[decision]
    action = {
        "ACCEPT_FOR_SECOND_REVIEW": "PRIMARY_ACCEPTED",
        "REJECT": "PRIMARY_REJECTED", "HOLD": "PRIMARY_HELD",
    }[decision]
    review_id, event_id = uuid4(), uuid4()
    evidence = {
        "snapshot_id": item["snapshot_id"],
        "evidence_item_id": item["evidence_item_id"],
        "village_id": item["village_id"],
        "source_feature_id": item["source_feature_id"],
        "disposition": item["disposition"],
        "best_match_rank": item["best_match_rank"],
        "best_match_basis": item["best_match_basis"],
        **_guardrails(),
    }
    db.execute(text("""
      insert into geography_village_resolution_evidence_reviews(
        id,snapshot_id,evidence_item_id,village_id,source_feature_id,status,
        primary_decision,primary_reviewer_id,primary_notes
      ) values(:id,:snapshot,:item,:village,:source,:status,:decision,:actor,:notes)
    """), {
        "id": str(review_id), "snapshot": item["snapshot_id"],
        "item": item["evidence_item_id"], "village": item["village_id"],
        "source": item["source_feature_id"], "status": status,
        "decision": decision, "actor": str(principal.user_id), "notes": body.notes,
    })
    db.execute(text("""
      insert into geography_village_resolution_evidence_review_events(
        id,review_id,action,actor_id,notes,evidence
      ) values(:id,:review,:action,:actor,:notes,cast(:evidence as jsonb))
    """), {
        "id": str(event_id), "review": str(review_id), "action": action,
        "actor": str(principal.user_id), "notes": body.notes,
        "evidence": json.dumps(evidence),
    })
    db.commit()
    return {
        "schema_version": "village_resolution_evidence_primary_review.v1",
        "review_id": str(review_id), "status": status, "decision": decision,
        "second_review_required": status == "PENDING_SECOND_REVIEW",
        "guardrails": _guardrails(),
    }


@router.post("/{review_id}/second-review")
def complete_second_review(
    review_id: UUID,
    body: SecondEvidenceReview,
    db: Session = Depends(get_db),
    principal=Depends(require_admin_permission(AdminPermission.PUBLISH)),
):
    if principal.role != "ENTERPRISE_ADMIN":
        raise HTTPException(403, {"code": "ENTERPRISE_ADMIN_SECOND_REVIEW_REQUIRED"})
    decision = body.decision.upper()
    if decision not in SECOND_DECISIONS:
        raise HTTPException(400, {"code": "INVALID_SECOND_EVIDENCE_DECISION"})
    if body.confirmation_phrase != "COMPLETE SECOND VILLAGE EVIDENCE REVIEW":
        raise HTTPException(400, {"code": "SECOND_EVIDENCE_REVIEW_CONFIRMATION_REQUIRED"})
    review = db.execute(text("""
      select id::text review_id, primary_reviewer_id::text primary_reviewer_id
      from geography_village_resolution_evidence_reviews
      where id=:id and status='PENDING_SECOND_REVIEW' for update
    """), {"id": str(review_id)}).mappings().first()
    if not review:
        raise HTTPException(409, {"code": "PENDING_SECOND_EVIDENCE_REVIEW_NOT_FOUND"})
    if review["primary_reviewer_id"] == str(principal.user_id):
        raise HTTPException(409, {"code": "SECOND_REVIEWER_MUST_DIFFER_FROM_PRIMARY"})
    status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "HOLD": "HELD"}[decision]
    action = {"APPROVE": "SECOND_APPROVED", "REJECT": "SECOND_REJECTED", "HOLD": "SECOND_HELD"}[decision]
    db.execute(text("""
      update geography_village_resolution_evidence_reviews
      set status=:status,second_decision=:decision,second_reviewer_id=:actor,
          second_notes=:notes,updated_at=now() where id=:id
    """), {
        "status": status, "decision": decision, "actor": str(principal.user_id),
        "notes": body.notes, "id": str(review_id),
    })
    db.execute(text("""
      insert into geography_village_resolution_evidence_review_events(
        id,review_id,action,actor_id,notes,evidence
      ) values(:id,:review,:action,:actor,:notes,cast(:evidence as jsonb))
    """), {
        "id": str(uuid4()), "review": str(review_id), "action": action,
        "actor": str(principal.user_id), "notes": body.notes,
        "evidence": json.dumps(_guardrails()),
    })
    db.commit()
    return {
        "schema_version": "village_resolution_evidence_second_review.v1",
        "review_id": str(review_id), "status": status, "decision": decision,
        "application_authorized": False, "guardrails": _guardrails(),
    }
