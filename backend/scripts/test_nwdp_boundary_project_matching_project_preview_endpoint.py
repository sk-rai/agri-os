#!/usr/bin/env python3
"""Regression for read-only NWDP boundary project matching project preview endpoint."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import ProjectRole
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def choose_project_id(db) -> str:
    row = db.execute(text("""
        select p.id::text as project_id
        from projects p
        where p.is_active = true
        order by p.created_at desc
        limit 1
    """)).mappings().first()
    if not row:
        raise RuntimeError("No active project available for regression")
    return row["project_id"]


def staging_summary(db):
    return db.execute(text("""
        select
          count(*) as candidates,
          sum(case when is_active then 1 else 0 end) as active_candidates,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidates
        from geography_boundary_crosswalk_candidates
    """)).mappings().one()


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING PROJECT PREVIEW ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None
    project_role_id = None

    try:
        project_id = choose_project_id(db)
        before = staging_summary(db)

        denied = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview?project_id={project_id}",
            headers={"X-Tenant-ID": "default"},
        )
        check(denied.status_code in {401, 403}, "Unauthenticated project preview is denied", denied.text[:500])

        admin, headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id="default",
        )
        project_role_id = uuid.uuid4()
        db.add(
            ProjectRole(
                id=project_role_id,
                project_id=uuid.UUID(project_id),
                user_id=admin.id,
                role="MANAGER",
                territory_scope={},
                is_active=True,
            )
        )
        db.commit()

        missing_project = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview",
            headers=headers,
        )
        check(
            missing_project.status_code == 400,
            "Project-scoped authorization requires project_id",
            missing_project.text[:500],
        )
        check(
            missing_project.json()["detail"]
            == "Project-scoped permission requires project_id.",
            "Missing project rejection reason is stable",
            missing_project.json(),
        )

        wrong_tenant_headers = dict(headers)
        wrong_tenant_headers["X-Tenant-ID"] = "wrong-tenant"
        wrong_tenant = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview?project_id={project_id}&limit=25",
            headers=wrong_tenant_headers,
        )
        check(
            wrong_tenant.status_code == 403,
            "Cross-tenant project preview is denied",
            wrong_tenant.text[:500],
        )

        response = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-project-matching/project-preview?project_id={project_id}&limit=25",
            headers=headers,
        )
        data = response.json()

        check(response.status_code == 200, "Admin viewer can read project preview", response.text[:1000])
        check(data["schema_version"] == "nwdp_boundary_project_matching_project_preview.v1", "Schema version is stable", data)
        check(data["mode"] == "READ_ONLY_PROJECT_MATCHING_PROJECT_PREVIEW", "Endpoint is read-only", data)
        check(data["project"]["project_id"] == project_id, "Endpoint is scoped to requested project", data["project"])

        summary = data["summary"]
        check(summary["project_village_count"] >= 0, "Preview reports project village count", summary)
        check(summary["eligible_candidate_count"] >= 0, "Preview reports eligible candidate count", summary)
        check(summary["manual_review_excluded_from_matching"] is True, "Manual review candidates are excluded", summary)
        check(summary["blocked_excluded_from_matching"] is True, "Blocked candidates are excluded", summary)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["candidate_activation_changed"] is False, "Endpoint does not activate candidates", guardrails)
        check(guardrails["candidate_promotion_changed"] is False, "Endpoint does not promote candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Endpoint writes no runtime tables", guardrails)
        check(guardrails["runtime_spatial_matching_changed"] is False, "Endpoint keeps spatial matching disabled", guardrails)
        check(guardrails["lookup_api_enabled"] is False, "Endpoint keeps lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", guardrails)

        readiness = data["readiness"]
        check(readiness["ready_for_admin_project_matching_preview"] is True, "Endpoint is ready for admin preview", readiness)
        check(readiness["ready_for_project_matching_apply"] is False, "Endpoint is not apply", readiness)
        check(readiness["ready_for_runtime_spatial_matching"] is False, "Endpoint is not runtime matching", readiness)

        after = staging_summary(db)
        check(after["candidates"] == before["candidates"], "Endpoint did not create/delete candidates", dict(after))
        check(after["active_candidates"] == 0, "Endpoint did not activate candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Endpoint did not promote candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY PROJECT MATCHING PROJECT PREVIEW ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if project_role_id is not None:
            db.query(ProjectRole).filter(
                ProjectRole.id == project_role_id
            ).delete(synchronize_session=False)
            db.commit()
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
