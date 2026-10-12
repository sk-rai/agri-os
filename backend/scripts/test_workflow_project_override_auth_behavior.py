#!/usr/bin/env python3
"""Behavior regression for authorized project workflow override mutations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateOverride,
    WorkflowTemplateVersion,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("WORKFLOW PROJECT OVERRIDE AUTHORIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"workflow-override-auth-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = (
        f"workflow-override-auth-foreign-{uuid.uuid4().hex[:8]}"
    )
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()

    admin_user_id = None
    viewer_user_id = None
    manager_user_id = None
    override_id = None

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        template_row = (
            db.query(WorkflowTemplate, WorkflowTemplateVersion)
            .join(
                WorkflowTemplateVersion,
                WorkflowTemplateVersion.template_id
                == WorkflowTemplate.id,
            )
            .filter(
                WorkflowTemplate.tenant_id == "default",
                WorkflowTemplate.is_active == True,
                WorkflowTemplateVersion.status == "PUBLISHED",
                WorkflowTemplateVersion.is_active == True,
            )
            .first()
        )
        check(
            template_row is not None,
            "At least one published default workflow exists",
        )
        template, version = template_row
        template_id = template.id
        version_id = version.id

        db.add_all([
            Tenant(
                id=tenant_id,
                name="Workflow Override Authorization Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Workflow Override Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Workflow Override Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="PLANNED",
                geography_scope={},
                crop_scope=[template.crop_code],
                config={},
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Workflow Override Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="PLANNED",
                geography_scope={},
                crop_scope=[template.crop_code],
                config={},
                created_at=now,
                updated_at=now,
            ),
        ])
        db.commit()

        admin, admin_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=tenant_id,
        )
        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )
        manager, manager_headers = create_test_admin(
            db,
            role="MANAGER",
            tenant_id=tenant_id,
        )
        admin_user_id = admin.id
        viewer_user_id = viewer.id
        manager_user_id = manager.id
    finally:
        db.close()

    client = TestClient(app)
    route = (
        f"/api/v1/workflow-catalog/projects/{project_id}"
        "/workflow-overrides"
    )
    payload = {
        "template_version_id": str(version_id),
        "target_type": "STAGE",
        "target_code": "AUTHORIZATION_REGRESSION_STAGE",
        "operation": "HIDE",
        "override_payload": {},
        "priority": 25,
        "reason": "Verify authenticated project override governance.",
    }

    try:
        missing = client.post(
            route,
            headers={"X-Tenant-ID": tenant_id},
            json=payload,
        )
        check(
            missing.status_code == 401,
            "Workflow override creation rejects missing bearer",
            missing.text,
        )

        viewer_create = client.post(
            route,
            headers=viewer_headers,
            json=payload,
        )
        check(
            viewer_create.status_code == 403,
            "Workflow override creation rejects view-only administrator",
            viewer_create.text,
        )

        manager_create = client.post(
            route,
            headers=manager_headers,
            json=payload,
        )
        check(
            manager_create.status_code == 403,
            "Workflow override creation rejects unassigned manager",
            manager_create.text,
        )

        impersonated_headers = {
            **admin_headers,
            "X-Actor-ID": str(uuid.uuid4()),
        }
        impersonated = client.post(
            route,
            headers=impersonated_headers,
            json=payload,
        )
        check(
            impersonated.status_code == 403,
            "Workflow override creation rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Actor impersonation has stable error code",
        )

        mismatched_headers = {
            **admin_headers,
            "X-Tenant-ID": foreign_tenant_id,
        }
        mismatched = client.post(
            route,
            headers=mismatched_headers,
            json=payload,
        )
        check(
            mismatched.status_code == 403,
            "Workflow override creation rejects tenant mismatch",
            mismatched.text,
        )

        foreign = client.post(
            (
                "/api/v1/workflow-catalog/projects/"
                f"{foreign_project_id}/workflow-overrides"
            ),
            headers=admin_headers,
            json=payload,
        )
        check(
            foreign.status_code in (403, 404),
            "Workflow override creation rejects foreign-tenant project",
            foreign.text,
        )

        created = client.post(
            route,
            headers=admin_headers,
            json=payload,
        )
        check(
            created.status_code == 200,
            "Authorized administrator creates workflow override",
            created.text[:1200],
        )

        verify = SessionLocal()
        try:
            override = (
                verify.query(WorkflowTemplateOverride)
                .filter(
                    WorkflowTemplateOverride.tenant_id == tenant_id,
                    WorkflowTemplateOverride.project_id == project_id,
                    WorkflowTemplateOverride.target_code
                    == payload["target_code"],
                )
                .one()
            )
            override_id = override.id
            check(
                override.is_active is True,
                "Created workflow override is active",
            )
            check(
                override.template_version_id == version_id,
                "Created override uses selected published version",
            )

            create_audit = (
                verify.query(WorkflowTemplateAuditEvent)
                .filter(
                    WorkflowTemplateAuditEvent.tenant_id == tenant_id,
                    WorkflowTemplateAuditEvent.action
                    == "CREATE_PROJECT_WORKFLOW_OVERRIDE",
                    WorkflowTemplateAuditEvent.target_id
                    == str(override_id),
                )
                .one()
            )
            check(
                create_audit.actor_id == admin_user_id,
                "Creation audit records verified administrator",
                str(create_audit.actor_id),
            )
            check(
                create_audit.template_id == template_id,
                "Creation audit records selected template",
            )
            check(
                create_audit.after["is_active"] is True,
                "Creation audit preserves active resulting state",
            )
        finally:
            verify.close()

        delete_route = f"{route}/{override_id}"

        delete_impersonated = client.delete(
            delete_route,
            headers=impersonated_headers,
        )
        check(
            delete_impersonated.status_code == 403,
            "Workflow override archival rejects actor impersonation",
            delete_impersonated.text,
        )

        delete_mismatched = client.delete(
            delete_route,
            headers=mismatched_headers,
        )
        check(
            delete_mismatched.status_code == 403,
            "Workflow override archival rejects tenant mismatch",
            delete_mismatched.text,
        )

        archived = client.delete(
            delete_route,
            headers=admin_headers,
        )
        check(
            archived.status_code == 200,
            "Authorized administrator archives workflow override",
            archived.text[:1200],
        )

        verify = SessionLocal()
        try:
            override = (
                verify.query(WorkflowTemplateOverride)
                .filter(WorkflowTemplateOverride.id == override_id)
                .one()
            )
            check(
                override.is_active is False,
                "Archived override is retained as inactive state",
            )

            archive_audit = (
                verify.query(WorkflowTemplateAuditEvent)
                .filter(
                    WorkflowTemplateAuditEvent.tenant_id == tenant_id,
                    WorkflowTemplateAuditEvent.action
                    == "ARCHIVE_PROJECT_WORKFLOW_OVERRIDE",
                    WorkflowTemplateAuditEvent.target_id
                    == str(override_id),
                )
                .one()
            )
            check(
                archive_audit.actor_id == admin_user_id,
                "Archival audit records verified administrator",
                str(archive_audit.actor_id),
            )
            check(
                archive_audit.before["is_active"] is True,
                "Archival audit preserves active prior state",
            )
            check(
                archive_audit.after["is_active"] is False,
                "Archival audit preserves inactive resulting state",
            )
        finally:
            verify.close()

        repeated = client.delete(
            delete_route,
            headers=admin_headers,
        )
        check(
            repeated.status_code == 404,
            "Archived override cannot be archived twice",
            repeated.text,
        )

    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(WorkflowTemplateAuditEvent).filter(
                WorkflowTemplateAuditEvent.tenant_id.in_(
                    [tenant_id, foreign_tenant_id]
                ),
                WorkflowTemplateAuditEvent.action.in_([
                    "CREATE_PROJECT_WORKFLOW_OVERRIDE",
                    "ARCHIVE_PROJECT_WORKFLOW_OVERRIDE",
                ]),
            ).delete(synchronize_session=False)
            cleanup.query(WorkflowTemplateOverride).filter(
                WorkflowTemplateOverride.tenant_id.in_(
                    [tenant_id, foreign_tenant_id]
                )
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.id.in_([project_id, foreign_project_id])
            ).delete(synchronize_session=False)
            cleanup.commit()

            for user_id in (
                manager_user_id,
                viewer_user_id,
                admin_user_id,
            ):
                if user_id:
                    delete_test_admin(cleanup, user_id)

            cleanup.query(Tenant).filter(
                Tenant.id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()

    print("=" * 72)
    print("Workflow project override authorization validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
