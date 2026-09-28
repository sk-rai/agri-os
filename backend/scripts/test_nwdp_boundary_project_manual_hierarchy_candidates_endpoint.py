#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

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


def check(condition: bool, label: str, detail=None):
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


def counts(db) -> dict:
    row = db.execute(text("""
        select
          (
            select count(*)
            from geography_boundary_project_matches
          ) as project_matches,
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


def create_project(db, project_id: str, candidate: dict) -> None:
    scope = {
        "source":
            "manual_hierarchy_candidates_endpoint_regression",
        "state_or_ut": candidate["canonical_state_name"],
        "village_ids": [candidate["canonical_village_id"]],
        "village_lgd_codes": [
            candidate["canonical_village_code"]
        ],
    }
    db.execute(text("""
        insert into projects (
          id,
          tenant_id,
          name,
          description,
          start_date,
          end_date,
          status,
          geography_scope,
          crop_scope,
          config,
          created_at,
          updated_at,
          version,
          is_active
        )
        values (
          :project_id,
          :tenant_id,
          'NWDP Manual Hierarchy Read Regression',
          'Temporary project-scoped read-model fixture.',
          :start_date,
          :end_date,
          'ACTIVE',
          cast(:scope as jsonb),
          '[]'::jsonb,
          '{}'::jsonb,
          now(),
          now(),
          'v1.0',
          true
        )
    """), {
        "project_id": project_id,
        "tenant_id": TENANT_ID,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "scope": json.dumps(scope),
    })
    db.commit()


def cleanup(db, project_id: str) -> None:
    db.rollback()
    db.execute(
        text(
            "delete from projects "
            "where id = :project_id"
        ),
        {"project_id": project_id},
    )
    db.commit()


def main() -> int:
    print("=" * 72)
    print(
        "NWDP PROJECT MANUAL HIERARCHY CANDIDATES "
        "ENDPOINT REGRESSION"
    )
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_id = str(uuid.uuid4())

    try:
        candidates = (
            _nwdp_project_manual_hierarchy_candidate_rows(db)
        )
        check(
            len(candidates) == 3,
            "Database read model exposes three reviewed candidates",
            candidates,
        )
        selected = candidates[0]
        excluded_ids = {
            row["candidate_id"]
            for row in candidates[1:]
        }

        create_project(db, project_id, selected)
        baseline = counts(db)

        url = (
            "/api/v1/master-data/geography/"
            "nwdp-boundary-project-matching/projects/"
            f"{project_id}/manual-hierarchy-candidates"
        )

        denied = client.get(
            url,
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(
            denied.status_code in {401, 403},
            "Unauthenticated read is denied",
            denied.text[:500],
        )

        admin, headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=TENANT_ID,
        )

        wrong_tenant_headers = dict(headers)
        wrong_tenant_headers["X-Tenant-ID"] = "wrong-tenant"
        wrong_tenant = client.get(
            url,
            headers=wrong_tenant_headers,
        )
        check(
            wrong_tenant.status_code == 403,
            "Cross-tenant read is denied",
            wrong_tenant.text[:500],
        )

        response = client.get(url, headers=headers)
        data = response.json()
        check(
            response.status_code == 200,
            "Authorized project-scoped read succeeds",
            data,
        )
        check(
            data["schema_version"]
            == "nwdp_boundary_project_manual_hierarchy_candidates.v1",
            "Schema version is stable",
            data,
        )
        check(
            data["mode"]
            == "READ_ONLY_PROJECT_SCOPED_MANUAL_HIERARCHY_CANDIDATES",
            "Endpoint mode is read-only and project scoped",
            data,
        )
        check(
            data["project_id"] == project_id
            and data["tenant_id"] == TENANT_ID,
            "Response identifies exact tenant and project",
            data,
        )
        check(
            data["count"] == 1,
            "Only the project village candidate is returned",
            data,
        )
        check(
            data["items"][0]["candidate_id"]
            == selected["candidate_id"],
            "Returned candidate matches project geography",
            data["items"],
        )
        check(
            not excluded_ids.intersection({
                row["candidate_id"]
                for row in data["items"]
            }),
            "Candidates outside project geography are excluded",
            data["items"],
        )
        check(
            data["items"][0]["candidate_bucket"]
            == "BLOCKED_SOURCE_CAVEAT"
            and data["items"][0]["review_status"] == "BLOCKED"
            and data["items"][0]["candidate_is_active"] is False,
            "Global candidate remains blocked and inactive",
            data["items"][0],
        )
        check(
            data["guardrails"]["db_writes_attempted"] is False
            and data["guardrails"][
                "project_assignments_written"
            ] is False
            and data["readiness"][
                "ready_for_project_manual_apply"
            ] is True
            and data["readiness"][
                "ready_for_global_reuse"
            ] is False
            and data["readiness"][
                "ready_for_runtime_activation"
            ] is False,
            "Endpoint advertises guarded project-only apply",
            data,
        )

        after = counts(db)
        check(
            after == baseline,
            "Endpoint leaves candidate, assignment, and runtime counts unchanged",
            {
                "before": baseline,
                "after": after,
            },
        )

        print("=" * 72)
        print(
            "NWDP PROJECT MANUAL HIERARCHY CANDIDATES "
            "ENDPOINT REGRESSION PASSED"
        )
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        cleanup(db, project_id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
