"""Regression for JWT-backed admin role and project-scope enforcement."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, ProjectRole, Tenant
from app.modules.master_data.models import (
    AgriculturalInput,
    AgriculturalInputAuditEvent,
    ProjectInputAssignment,
    ProjectInputAssignmentAuditEvent,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


TENANT_ID = "default"
TEMP_CODE = "ADMIN_PERMISSION_TEST_INPUT"


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant(db):
    if not db.query(Tenant).filter(Tenant.id == TENANT_ID).first():
        db.add(Tenant(
            id=TENANT_ID,
            name="Default",
            type="ENTERPRISE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()


def cleanup(db, *, user_ids, project_ids):
    db.rollback()
    db.query(ProjectInputAssignmentAuditEvent).filter(
        ProjectInputAssignmentAuditEvent.input_code == TEMP_CODE
    ).delete(synchronize_session=False)
    db.query(ProjectInputAssignment).filter(
        ProjectInputAssignment.input_code == TEMP_CODE
    ).delete(synchronize_session=False)
    db.query(AgriculturalInputAuditEvent).filter(
        AgriculturalInputAuditEvent.input_code == TEMP_CODE
    ).delete(synchronize_session=False)
    db.query(AgriculturalInput).filter(
        AgriculturalInput.code == TEMP_CODE
    ).delete(synchronize_session=False)
    db.query(ProjectRole).filter(
        ProjectRole.project_id.in_(project_ids)
    ).delete(synchronize_session=False)
    db.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
    db.commit()
    for user_id in user_ids:
        delete_test_admin(db, user_id)


def main():
    print("=" * 72)
    print("ADMIN AUTHORIZATION REGRESSION")
    print("=" * 72)
    client = TestClient(app)
    db = SessionLocal()
    users = []
    project_ids = [uuid.uuid4(), uuid.uuid4()]
    try:
        ensure_tenant(db)
        viewer, viewer_headers = create_test_admin(db, role="ADMIN_VIEWER")
        editor, editor_headers = create_test_admin(db, role="AGRONOMIST")
        publisher, publisher_headers = create_test_admin(db, role="MANAGER")
        enterprise, enterprise_headers = create_test_admin(db, role="ENTERPRISE_ADMIN")
        users = [viewer.id, editor.id, publisher.id, enterprise.id]

        payload = {
            "code": TEMP_CODE,
            "category_code": "FERTILIZER",
            "canonical_name": "Admin Permission Test Input",
            "unit": "kg",
            "applicable_crops": ["RICE"],
            "change_reason": "Authorization regression",
        }
        no_auth = client.post("/api/v1/input-catalog/inputs", json=payload)
        check(no_auth.status_code == 401, "Missing bearer token is rejected", no_auth.text)
        invalid_token = client.post(
            "/api/v1/input-catalog/inputs",
            headers={"Authorization": "Bearer invalid-token", "X-Tenant-ID": TENANT_ID},
            json=payload,
        )
        check(invalid_token.status_code == 401, "Invalid bearer token is rejected", invalid_token.text)
        viewer_create = client.post("/api/v1/input-catalog/inputs", headers=viewer_headers, json=payload)
        check(viewer_create.status_code == 403, "Viewer cannot edit master inputs", viewer_create.text)
        tenant_mismatch = client.post(
            "/api/v1/input-catalog/inputs",
            headers={**editor_headers, "X-Tenant-ID": "another-tenant"},
            json=payload,
        )
        check(tenant_mismatch.status_code == 403, "Token cannot cross tenant boundary", tenant_mismatch.text)
        mismatch_headers = {**editor_headers, "X-Actor-ID": str(uuid.uuid4())}
        mismatch = client.post("/api/v1/input-catalog/inputs", headers=mismatch_headers, json=payload)
        check(mismatch.status_code == 403, "Actor header cannot impersonate another user", mismatch.text)
        editor_create = client.post("/api/v1/input-catalog/inputs", headers=editor_headers, json=payload)
        check(editor_create.status_code == 200, "Agronomist can create master input", editor_create.text)

        editor_archive = client.post(
            f"/api/v1/input-catalog/inputs/{TEMP_CODE}/archive",
            headers=editor_headers,
            json={"reason": "Should be forbidden"},
        )
        check(editor_archive.status_code == 403, "Editor cannot archive master input", editor_archive.text)
        publisher_archive = client.post(
            f"/api/v1/input-catalog/inputs/{TEMP_CODE}/archive",
            headers=publisher_headers,
            json={"reason": "Publisher regression archive"},
        )
        check(publisher_archive.status_code == 200, "Publisher can archive unreferenced input", publisher_archive.text)
        publisher_restore = client.post(
            f"/api/v1/input-catalog/inputs/{TEMP_CODE}/restore",
            headers=publisher_headers,
            json={"reason": "Publisher regression restore"},
        )
        check(publisher_restore.status_code == 200, "Publisher can restore master input", publisher_restore.text)
        submit_input = client.post(
            f"/api/v1/input-catalog/inputs/{TEMP_CODE}/submit-review",
            headers=editor_headers,
            json={"reason": "Permission regression review"},
        )
        check(submit_input.status_code == 200, "Editor can submit input review", submit_input.text)
        publish_input = client.post(
            f"/api/v1/input-catalog/inputs/{TEMP_CODE}/publish",
            headers=publisher_headers,
            json={"reason": "Permission regression approval"},
        )
        check(publish_input.status_code == 200, "Publisher can publish reviewed input", publish_input.text)

        for index, project_id in enumerate(project_ids):
            db.add(Project(
                id=project_id,
                tenant_id=TENANT_ID,
                name=f"Permission Test Project {index + 1}",
                start_date=date(2027, 1, 1),
                end_date=date(2027, 12, 31),
                status="PLANNED",
                crop_scope=["RICE"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
        db.add(ProjectRole(
            id=uuid.uuid4(),
            project_id=project_ids[0],
            user_id=editor.id,
            role="AGRONOMIST",
            territory_scope={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()

        assigned_project = client.put(
            f"/api/v1/input-catalog/projects/{project_ids[0]}/input-assignments/{TEMP_CODE}",
            headers=editor_headers,
            json={"enabled": True, "reason": "Scoped editor regression"},
        )
        check(assigned_project.status_code == 200, "Project agronomist can edit assigned project", assigned_project.text)
        unassigned_project = client.put(
            f"/api/v1/input-catalog/projects/{project_ids[1]}/input-assignments/{TEMP_CODE}",
            headers=editor_headers,
            json={"enabled": True},
        )
        check(unassigned_project.status_code == 403, "Project editor cannot edit unassigned project", unassigned_project.text)
        enterprise_project = client.put(
            f"/api/v1/input-catalog/projects/{project_ids[1]}/input-assignments/{TEMP_CODE}",
            headers=enterprise_headers,
            json={"enabled": True, "reason": "Enterprise override regression"},
        )
        check(enterprise_project.status_code == 200, "Enterprise admin can edit tenant project", enterprise_project.text)

        random_version = uuid.uuid4()
        editor_publish = client.post(
            f"/api/v1/workflow-catalog/drafts/{random_version}/publish",
            headers=editor_headers,
            json={"archive_previous": True},
        )
        check(editor_publish.status_code == 403, "Editor cannot publish workflow", editor_publish.text)
        publisher_publish = client.post(
            f"/api/v1/workflow-catalog/drafts/{random_version}/publish",
            headers=publisher_headers,
            json={"archive_previous": True},
        )
        check(publisher_publish.status_code == 404, "Publisher passes authorization before workflow lookup", publisher_publish.text)
    finally:
        cleanup(db, user_ids=users, project_ids=project_ids)
        db.close()

    print("=" * 72)
    print("Admin authorization validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
