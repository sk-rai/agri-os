"""Regression for runtime app bootstrap configuration.

Validates:
- /api/v1/app-config/bootstrap is callable before login / without X-Tenant-ID
- tenant config overrides stable defaults
- project config overrides tenant defaults
- missing project returns 404
- form contracts are advertised for Android
"""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant


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
    print("APP CONFIG BOOTSTRAP REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    tenant_id = f"bootstrap-test-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    db = SessionLocal()
    try:
        public_response = client.get("/api/v1/app-config/bootstrap")
        check(public_response.status_code == 200, "Bootstrap works without tenant header", public_response.text[:300])
        public_payload = public_response.json()
        check(public_payload["schema_version"] == "app_bootstrap.v1", "Schema version is stable")
        check(public_payload["tenant"]["id"] == "default", "Public bootstrap uses default tenant context")
        check(public_payload["feature_flags"]["white_label_runtime_branding"] is True, "White-label feature flag is advertised")
        check(any(form["form_id"] == "activity_log" for form in public_payload["forms"]), "Activity log form version is advertised")

        tenant = Tenant(
            id=tenant_id,
            name="Bootstrap Tenant",
            type="FPO",
            config={
                "branding": {
                    "app_name": "Green Partner",
                    "primary_color": "#008000",
                    "support_phone": "+911234567890",
                },
                "localization": {
                    "default_language": "hi",
                    "supported_languages": ["hi", "en", "mr"],
                },
                "units": {
                    "default_area_unit": "ACRE",
                    "currency": "INR",
                },
                "enabled_modules": ["FARMER_PROFILE", "LAND_PARCELS"],
                "feature_flags": {
                    "backend_driven_farmer_forms": True,
                },
            },
            created_at=now(),
            updated_at=now(),
        )
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Bootstrap Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE", "SUGARCANE"],
            geography_scope={"state_ids": ["UP"]},
            config={
                "branding": {
                    "app_name": "Rice Field Program",
                    "accent_color": "#AA7700",
                },
                "feature_flags": {
                    "backend_driven_parcel_forms": True,
                },
            },
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([tenant, project])
        db.commit()

        tenant_response = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": tenant_id})
        check(tenant_response.status_code == 200, "Tenant bootstrap returns 200", tenant_response.text[:300])
        tenant_payload = tenant_response.json()
        check(tenant_payload["tenant"]["exists"] is True, "Tenant exists is true")
        check(tenant_payload["tenant"]["name"] == "Bootstrap Tenant", "Tenant name returned")
        check(tenant_payload["branding"]["app_name"] == "Green Partner", "Tenant branding overrides default app name")
        check(tenant_payload["branding"]["primary_color"] == "#008000", "Tenant primary color override applied")
        check(tenant_payload["branding"]["secondary_color"] == "#16A34A", "Unspecified nested branding default is preserved")
        check(tenant_payload["localization"]["default_language"] == "hi", "Tenant localization override applied")
        check(tenant_payload["units"]["default_area_unit"] == "ACRE", "Tenant unit override applied")
        check(tenant_payload["feature_flags"]["backend_driven_farmer_forms"] is True, "Tenant feature flag override applied")
        check(tenant_payload["feature_flags"]["media_attachments"] is False, "Unspecified feature flag default is preserved")

        project_response = client.get(
            f"/api/v1/app-config/bootstrap?project_id={project_id}",
            headers={"X-Tenant-ID": tenant_id},
        )
        check(project_response.status_code == 200, "Project bootstrap returns 200", project_response.text[:300])
        project_payload = project_response.json()
        check(project_payload["project"]["id"] == str(project_id), "Project id returned")
        check(project_payload["project"]["crop_scope"] == ["RICE", "SUGARCANE"], "Project crop scope returned")
        check(project_payload["branding"]["app_name"] == "Rice Field Program", "Project branding overrides tenant")
        check(project_payload["branding"]["primary_color"] == "#008000", "Tenant branding survives project partial override")
        check(project_payload["branding"]["accent_color"] == "#AA7700", "Project accent color override applied")
        check(project_payload["feature_flags"]["backend_driven_farmer_forms"] is True, "Tenant feature flag survives project merge")
        check(project_payload["feature_flags"]["backend_driven_parcel_forms"] is True, "Project feature flag override applied")
        check(project_payload["contracts"]["profile_hydration"]["schema_version"] == "profile_hydration.v1", "Hydration contract advertised")

        missing_response = client.get(
            f"/api/v1/app-config/bootstrap?project_id={uuid.uuid4()}",
            headers={"X-Tenant-ID": tenant_id},
        )
        check(missing_response.status_code == 404, "Missing project returns 404", missing_response.text)
    finally:
        db.rollback()
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print("=" * 72)
    print("App config bootstrap validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
