"""Regression for project runtime app-config updates."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Project, Tenant
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
    print("PROJECT APP CONFIG REGRESSION")
    print("=" * 72)

    tenant_id = f"project-config-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    admin = None
    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Project Config Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Project Config Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            config={},
            created_at=now(),
            updated_at=now(),
        )
        db.add(project)
        db.commit()
        admin, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=tenant_id)

        client = TestClient(app)

        print("\n[1] Planned empty project can update feature flags")
        response = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers=headers,
            json={
                "branding": {"app_name": "Configured Project", "primary_color": "#123456"},
                "feature_flags": {
                    "backend_driven_farmer_forms": True,
                    "backend_driven_parcel_forms": True,
                    "backend_driven_soil_forms": True,
                },
                "enabled_modules": ["FARMER_PROFILE", "LAND_PARCELS", "SOIL_PROFILE"],
                "reason": "Enable backend-driven forms for planned project",
            },
        )
        check(response.status_code == 200, "Project app-config patch returns 200", response.text)
        payload = response.json()
        check(payload["schema_version"] == "project_app_config.v1", "Response schema version is stable")
        check(payload["updated"] is True, "Patch response marks updated")
        check(payload["config"]["branding"]["app_name"] == "Configured Project", "Branding config updated")
        check(payload["config"]["feature_flags"]["backend_driven_farmer_forms"] is True, "Farmer form flag updated")
        check("feature_flags" in payload["applied_sections"], "Applied sections report feature flags")

        print("\n[2] Bootstrap reflects project app-config")
        bootstrap = client.get(
            f"/api/v1/app-config/bootstrap?project_id={project_id}",
            headers={"X-Tenant-ID": tenant_id},
        )
        check(bootstrap.status_code == 200, "Bootstrap returns 200 after config patch", bootstrap.text[:300])
        body = bootstrap.json()
        check(body["branding"]["app_name"] == "Configured Project", "Bootstrap reflects project branding")
        check(body["profile_forms"]["farmer_registration"]["enabled"] is True, "Bootstrap enables farmer form")
        check(body["profile_forms"]["parcel_registration"]["enabled"] is True, "Bootstrap enables parcel form")
        check(body["profile_forms"]["soil_profile"]["enabled"] is True, "Bootstrap enables soil form")

        print("\n[3] Locked project blocks risky behavior-changing sections")
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9198{uuid.uuid4().int % 100000000:08d}",
            village_name_manual="Config Village",
            display_name="Config Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        blocked = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers=headers,
            json={
                "feature_flags": {"backend_driven_farmer_forms": False},
                "reason": "Unsafe change after enrollment",
            },
        )
        check(blocked.status_code == 409, "Locked project blocks feature flag changes", blocked.text)
        detail = blocked.json()["detail"]
        check(detail["error"] == "PROJECT_APP_CONFIG_LOCKED", "Blocked response has stable error code")
        check("feature_flags" in detail["blocked_sections"], "Blocked response names feature_flags")

        print("\n[4] Locked project still allows branding-only updates")
        branding = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers=headers,
            json={
                "branding": {"app_name": "Locked Branding Update"},
                "reason": "Safe display-only update",
            },
        )
        check(branding.status_code == 200, "Locked project allows branding update", branding.text)
        check(branding.json()["config"]["branding"]["app_name"] == "Locked Branding Update", "Locked branding update persisted")
    finally:
        db.rollback()
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        if admin:
            delete_test_admin(db, admin.id)
        db.close()

    print("=" * 72)
    print("Project app config validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
