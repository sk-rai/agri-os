"""Regression for backend-driven profile form contracts."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, ProjectAppConfigAuditEvent, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


REQUIRED_FORMS = {"farmer_registration", "parcel_registration", "soil_profile"}
REQUIRED_FLAGS = {
    "backend_driven_farmer_forms",
    "backend_driven_parcel_forms",
    "backend_driven_soil_forms",
}


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant(db):
    if not db.query(Tenant).filter(Tenant.id == "default").first():
        db.add(Tenant(id="default", name="Default", type="ENTERPRISE"))
        db.commit()


def field_by_id(schema, field_id):
    for field in schema["fields"]:
        if field["id"] == field_id:
            return field
    return None


def main():
    print("=" * 72)
    print("PROFILE FORM CONTRACT REGRESSION")
    print("=" * 72)
    db = SessionLocal()
    admin = None
    project = None
    ensure_tenant(db)
    client = TestClient(app)
    admin, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id="default")

    bootstrap = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": "default"})
    check(bootstrap.status_code == 200, "Bootstrap returns 200", bootstrap.text[:400])
    payload = bootstrap.json()
    check(payload["schema_version"] == "app_bootstrap.v1", "Bootstrap schema version is stable")
    check("profile_forms" in payload, "Bootstrap advertises profile_forms")
    check(REQUIRED_FLAGS.issubset(set(payload["feature_flags"].keys())), "Bootstrap exposes profile form feature flags")
    advertised = payload["profile_forms"]
    check(REQUIRED_FORMS.issubset(set(advertised.keys())), "Bootstrap advertises required profile forms", advertised.keys())

    schemas = {}
    for form_id in sorted(REQUIRED_FORMS):
        contract = advertised[form_id]
        check(contract["form_id"] == form_id, f"{form_id} contract echoes form id")
        check(contract["endpoint"] == f"/api/v1/forms/{form_id}", f"{form_id} endpoint is stable")
        check(contract["feature_flag"] in REQUIRED_FLAGS, f"{form_id} references a profile feature flag")
        response = client.get(contract["endpoint"], headers={"X-Tenant-ID": "default"})
        check(response.status_code == 200, f"{form_id} schema endpoint returns 200", response.text[:300])
        schema = response.json()
        schemas[form_id] = schema
        check(schema["form_id"] == form_id, f"{form_id} schema echoes form id")
        check(bool(schema["version"]), f"{form_id} has version")
        check(bool(schema["submit_endpoint"]), f"{form_id} has submit endpoint")
        check(isinstance(schema["fields"], list) and len(schema["fields"]) > 0, f"{form_id} has fields")
        check(all("id" in field and "type" in field and "label" in field for field in schema["fields"]), f"{form_id} fields include id/type/label")

    validation = client.get("/api/v1/app-config/profile-forms/validation", headers=headers)
    check(validation.status_code == 200, "Profile form validation returns 200", validation.text[:500])
    validation_payload = validation.json()
    check(validation_payload["schema_version"] == "profile_form_validation.v1", "Profile form validation schema is stable")
    check(validation_payload["ready"] is True, "Profile form validation reports ready")
    check(validation_payload["summary"]["form_count"] == 3, "Profile form validation counts required forms")
    check(validation_payload["summary"]["gps_field_count"] >= 3, "Profile form validation counts GPS widgets")
    check(validation_payload["summary"]["error_count"] == 0, "Profile form validation has no errors")

    farmer = schemas["farmer_registration"]
    check(field_by_id(farmer, "mobile_number") is not None, "Farmer form includes mobile_number")
    check(field_by_id(farmer, "mobile_number")["required"] is True, "Farmer mobile_number is required")
    check(field_by_id(farmer, "pin_code") is not None, "Farmer form includes Android PIN code")
    check(field_by_id(farmer, "assistance_mode")["android_hint"]["payload_field"] == "assistance_mode", "Farmer form advertises assistance_mode payload")
    check(field_by_id(farmer, "enrollment_location")["type"] == "GPS_POINT", "Farmer form includes GPS_POINT enrollment location")

    parcel = schemas["parcel_registration"]
    parcel_types = {field["type"] for field in parcel["fields"]}
    check("GPS_POINT" in parcel_types, "Parcel form includes GPS_POINT")
    check("GPS_POLYGON" in parcel_types, "Parcel form includes GPS_POLYGON")
    annual_rent = field_by_id(parcel, "annual_rent")
    check(annual_rent["depends_on"] == "ownership_type", "Parcel annual_rent depends on ownership_type")
    check(annual_rent["depends_on_value"] == "LEASED", "Parcel annual_rent serializes depends_on_value")
    check(field_by_id(parcel, "geometry_source")["default_value"] == "NONE", "Parcel form includes geometry_source default")
    check(field_by_id(parcel, "kharif_crops")["android_hint"]["payload_container"] == "crops_by_season", "Parcel form advertises seasonal crop payload container")

    soil = schemas["soil_profile"]
    lab_name = field_by_id(soil, "lab_name")
    shc = field_by_id(soil, "shc_card_number")
    check(lab_name["depends_on"] == "data_source" and lab_name["depends_on_value"] == "LAB_REPORT", "Soil lab_name conditional metadata is serialized")
    check(shc["depends_on"] == "data_source" and shc["depends_on_value"] == "SHC_CARD", "Soil SHC conditional metadata is serialized")
    check(field_by_id(soil, "boron_b")["canonical_field"] == "soil_profile.boron_bo", "Soil form maps Android boron_b to backend boron_bo")
    check(field_by_id(soil, "inferred_soil_type")["depends_on_value"] == "INFERRED", "Soil form includes inferred soil hint fields")

    project = Project(
        id=uuid.uuid4(),
        tenant_id="default",
        name="Profile Form Config Regression",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
        status="PLANNED",
        crop_scope=["RICE"],
        geography_scope={},
        config={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(project)
    db.commit()

    unauth_patch = client.patch(
        f"/api/v1/app-config/projects/{project.id}/config",
        headers={"X-Tenant-ID": "default"},
        json={"config_patch": {"feature_flags": {"backend_driven_farmer_forms": True}}, "reason": "Regression"},
    )
    check(unauth_patch.status_code == 401, "Project app config patch requires admin auth", unauth_patch.text)

    patch = client.patch(
        f"/api/v1/app-config/projects/{project.id}/config",
        headers=headers,
        json={"config_patch": {"feature_flags": {"backend_driven_farmer_forms": True, "backend_driven_parcel_forms": True}}, "reason": "Enable profile forms in regression"},
    )
    check(patch.status_code == 200, "Project app config patch returns 200", patch.text[:500])
    patched = patch.json()
    check(patched["schema_version"] == "effective_app_config.v1", "Patch returns effective config")
    check(patched["profile_forms"]["farmer_registration"]["enabled"] is True, "Farmer profile form flag is enabled by project patch")
    check(patched["profile_forms"]["parcel_registration"]["enabled"] is True, "Parcel profile form flag is enabled by project patch")
    check(patched["profile_forms"]["soil_profile"]["enabled"] is False, "Unpatched soil profile flag remains disabled")
    check(patched["layers"]["project"]["feature_flags"]["backend_driven_farmer_forms"] is True, "Project layer stores farmer flag")
    check(patched["update"]["audit_event"]["reason"] == "Enable profile forms in regression", "Patch response includes audit reason")
    check("feature_flags" in patched["update"]["audit_event"]["patched_sections"], "Patch response includes patched sections")

    audit = client.get(f"/api/v1/app-config/projects/{project.id}/config/audit", headers=headers)
    check(audit.status_code == 200, "Project app config audit returns 200", audit.text[:500])
    audit_payload = audit.json()
    check(audit_payload["schema_version"] == "project_app_config_audit.v1", "Project app config audit schema is stable")
    check(audit_payload["count"] >= 1, "Project app config audit returns events")
    latest_event = audit_payload["events"][0]
    check(latest_event["action"] == "UPDATE_PROJECT_APP_CONFIG", "Project app config audit records action")
    check(latest_event["reason"] == "Enable profile forms in regression", "Project app config audit records reason")
    check(latest_event["config_patch"]["feature_flags"]["backend_driven_farmer_forms"] is True, "Project app config audit records config patch")

    project_validation = client.get(f"/api/v1/app-config/profile-forms/validation?project_id={project.id}", headers=headers)
    check(project_validation.status_code == 200, "Project profile form validation returns 200", project_validation.text[:500])
    project_validation_payload = project_validation.json()
    check(project_validation_payload["filters"]["project_id"] == str(project.id), "Project profile form validation echoes project id")
    check(project_validation_payload["summary"]["enabled_count"] == 2, "Project profile form validation reflects enabled project flags")
    check(project_validation_payload["ready"] is True, "Project profile form validation reports ready")

    project_bootstrap = client.get(f"/api/v1/app-config/bootstrap?project_id={project.id}", headers={"X-Tenant-ID": "default"})
    check(project_bootstrap.status_code == 200, "Project bootstrap returns 200 after patch", project_bootstrap.text[:400])
    project_payload = project_bootstrap.json()
    check(project_payload["profile_forms"]["farmer_registration"]["enabled"] is True, "Project bootstrap advertises farmer profile flag")
    check(project_payload["profile_forms"]["parcel_registration"]["enabled"] is True, "Project bootstrap advertises parcel profile flag")

    db.query(ProjectAppConfigAuditEvent).filter(ProjectAppConfigAuditEvent.project_id == project.id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
    db.commit()
    if admin:
        delete_test_admin(db, admin.id)
        admin = None
    project = None

    print("=" * 72)
    print("Profile form contracts validated")
    print("=" * 72)
    if admin:
        delete_test_admin(db, admin.id)
    if project:
        db.query(ProjectAppConfigAuditEvent).filter(ProjectAppConfigAuditEvent.project_id == project.id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
        db.commit()
    db.close()


if __name__ == "__main__":
    main()
