"""Regression for effective project app-config inspection."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, ProjectRole, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def now():
    return datetime.now(timezone.utc)


def main():
    print("=" * 72)
    print("EFFECTIVE APP CONFIG REGRESSION")
    print("=" * 72)

    tenant_id = f"effective-config-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    viewer = None
    outsider = None
    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Effective Config Tenant",
            type="ENTERPRISE",
            config={
                "branding": {"app_name": "Tenant Brand", "primary_color": "#006600"},
                "feature_flags": {
                    "backend_driven_farmer_forms": True,
                    "backend_driven_soil_forms": True,
                },
                "units": {"default_area_unit": "ACRE", "currency": "INR"},
            },
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Effective Config Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            config={
                "branding": {"app_name": "Project Brand"},
                "feature_flags": {"backend_driven_parcel_forms": True},
            },
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
        viewer, viewer_headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id=tenant_id)
        outsider, outsider_headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id=tenant_id)
        db.add(ProjectRole(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=viewer.id,
            role="ADMIN_VIEWER",
            territory_scope={},
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        client = TestClient(app)
        endpoint = f"/api/v1/app-config/projects/{project_id}/effective-app-config"

        no_auth = client.get(endpoint, headers={"X-Tenant-ID": tenant_id})
        check(no_auth.status_code == 401, "Effective config requires admin auth", no_auth.text)

        denied = client.get(endpoint, headers=outsider_headers)
        check(denied.status_code == 403, "Unassigned project viewer is denied", denied.text)

        response = client.get(endpoint, headers=viewer_headers)
        check(response.status_code == 200, "Assigned viewer can read effective config", response.text[:500])
        payload = response.json()
        check(payload["schema_version"] == "effective_app_config.v1", "Schema version is stable")
        check(payload["tenant"]["id"] == tenant_id, "Tenant id returned")
        check(payload["project"]["id"] == str(project_id), "Project id returned")
        check(payload["layers"]["tenant"]["branding"]["app_name"] == "Tenant Brand", "Tenant layer is returned")
        check(payload["layers"]["project"]["branding"]["app_name"] == "Project Brand", "Project layer is returned")
        check(payload["effective_config"]["branding"]["app_name"] == "Project Brand", "Project branding wins")
        check(payload["effective_config"]["branding"]["primary_color"] == "#006600", "Tenant branding fills project gaps")
        check(payload["effective_config"]["units"]["default_area_unit"] == "ACRE", "Tenant units flow through")
        check(payload["profile_forms"]["farmer_registration"]["enabled"] is True, "Farmer form enabled from tenant")
        check(payload["profile_forms"]["parcel_registration"]["enabled"] is True, "Parcel form enabled from project")
        check(payload["profile_forms"]["soil_profile"]["enabled"] is True, "Soil form enabled from tenant")
        check(payload["section_sources"]["branding"] == "project", "Branding source is project")
        check(payload["section_sources"]["units"] == "tenant", "Units source is tenant")
        check(payload["section_sources"]["self_service"] == "default", "Self-service source is default")

        missing = client.get(f"/api/v1/app-config/projects/{uuid.uuid4()}/effective-app-config", headers=viewer_headers)
        check(missing.status_code == 404, "Missing project returns 404", missing.text)
    finally:
        db.rollback()
        db.query(ProjectRole).filter(ProjectRole.project_id == project_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        if viewer:
            delete_test_admin(db, viewer.id)
        if outsider:
            delete_test_admin(db, outsider.id)
        db.close()

    print("=" * 72)
    print("Effective app config validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
