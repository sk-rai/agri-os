#!/usr/bin/env python3
"""Regression for project-scoped NWDP manual-hierarchy assignment."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.api.geography import (
    _nwdp_project_manual_hierarchy_candidate_rows,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

TENANT_ID = "default"
ROLLBACK_TOKEN = "nwdp-manual-hierarchy-assignment-regression"
MATCH_SOURCE = "ADMIN_PROJECT_MANUAL_HIERARCHY_OVERRIDE"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(
            "   ",
            json.dumps(
                detail,
                indent=2,
                sort_keys=True,
                default=str,
            )[:2000],
        )
    if not condition:
        raise AssertionError(label)


def counts(db):
    row = db.execute(text("""
        select
          (
            select count(*)
            from geography_boundary_project_matches
          ) as matches,
          (
            select count(*)
            from geography_boundary_project_matches
            where is_active = true
          ) as active_matches,
          (
            select count(*)
            from geography_boundary_crosswalk_candidates
            where is_active = true
          ) as active_candidates,
          (
            select count(*)
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidates,
          (
            select count(*)
            from geography_boundary_runtime_features
          ) as runtime_features,
          (
            select count(*)
            from geography_boundary_runtime_crosswalks
          ) as runtime_crosswalks
    """)).mappings().one()
    return {
        key: int(value or 0)
        for key, value in dict(row).items()
    }


def candidate_state(db, candidate_id):
    return dict(db.execute(text("""
        select
          c.candidate_bucket,
          c.review_status,
          c.promotion_status,
          c.is_active,
          c.proposed_village_id::text,
          sf.geometry_validation_status
        from geography_boundary_crosswalk_candidates c
        join geography_boundary_source_features sf
          on sf.id = c.source_feature_id
        where c.id = :candidate_id
    """), {"candidate_id": candidate_id}).mappings().one())


def create_project(db, project_id, candidate):
    scope = {
        "source": "manual_hierarchy_assignment_regression",
        "state_or_ut": candidate["canonical_state_name"],
        "village_ids": [candidate["canonical_village_id"]],
        "village_lgd_codes": [
            candidate["canonical_village_code"],
        ],
    }
    db.execute(text("""
        insert into projects (
          id, tenant_id, name, description,
          start_date, end_date, status,
          geography_scope, crop_scope, config,
          created_at, updated_at, version, is_active
        )
        values (
          :project_id, :tenant_id,
          'NWDP Manual Hierarchy Assignment Regression',
          'Temporary project-only manual hierarchy fixture.',
          :start_date, :end_date, 'ACTIVE',
          cast(:scope as jsonb), '[]'::jsonb, '{}'::jsonb,
          now(), now(), 'v1.0', true
        )
    """), {
        "project_id": project_id,
        "tenant_id": TENANT_ID,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "scope": json.dumps(scope),
    })
    db.commit()


def cleanup(db, project_id):
    db.rollback()
    db.execute(text("""
        delete from geography_boundary_project_matches
        where project_id = :project_id
           or rollback_token = :rollback_token
    """), {
        "project_id": project_id,
        "rollback_token": ROLLBACK_TOKEN,
    })
    db.execute(
        text("delete from projects where id = :project_id"),
        {"project_id": project_id},
    )
    db.commit()


def main():
    print("=" * 72)
    print("NWDP PROJECT MANUAL HIERARCHY ASSIGNMENT REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    client = TestClient(app)
    project_id = str(uuid.uuid4())
    viewer = admin = None

    try:
        candidates = _nwdp_project_manual_hierarchy_candidate_rows(db)
        check(
            len(candidates) == 3,
            "Reviewed manual hierarchy candidate set is exact",
            candidates,
        )
        selected = candidates[0]
        other = candidates[1]

        before_candidate = candidate_state(
            db,
            selected["candidate_id"],
        )
        baseline = counts(db)
        create_project(db, project_id, selected)

        url = (
            "/api/v1/master-data/geography/"
            "nwdp-boundary-project-matching/projects/"
            f"{project_id}/villages/"
            f"{selected['canonical_village_id']}"
        )
        body = {
            "candidate_id": selected["candidate_id"],
            "rollback_token": ROLLBACK_TOKEN,
            "reason":
                "Project admin selected reviewed hierarchy candidate.",
            "supersede_existing": False,
        }

        denied = client.put(
            url,
            json=body,
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(
            denied.status_code in {401, 403},
            "Unauthenticated manual assignment is denied",
            denied.text[:500],
        )

        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=TENANT_ID,
        )
        denied = client.put(
            url,
            json=body,
            headers=viewer_headers,
        )
        check(
            denied.status_code == 403,
            "VIEW-only manual assignment is denied",
            denied.text[:500],
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        wrong_tenant_headers = dict(headers)
        wrong_tenant_headers["X-Tenant-ID"] = "wrong-tenant"
        denied = client.put(
            url,
            json=body,
            headers=wrong_tenant_headers,
        )
        check(
            denied.status_code == 403,
            "Cross-tenant manual assignment is denied",
            denied.text[:500],
        )

        wrong_candidate_body = dict(body)
        wrong_candidate_body["candidate_id"] = other["candidate_id"]
        denied = client.put(
            url,
            json=wrong_candidate_body,
            headers=headers,
        )
        check(
            denied.status_code == 409,
            "Candidate targeting another village is rejected",
            denied.text[:500],
        )
        check(
            denied.json()["detail"]
            == "BOUNDARY_CANDIDATE_NOT_ASSIGNABLE",
            "Wrong-target rejection reason is stable",
            denied.json(),
        )
        check(
            counts(db) == baseline,
            "Rejected cases write no assignment",
        )

        response = client.put(url, json=body, headers=headers)
        data = response.json()
        check(
            response.status_code == 200,
            "Project manual hierarchy assignment succeeds",
            data,
        )
        check(
            data["action"] == "APPLIED",
            "Manual assignment action is APPLIED",
            data,
        )
        assignment = data["assignment"]
        check(
            assignment["tenant_id"] == TENANT_ID
            and assignment["project_id"] == project_id
            and assignment["village_id"]
            == selected["canonical_village_id"]
            and assignment["boundary_candidate_id"]
            == selected["candidate_id"],
            "Assignment scope and identities are exact",
            assignment,
        )
        check(
            assignment["match_source"] == MATCH_SOURCE,
            "Manual hierarchy audit source is explicit",
            assignment,
        )
        check(
            assignment["metadata"]["assignment_scope"]
            == "PROJECT_ONLY"
            and assignment["metadata"][
                "global_candidate_status_changed"
            ] is False
            and assignment["metadata"][
                "canonical_geography_changed"
            ] is False
            and assignment["metadata"][
                "global_equivalence_created"
            ] is False,
            "Assignment metadata preserves project-only boundary",
            assignment["metadata"],
        )

        applied = counts(db)
        check(
            applied["matches"] == baseline["matches"] + 1
            and applied["active_matches"]
            == baseline["active_matches"] + 1,
            "Exactly one active project match is created",
            {"before": baseline, "after": applied},
        )

        after_candidate = candidate_state(
            db,
            selected["candidate_id"],
        )
        check(
            after_candidate == before_candidate,
            "Global candidate remains unchanged",
            {
                "before": before_candidate,
                "after": after_candidate,
            },
        )
        check(
            after_candidate["candidate_bucket"]
            == "BLOCKED_SOURCE_CAVEAT"
            and after_candidate["review_status"] == "BLOCKED"
            and after_candidate["promotion_status"]
            == "NOT_PROMOTED"
            and after_candidate["is_active"] is False
            and after_candidate["proposed_village_id"] is None,
            "Global candidate remains blocked and inactive",
            after_candidate,
        )

        for key in [
            "active_candidates",
            "promoted_candidates",
            "runtime_features",
            "runtime_crosswalks",
        ]:
            check(
                applied[key] == baseline[key],
                f"Global/runtime count unchanged: {key}",
            )

        repeated = client.put(url, json=body, headers=headers)
        check(
            repeated.status_code == 200
            and repeated.json()["action"]
            == "IDEMPOTENT_NO_OP",
            "Repeated manual assignment is idempotent",
            repeated.json(),
        )
        check(
            counts(db) == applied,
            "Idempotent repeat changes no counts",
        )

        rollback = client.delete(
            url,
            params={"rollback_token": ROLLBACK_TOKEN},
            headers=headers,
        )
        rollback_data = rollback.json()
        check(
            rollback.status_code == 200
            and rollback_data["action"] == "ROLLED_BACK",
            "Manual assignment rollback succeeds",
            rollback_data,
        )
        check(
            rollback_data["assignment"]["is_active"] is False,
            "Rolled-back assignment is inactive",
            rollback_data,
        )

        final = counts(db)
        check(
            final["matches"] == baseline["matches"] + 1,
            "Rolled-back assignment history is retained",
            final,
        )
        check(
            final["active_matches"]
            == baseline["active_matches"],
            "No manual fixture assignment remains active",
            final,
        )
        check(
            candidate_state(db, selected["candidate_id"])
            == before_candidate,
            "Rollback leaves global candidate unchanged",
        )

        repeated_rollback = client.delete(
            url,
            params={"rollback_token": ROLLBACK_TOKEN},
            headers=headers,
        )
        check(
            repeated_rollback.status_code == 200
            and repeated_rollback.json()["action"]
            == "IDEMPOTENT_ROLLBACK_NO_OP",
            "Repeated rollback is idempotent",
            repeated_rollback.json(),
        )

        print("=" * 72)
        print(
            "NWDP PROJECT MANUAL HIERARCHY "
            "ASSIGNMENT REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        if viewer is not None:
            delete_test_admin(db, viewer.id)
        if admin is not None:
            delete_test_admin(db, admin.id)
        cleanup(db, project_id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
