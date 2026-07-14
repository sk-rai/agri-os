"""Regression for tenant-level runtime app-config updates."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
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
    print("TENANT APP CONFIG REGRESSION")
    print("=" * 72)

    tenant_id = f"tenant-config-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    db = SessionLocal()
    enterprise = None
    manager = None
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Tenant Config Test",
            type="ENTERPRISE",
            config={},
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Tenant Config Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            config={"branding": {"app_name": "Project Override"}},
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
        enterprise, enterprise_headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=tenant_id)
        manager, manager_headers = create_test_admin(db, role="MANAGER", tenant_id=tenant_id)
        client = TestClient(app)

        print("\n[1] Non-enterprise admin cannot update tenant app-config")
        denied = client.patch(
            f"/api/v1/tenants/{tenant_id}/app-config",
            headers=manager_headers,
            json={"branding": {"app_name": "Should Not Apply"}, "reason": "Manager denied"},
        )
        check(denied.status_code == 403, "Manager is denied tenant app-config update", denied.text)
        check(denied.json()["detail"]["error"] == "ENTERPRISE_ADMIN_REQUIRED", "Denied response has stable error code")

        print("\n[2] Enterprise admin updates tenant app-config")
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}/app-config",
            headers=enterprise_headers,
            json={
                "branding": {
                    "app_name": "Tenant Brand",
                    "primary_color": "#006600",
                },
                "localization": {
                    "default_language": "hi",
                    "supported_languages": ["hi", "en"],
                    "country_code": "IN",
                },
                "units": {
                    "default_area_unit": "ACRE",
                    "currency": "INR",
                },
                "feature_flags": {
                    "backend_driven_farmer_forms": True,
                    "backend_driven_soil_forms": True,
                },
                "reason": "Tenant white-label defaults",
            },
        )
        check(response.status_code == 200, "Tenant app-config patch returns 200", response.text)
        payload = response.json()
        check(payload["schema_version"] == "tenant_app_config.v1", "Response schema version is stable")
        check(payload["config"]["branding"]["app_name"] == "Tenant Brand", "Tenant branding updated")
        check(payload["config"]["feature_flags"]["backend_driven_farmer_forms"] is True, "Tenant farmer form flag updated")
        check("feature_flags" in payload["applied_sections"], "Applied sections include feature flags")

        print("\n[3] Bootstrap reflects tenant defaults")
        tenant_bootstrap = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": tenant_id})
        check(tenant_bootstrap.status_code == 200, "Tenant bootstrap returns 200", tenant_bootstrap.text[:300])
        tenant_body = tenant_bootstrap.json()
        check(tenant_body["branding"]["app_name"] == "Tenant Brand", "Bootstrap reflects tenant branding")
        check(tenant_body["units"]["default_area_unit"] == "ACRE", "Bootstrap reflects tenant units")
        check(tenant_body["profile_forms"]["farmer_registration"]["enabled"] is True, "Tenant enables farmer form")
        check(tenant_body["profile_forms"]["parcel_registration"]["enabled"] is False, "Tenant leaves parcel form disabled")
        check(tenant_body["profile_forms"]["soil_profile"]["enabled"] is True, "Tenant enables soil form")

        print("\n[4] Project config overrides tenant config")
        project_bootstrap = client.get(
            f"/api/v1/app-config/bootstrap?project_id={project_id}",
            headers={"X-Tenant-ID": tenant_id},
        )
        check(project_bootstrap.status_code == 200, "Project bootstrap returns 200", project_bootstrap.text[:300])
        project_body = project_bootstrap.json()
        check(project_body["branding"]["app_name"] == "Project Override", "Project branding overrides tenant branding")
        check(project_body["branding"]["primary_color"] == "#006600", "Tenant branding fills unspecified project values")
        check(project_body["profile_forms"]["farmer_registration"]["enabled"] is True, "Project inherits tenant farmer form flag")

        print("\n[5] Tenant path/header mismatch is rejected")
        mismatch = client.patch(
            f"/api/v1/tenants/{tenant_id}-other/app-config",
            headers=enterprise_headers,
            json={"branding": {"app_name": "Mismatch"}, "reason": "Mismatch denied"},
        )
        check(mismatch.status_code == 403, "Tenant path/header mismatch rejected", mismatch.text)
    finally:
        db.rollback()
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        if enterprise:
            delete_test_admin(db, enterprise.id)
        if manager:
            delete_test_admin(db, manager.id)
        db.close()

    print("=" * 72)
    print("Tenant app config validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
