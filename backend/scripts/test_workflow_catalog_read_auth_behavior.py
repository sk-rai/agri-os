#!/usr/bin/env python3
"""Behavior regression for workflow catalog read authorization."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Project,
    Tenant,
)
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateVersion,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("WORKFLOW CATALOG READ AUTHORIZATION REGRESSION")
    print("=" * 72)

    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"workflow-catalog-read-{suffix}"
    foreign_tenant_id = f"workflow-catalog-read-foreign-{suffix}"
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    draft_version_id = uuid.uuid4()

    user_ids = []
    template_id = None
    published_version_id = None
    editor_user_id = None

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        pair = (
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
            pair is not None,
            "At least one published default workflow exists",
        )
        template, published = pair
        template_id = template.id
        published_version_id = published.id

        db.add_all([
            Tenant(
                id=tenant_id,
                name="Workflow Catalog Read Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Workflow Catalog Read Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Workflow Catalog Runtime Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                crop_scope=[template.crop_code],
                geography_scope={},
                config={},
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Workflow Catalog Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="ACTIVE",
                crop_scope=[template.crop_code],
                geography_scope={},
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
        editor, editor_headers = create_test_admin(
            db,
            role="ADMIN_EDITOR",
            tenant_id=tenant_id,
        )
        farmer_user, farmer_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=tenant_id,
        )
        unrelated_user, unrelated_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=tenant_id,
        )
        user_ids.extend([
            admin.id,
            viewer.id,
            editor.id,
            farmer_user.id,
            unrelated_user.id,
        ])
        editor_user_id = editor.id

        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=farmer_user.id,
            mobile_number=f"97{farmer_id.int % 100000000:08d}",
            village_name_manual="Workflow Catalog Test Village",
            primary_crop_code=template.crop_code,
            display_name="Workflow Catalog Farmer",
            status="ACTIVE",
            enrollment_method="SELF",
            created_at=now,
            updated_at=now,
        ))
        db.flush()
        db.add(FarmerProjectEnrollment(
            id=enrollment_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            enrollment_method="SELF",
            enrollment_source="WORKFLOW_CATALOG_AUTH_REGRESSION",
            enrolled_by=farmer_user.id,
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[],
            metadata_={},
            created_at=now,
            updated_at=now,
        ))
        db.add(WorkflowTemplateVersion(
            id=draft_version_id,
            template_id=template.id,
            version_number=f"auth-read-{suffix}",
            status="DRAFT",
            total_duration_days=published.total_duration_days,
            schema_version=published.schema_version or "1.0.0",
            metadata_={
                "source": "workflow_catalog_read_auth_regression",
            },
            created_at=now,
            updated_at=now,
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    catalog_route = (
        "/api/v1/workflow-catalog/enabled-crop-workflows"
    )
    project_catalog_route = (
        f"{catalog_route}?project_id={project_id}"
    )
    preview_route = (
        "/api/v1/workflow-catalog/workflow-preview/"
        f"{published_version_id}?project_id={project_id}"
    )
    draft_preview_route = (
        "/api/v1/workflow-catalog/draft-preview/"
        f"{draft_version_id}"
    )
    validation_route = (
        "/api/v1/workflow-catalog/drafts/"
        f"{draft_version_id}/validation"
    )
    impact_route = (
        "/api/v1/workflow-catalog/drafts/"
        f"{draft_version_id}/publish-impact"
    )
    legacy_route = (
        "/api/v1/workflow-catalog/legacy-cycle-pins"
        f"?project_id={project_id}&limit=10"
    )
    versions_route = (
        "/api/v1/workflow-catalog/templates/"
        f"{template_id}/versions"
    )
    audit_route = (
        "/api/v1/workflow-catalog/templates/"
        f"{template_id}/audit?version_id={draft_version_id}"
    )

    try:
        missing = client.get(
            catalog_route,
            headers={"X-Tenant-ID": tenant_id},
        )
        check(
            missing.status_code == 401,
            "Runtime workflow catalog rejects missing bearer",
            missing.text,
        )

        impersonated = client.get(
            catalog_route,
            headers={
                **farmer_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
        )
        check(
            impersonated.status_code == 403,
            "Runtime workflow catalog rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Runtime impersonation uses stable error code",
        )

        mismatch = client.get(
            catalog_route,
            headers={
                **farmer_headers,
                "X-Tenant-ID": foreign_tenant_id,
            },
        )
        check(
            mismatch.status_code == 403,
            "Runtime workflow catalog rejects tenant mismatch",
            mismatch.text,
        )
        check(
            mismatch.json()["detail"]["error"]
            == "TENANT_ID_MISMATCH",
            "Runtime tenant mismatch uses stable error code",
        )

        global_catalog = client.get(
            catalog_route,
            headers=farmer_headers,
        )
        check(
            global_catalog.status_code == 200,
            "Authenticated farmer reads tenant workflow catalog",
            global_catalog.text[:800],
        )
        check(
            global_catalog.json()["tenant_id"] == tenant_id,
            "Runtime catalog reports verified tenant",
        )

        project_catalog = client.get(
            project_catalog_route,
            headers=farmer_headers,
        )
        check(
            project_catalog.status_code == 200,
            "Enrolled farmer reads project workflow catalog",
            project_catalog.text[:800],
        )
        check(
            project_catalog.json()["project_id"] == str(project_id),
            "Project catalog reports authorized project",
        )

        unrelated = client.get(
            project_catalog_route,
            headers=unrelated_headers,
        )
        check(
            unrelated.status_code == 403,
            "Unrelated farmer cannot read project workflow catalog",
            unrelated.text,
        )
        check(
            unrelated.json()["detail"]["error"]
            == "WORKFLOW_PROJECT_SCOPE_DENIED",
            "Project denial uses stable error code",
        )

        foreign = client.get(
            (
                f"{catalog_route}?project_id="
                f"{foreign_project_id}"
            ),
            headers=farmer_headers,
        )
        check(
            foreign.status_code == 404,
            "Runtime catalog hides foreign-tenant project",
            foreign.text,
        )

        preview = client.get(
            preview_route,
            headers=farmer_headers,
        )
        check(
            preview.status_code == 200,
            "Enrolled farmer previews published project workflow",
            preview.text[:800],
        )
        check(
            preview.json()["tenant_id"] == tenant_id,
            "Published preview reports verified tenant",
        )

        preview_unrelated = client.get(
            preview_route,
            headers=unrelated_headers,
        )
        check(
            preview_unrelated.status_code == 403,
            "Unrelated farmer cannot preview project workflow",
            preview_unrelated.text,
        )

        admin_missing = client.get(
            draft_preview_route,
            headers={"X-Tenant-ID": tenant_id},
        )
        check(
            admin_missing.status_code == 401,
            "Draft preview rejects missing bearer",
            admin_missing.text,
        )

        admin_impersonated = client.get(
            draft_preview_route,
            headers={
                **viewer_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
        )
        check(
            admin_impersonated.status_code == 403,
            "Draft preview rejects actor impersonation",
            admin_impersonated.text,
        )
        check(
            admin_impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Admin impersonation uses stable error code",
        )

        admin_mismatch = client.get(
            draft_preview_route,
            headers={
                **viewer_headers,
                "X-Tenant-ID": foreign_tenant_id,
            },
        )
        check(
            admin_mismatch.status_code == 403,
            "Draft preview rejects tenant mismatch",
            admin_mismatch.text,
        )

        for label, route in (
            ("Draft preview", draft_preview_route),
            ("Publish impact", impact_route),
            ("Legacy-cycle pin report", legacy_route),
            ("Template version history", versions_route),
            ("Template audit history", audit_route),
        ):
            response = client.get(route, headers=viewer_headers)
            check(
                response.status_code == 200,
                f"{label} permits view administrator",
                response.text[:800],
            )

        viewer_validation = client.get(
            validation_route,
            headers=viewer_headers,
        )
        check(
            viewer_validation.status_code == 403,
            "Draft validation rejects view-only administrator",
            viewer_validation.text,
        )
        check(
            viewer_validation.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "Draft validation denial uses stable permission error",
        )

        validated = client.get(
            validation_route,
            headers=editor_headers,
        )
        check(
            validated.status_code == 200,
            "Editor validates workflow draft",
            validated.text[:1000],
        )

        verify = SessionLocal()
        try:
            event = (
                verify.query(WorkflowTemplateAuditEvent)
                .filter(
                    WorkflowTemplateAuditEvent.tenant_id
                    == tenant_id,
                    WorkflowTemplateAuditEvent.template_version_id
                    == draft_version_id,
                    WorkflowTemplateAuditEvent.action
                    == "VALIDATE_DRAFT",
                )
                .order_by(
                    WorkflowTemplateAuditEvent.created_at.desc()
                )
                .first()
            )
            check(
                event is not None,
                "Draft validation writes immutable audit event",
            )
            check(
                event.actor_id == editor_user_id,
                "Draft validation audit records verified editor",
                str(event.actor_id) if event else None,
            )
        finally:
            verify.close()

        admin_catalog = client.get(
            project_catalog_route,
            headers=admin_headers,
        )
        check(
            admin_catalog.status_code == 200,
            "Enterprise administrator reads tenant project catalog",
            admin_catalog.text[:800],
        )

    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(WorkflowTemplateAuditEvent).filter(
                WorkflowTemplateAuditEvent.template_version_id
                == draft_version_id
            ).delete(synchronize_session=False)
            cleanup.query(WorkflowTemplateVersion).filter(
                WorkflowTemplateVersion.id == draft_version_id
            ).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollment).filter(
                FarmerProjectEnrollment.id == enrollment_id
            ).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(
                Farmer.id == farmer_id
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.id.in_([project_id, foreign_project_id])
            ).delete(synchronize_session=False)
            cleanup.commit()

            for user_id in reversed(user_ids):
                delete_test_admin(cleanup, user_id)

            cleanup.query(Tenant).filter(
                Tenant.id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()

    print("=" * 72)
    print("Workflow catalog read authorization validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
