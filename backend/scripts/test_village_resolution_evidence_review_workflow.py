#!/usr/bin/env python3
"""Behavior contract for reusable two-session local-evidence review."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def counts(db):
    return dict(db.execute(text("""
      select
        (select count(*) from geography_villages where is_active) villages,
        (select count(*) from geography_village_pin_links where is_active) pins,
        (select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime,
        (select count(*) from geography_village_resolution_evidence_reviews) reviews,
        (select count(*) from geography_village_resolution_evidence_review_events) events
    """)).mappings().one())


def main():
    db = SessionLocal()
    first = second = None
    review_id = None
    try:
        before = counts(db)
        first, first_headers = create_test_admin(
            db, role="ENTERPRISE_ADMIN", tenant_id="default"
        )
        second, second_headers = create_test_admin(
            db, role="ENTERPRISE_ADMIN", tenant_id="default"
        )
        first_id, second_id = str(first.id), str(second.id)
        item = db.execute(text("""
          select item.id::text evidence_item_id
          from geography_village_resolution_evidence_items item
          join geography_village_resolution_evidence_snapshots snapshot
            on snapshot.id=item.snapshot_id and snapshot.is_active=true
          where item.review_eligibility='TWO_SESSION_REVIEW_ELIGIBLE'
            and item.source_collision=false
            and item.source_feature_id is not null
            and not exists (
              select 1 from geography_village_resolution_evidence_reviews review
              where review.snapshot_id=item.snapshot_id
                and review.evidence_item_id=item.id
            )
          order by item.best_match_rank,item.village_id limit 1
        """)).mappings().one()
        client = TestClient(app)
        primary = client.post(
            "/api/v1/master-data/geography/village-resolution/reviews",
            headers=first_headers,
            json={
                "evidence_item_id": item["evidence_item_id"],
                "decision": "ACCEPT_FOR_SECOND_REVIEW",
                "notes": "Primary reviewer accepts exact local evidence.",
            },
        )
        assert primary.status_code == 200, primary.text
        primary_body = primary.json()
        assert primary_body["status"] == "PENDING_SECOND_REVIEW"
        review_id = primary_body["review_id"]
        pending_queue = client.get(
            "/api/v1/master-data/geography/village-resolution/reviews",
            headers=first_headers,
        )
        assert pending_queue.status_code == 200, pending_queue.text
        pending_progress = pending_queue.json()["progress"]
        assert pending_progress["eligible_total"] == 125
        assert pending_progress["reviewed_total"] == 1
        assert pending_progress["pending_second_review"] == 1
        assert pending_progress["unreviewed"] == 124
        assert pending_progress["application_authorized"] is False
        self_review = client.post(
            f"/api/v1/master-data/geography/village-resolution/reviews/{review_id}/second-review",
            headers=first_headers,
            json={
                "decision": "APPROVE",
                "notes": "Self review must be rejected safely.",
                "confirmation_phrase": "COMPLETE SECOND VILLAGE EVIDENCE REVIEW",
            },
        )
        assert self_review.status_code == 409, self_review.text
        approved = client.post(
            f"/api/v1/master-data/geography/village-resolution/reviews/{review_id}/second-review",
            headers=second_headers,
            json={
                "decision": "APPROVE",
                "notes": "Independent reviewer confirms the evidence.",
                "confirmation_phrase": "COMPLETE SECOND VILLAGE EVIDENCE REVIEW",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["application_authorized"] is False
        queue = client.get(
            "/api/v1/master-data/geography/village-resolution/reviews?status=APPROVED",
            headers=second_headers,
        )
        assert queue.status_code == 200, queue.text
        row = next(x for x in queue.json()["items"] if x["review_id"] == review_id)
        assert [event["action"] for event in row["events"]] == [
            "PRIMARY_ACCEPTED", "SECOND_APPROVED"
        ]
        assert row["primary_reviewer_id"] == first_id
        assert row["second_reviewer_id"] == second_id
        approved_progress = queue.json()["progress"]
        assert approved_progress["eligible_total"] == 125
        assert approved_progress["approved"] == 1
        assert approved_progress["pending_second_review"] == 0
        assert approved_progress["completed_total"] == 1
        db.execute(text(
            "delete from geography_village_resolution_evidence_reviews where id=:id"
        ), {"id": review_id})
        db.commit()
        review_id = None
        delete_test_admin(db, first_id)
        delete_test_admin(db, second_id)
        first = second = None
        after = counts(db)
        assert after == before, (before, after)
        print(json.dumps({
            "schema_version": "village_resolution_evidence_review_workflow_test.v1",
            "primary_status": primary_body["status"],
            "second_status": approved.json()["status"],
            "self_review_rejected": True,
            "audit_actions": ["PRIMARY_ACCEPTED", "SECOND_APPROVED"],
            "database_restored": True,
            "canonical_geography_changed": False,
            "pin_links_changed": False,
            "runtime_changed": False,
            "android_changed": False,
            "application_authorized": False,
            "progress_transition": {
                "eligible_total": 125,
                "unreviewed": [124, 124],
                "pending_second_review": [1, 0],
                "approved": [0, 1],
            },
        }, indent=2))
        print("VILLAGE RESOLUTION EVIDENCE REVIEW WORKFLOW PASSED")
        return 0
    finally:
        if review_id:
            db.execute(text(
                "delete from geography_village_resolution_evidence_reviews where id=:id"
            ), {"id": review_id})
            db.commit()
        if first:
            delete_test_admin(db, str(first.id))
        if second:
            delete_test_admin(db, str(second.id))
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
