"""Regression for project runtime app-config updates."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import (Farmer, Project, ProjectAppConfigAuditEvent, Tenant)
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

        print("\n[1] Project app-config requires verified project administration")
        missing_bearer = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers={"X-Tenant-ID": tenant_id},
            json={
                "branding": {"app_name": "Unauthenticated"},
                "reason": "Missing bearer rejected",
            },
        )
        check(
            missing_bearer.status_code == 401,
            "Project app-config rejects missing bearer",
            missing_bearer.text,
        )

        impersonated_headers = dict(headers)
        impersonated_headers["X-Actor-ID"] = str(uuid.uuid4())
        impersonated = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers=impersonated_headers,
            json={
                "branding": {"app_name": "Impersonated"},
                "reason": "Actor impersonation rejected",
            },
        )
        check(
            impersonated.status_code == 403,
            "Project app-config rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"] == "ACTOR_ID_MISMATCH",
            "Project actor impersonation has stable error code",
        )

        mismatched_headers = dict(headers)
        mismatched_headers["X-Tenant-ID"] = f"{tenant_id}-foreign"
        tenant_mismatch = client.patch(
            f"/api/v1/projects/{project_id}/app-config",
            headers=mismatched_headers,
            json={
                "branding": {"app_name": "Wrong Tenant"},
                "reason": "Tenant mismatch rejected",
            },
        )
        check(
            tenant_mismatch.status_code == 403,
            "Project app-config rejects token/header tenant mismatch",
            tenant_mismatch.text,
        )
        check(
            tenant_mismatch.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "Project tenant mismatch has stable permission error",
        )

        print("\n[2] Planned empty project can update feature flags")
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

        audit_rows = (
            db.query(ProjectAppConfigAuditEvent)
            .filter(
                ProjectAppConfigAuditEvent.tenant_id == tenant_id,
                ProjectAppConfigAuditEvent.project_id == project_id,
                ProjectAppConfigAuditEvent.action
                == "UPDATE_PROJECT_APP_CONFIG",
            )
            .order_by(ProjectAppConfigAuditEvent.created_at)
            .all()
        )
        check(
            len(audit_rows) == 2,
            "Successful project app-config mutations write two audits",
            len(audit_rows),
        )
        check(
            all(str(row.actor_id) == str(admin.id) for row in audit_rows),
            "Project app-config audits record verified administrator",
            [str(row.actor_id) for row in audit_rows],
        )
        check(
            audit_rows[0].reason
            == "Enable backend-driven forms for planned project",
            "Project app-config audit preserves initial reason",
        )
        check(
            audit_rows[1].patched_sections == ["branding"],
            "Locked branding audit records applied section",
            audit_rows[1].patched_sections,
        )
        check(
            audit_rows[1].before_config["branding"]["app_name"]
            == "Configured Project",
            "Project audit preserves prior configuration",
        )
        check(
            audit_rows[1].after_config["branding"]["app_name"]
            == "Locked Branding Update",
            "Project audit preserves resulting configuration",
        )
    finally:
        db.rollback()
        db.query(ProjectAppConfigAuditEvent).filter(
            ProjectAppConfigAuditEvent.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(Farmer).filter(
            Farmer.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.tenant_id == tenant_id
        ).delete(synchronize_session=False)
        db.commit()
        if admin:
            delete_test_admin(db, admin.id)
        db.query(Tenant).filter(
            Tenant.id == tenant_id
        ).delete(synchronize_session=False)
        db.commit()
        db.close()

    print("=" * 72)
    print("Project app config validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
