"""Regression for backend-driven profile form contracts."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import CompanyDiscoveryCandidate, CompanyProfile, CompanyProfileAuditEvent, Project, ProjectAppConfigAuditEvent, Tenant
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
    db.query(CompanyDiscoveryCandidate).filter(CompanyDiscoveryCandidate.tenant_id == "default").delete(synchronize_session=False)
    db.query(CompanyProfileAuditEvent).filter(CompanyProfileAuditEvent.tenant_id == "default").delete(synchronize_session=False)
    db.query(CompanyProfile).filter(CompanyProfile.tenant_id == "default").delete(synchronize_session=False)
    db.commit()
    client = TestClient(app)
    admin, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id="default")

    bootstrap = client.get("/api/v1/app-config/bootstrap", headers={"X-Tenant-ID": "default"})
    check(bootstrap.status_code == 200, "Bootstrap returns 200", bootstrap.text[:400])
    payload = bootstrap.json()
    check(payload["schema_version"] == "app_bootstrap.v1", "Bootstrap schema version is stable")
    check("profile_forms" in payload, "Bootstrap advertises profile_forms")
    check(REQUIRED_FLAGS.issubset(set(payload["feature_flags"].keys())), "Bootstrap exposes profile form feature flags")
    company_missing = client.get("/api/v1/tenants/default/company-profile", headers={"X-Tenant-ID": "default"})
    check(company_missing.status_code == 200, "Company profile empty read returns 200", company_missing.text[:300])
    check(company_missing.json()["schema_version"] == "company_profile.v1", "Company profile schema is stable")
    check(company_missing.json()["profile"] == {}, "Company profile starts unconfigured")

    company_patch = client.put(
        "/api/v1/tenants/default/company-profile",
        headers=headers,
        json={
            "legal_name": "Default Agri OS Customer Pvt Ltd",
            "display_name": "Default Customer",
            "company_type": "FPO",
            "profile_source": "PUBLIC_WEB",
            "verification_status": "UNVERIFIED",
            "source_references": [{"label": "Public directory seed", "url": "https://example.test/company"}],
            "registration_number": "REG-DEFAULT-001",
            "support_email": "support@example.test",
            "support_phone": "+910000000000",
            "head_office": {"state": "Uttar Pradesh", "district": "Azamgarh"},
            "operating_geography": {"states": ["UTTAR_PRADESH"], "districts": ["AZAMGARH"]},
            "crop_focus": ["RICE", "WHEAT"],
            "service_model": {"farmer_modes": ["SELF_SERVICE", "FIELD_AGENT_ASSISTED"]},
            "config": {"backend_only": True, "android_visible": False},
            "metadata": {"source": "profile-form-regression"},
        },
    )
    check(company_patch.status_code == 200, "Company profile upsert returns 200", company_patch.text[:500])
    company_payload = company_patch.json()
    check(company_payload["updated"] is True, "Company profile upsert marks updated")
    check(company_payload["profile"]["company_type"] == "FPO", "Company profile stores company type")
    check(company_payload["profile"]["profile_source"] == "PUBLIC_WEB", "Company profile stores prepopulation source")
    check(company_payload["profile"]["verification_status"] == "UNVERIFIED", "Company profile stores verification status")
    check(company_payload["profile"]["source_references"][0]["label"] == "Public directory seed", "Company profile stores source references")
    check(company_payload["profile"]["operating_geography"]["districts"] == ["AZAMGARH"], "Company profile stores operating geography")
    check(company_payload["profile"]["config"]["backend_only"] is True, "Company profile stores backend-only config")

    company_read = client.get("/api/v1/tenants/default/company-profile", headers={"X-Tenant-ID": "default"})
    check(company_read.status_code == 200, "Company profile read returns 200 after save", company_read.text[:400])
    check(company_read.json()["profile"]["display_name"] == "Default Customer", "Company profile read returns saved profile")

    company_audit = client.get("/api/v1/tenants/default/company-profile/audit", headers=headers)
    check(company_audit.status_code == 200, "Company profile audit returns 200", company_audit.text[:500])
    company_audit_payload = company_audit.json()
    check(company_audit_payload["schema_version"] == "company_profile_audit.v1", "Company profile audit schema is stable")
    check(company_audit_payload["count"] >= 1, "Company profile audit returns events")
    check(company_audit_payload["events"][0]["action"] == "UPSERT_COMPANY_PROFILE", "Company profile audit records action")
    check(company_audit_payload["events"][0]["source"] == "PUBLIC_WEB", "Company profile audit records source")
    check(company_audit_payload["events"][0]["after_profile"]["display_name"] == "Default Customer", "Company profile audit records after profile")


    company_candidate = client.post(
        "/api/v1/company-discovery-candidates",
        headers=headers,
        json={
            "candidate_name": "Azamgarh Farmer Producer Company",
            "company_type": "FPO",
            "source": "PUBLIC_WEB",
            "source_references": [{"label": "Registry/search seed", "url": "https://example.test/fpo"}],
            "discovered_profile": {"display_name": "Azamgarh FPC", "support_phone": "+910000000001"},
            "operating_geography": {"state": "UTTAR_PRADESH", "district": "AZAMGARH"},
            "crop_focus": ["RICE"],
            "confidence_score": 0.82,
            "duplicate_keys": {"normalized_name": "AZAMGARH FARMER PRODUCER COMPANY"},
            "metadata": {"prepopulation_batch": "regression"},
        },
    )
    check(company_candidate.status_code == 201, "Company discovery candidate create returns 201", company_candidate.text[:500])
    candidate_payload = company_candidate.json()
    check(candidate_payload["schema_version"] if "schema_version" in candidate_payload else "candidate.v1", "Company discovery candidate payload returned")
    check(candidate_payload["review_status"] == "PENDING_REVIEW", "Company discovery candidate starts pending review")
    check(candidate_payload["source"] == "PUBLIC_WEB", "Company discovery candidate stores source")
    check(candidate_payload["operating_geography"]["district"] == "AZAMGARH", "Company discovery candidate stores geography")
    candidate_id = candidate_payload["id"]

    candidate_list = client.get("/api/v1/company-discovery-candidates?review_status=PENDING_REVIEW&source=PUBLIC_WEB&q=azamgarh", headers=headers)
    check(candidate_list.status_code == 200, "Company discovery candidate list returns 200", candidate_list.text[:500])
    candidate_list_payload = candidate_list.json()
    check(candidate_list_payload["schema_version"] == "company_discovery_candidates.v1", "Company discovery candidate list schema is stable")
    check(candidate_list_payload["count"] >= 1, "Company discovery candidate list returns pending rows")

    candidate_review = client.patch(
        f"/api/v1/company-discovery-candidates/{candidate_id}/review",
        headers=headers,
        json={"review_status": "APPROVED", "matched_tenant_id": "default", "review_notes": "Approved for future tenant claim."},
    )
    check(candidate_review.status_code == 200, "Company discovery candidate review returns 200", candidate_review.text[:500])
    reviewed_candidate = candidate_review.json()
    check(reviewed_candidate["review_status"] == "APPROVED", "Company discovery candidate review status updates")
    check(reviewed_candidate["matched_tenant_id"] == "default", "Company discovery candidate can link matched tenant")
    check(reviewed_candidate["reviewed_by"] is not None, "Company discovery candidate records reviewer")



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
    option_sources = [field.get("source") for schema in schemas.values() for field in schema["fields"] if str(field.get("source", "")).startswith("profile_options.")]
    check("profile_options.land_units" in option_sources, "Profile forms reference land unit option set")
    check("profile_options.soil_textures" in option_sources, "Profile forms reference soil texture option set")

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
    ownership_values = {option["value"] for option in field_by_id(parcel, "ownership_type")["options"]}
    check("PART_OWNER" in ownership_values, "Parcel ownership types include part owner")

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

    invalid_option_set_patch = client.patch(
        f"/api/v1/app-config/projects/{project.id}/config",
        headers=headers,
        json={
            "config_patch": {"profile_options": {"overrides": {"unknown_units": {"options": [{"value": "X", "label": {"en": "X"}}]}}}},
            "reason": "Invalid option set regression",
        },
    )
    check(invalid_option_set_patch.status_code == 400, "Unknown profile option override is rejected", invalid_option_set_patch.text)
    check(invalid_option_set_patch.json()["detail"]["error"] == "INVALID_PROFILE_OPTION_OVERRIDES", "Unknown option override returns structured error")

    duplicate_option_patch = client.patch(
        f"/api/v1/app-config/projects/{project.id}/config",
        headers=headers,
        json={
            "config_patch": {
                "profile_options": {
                    "overrides": {
                        "land_units": {
                            "options": [
                                {"value": "ACRE", "label": {"en": "Acre"}},
                                {"value": "ACRE", "label": {"en": "Acre duplicate"}},
                            ]
                        }
                    }
                }
            },
            "reason": "Duplicate option regression",
        },
    )
    check(duplicate_option_patch.status_code == 400, "Duplicate profile option values are rejected", duplicate_option_patch.text)
    duplicate_codes = {error["code"] for error in duplicate_option_patch.json()["detail"]["errors"]}
    check("PROFILE_OPTION_VALUE_DUPLICATE" in duplicate_codes, "Duplicate profile option error code is returned")

    patch = client.patch(
        f"/api/v1/app-config/projects/{project.id}/config",
        headers=headers,
        json={
            "config_patch": {
                "feature_flags": {"backend_driven_farmer_forms": True, "backend_driven_parcel_forms": True},
                "profile_options": {
                    "overrides": {
                        "land_units": {
                            "version": "project-test-1",
                            "title": {"en": "Project Land Units", "hi": "Project Land Units"},
                            "options": [
                                {"value": "ACRE", "label": {"en": "Acre", "hi": "Acre"}},
                                {"value": "HECTARE", "label": {"en": "Hectare", "hi": "Hectare"}},
                            ],
                            "metadata": {"configured_for": "profile-form-regression"},
                        }
                    }
                },
            },
            "reason": "Enable profile forms in regression",
        },
    )
    check(patch.status_code == 200, "Project app config patch returns 200", patch.text[:500])
    patched = patch.json()
    check(patched["schema_version"] == "effective_app_config.v1", "Patch returns effective config")
    check(patched["profile_forms"]["farmer_registration"]["enabled"] is True, "Farmer profile form flag is enabled by project patch")
    check(patched["profile_forms"]["parcel_registration"]["enabled"] is True, "Parcel profile form flag is enabled by project patch")
    check(patched["profile_forms"]["soil_profile"]["enabled"] is False, "Unpatched soil profile flag remains disabled")
    check(patched["layers"]["project"]["feature_flags"]["backend_driven_farmer_forms"] is True, "Project layer stores farmer flag")
    check(patched["layers"]["project"]["profile_options"]["overrides"]["land_units"]["version"] == "project-test-1", "Project layer stores option override")
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

    profile_contract = client.get(f"/api/v1/forms/profile-contract?project_id={project.id}", headers={"X-Tenant-ID": "default"})
    check(profile_contract.status_code == 200, "Profile contract summary returns 200", profile_contract.text[:500])
    contract_payload = profile_contract.json()
    check(contract_payload["schema_version"] == "profile_contract.v1", "Profile contract schema is stable")
    check(contract_payload["backend_owned_contract"]["android_should_hardcode_options"] is False, "Profile contract forbids Android hardcoded options")
    check(contract_payload["backend_owned_contract"]["agent_assisted_capture"] is True, "Profile contract advertises agent-assisted capture")
    check(contract_payload["backend_owned_contract"]["mode_bootstrap"] is True, "Profile contract advertises mode bootstrap")
    handoff = contract_payload["android_handoff"]
    check(handoff["mode_bootstrap_endpoint"] == "/api/v1/auth/mode-bootstrap", "Profile contract links mode bootstrap endpoint")
    check(handoff["agent_assisted_capture"]["dual_mode_supported"] is True, "Profile contract supports dual farmer/agent mode")
    check(handoff["location_model"]["normal_anchor"] == "parcel.pin_code", "Profile contract documents parcel PIN code anchor")
    check(handoff["location_model"]["multi_village_override"] == "parcel.location_scope", "Profile contract documents multi-village override")
    check("SHC_SLUSI" in handoff["soil_enrichment"]["manual_import_sources"], "Profile contract advertises SHC/SLUSI manual/import source")
    check("parcel_registration" in handoff["offline_sync"]["replay_order"], "Profile contract documents offline replay order")
    check(contract_payload["payload_mappings"]["parcel_registration"]["location_scope"] == "parcel.location_scope", "Profile contract maps parcel location_scope payload")
    check(contract_payload["payload_mappings"]["soil_profile"]["boron_b"] == "soil_profile.boron_bo", "Profile contract maps Android boron alias")

    project_options = client.get(f"/api/v1/forms/options?project_id={project.id}", headers={"X-Tenant-ID": "default"})
    check(project_options.status_code == 200, "Project profile option registry returns 200", project_options.text[:400])
    option_sources = {item["option_set"]: item.get("source") for item in project_options.json()["option_sets"]}
    check(option_sources["land_units"] == "project", "Project option registry marks overridden source")
    project_land_units = client.get(f"/api/v1/forms/options/land_units?project_id={project.id}", headers={"X-Tenant-ID": "default"})
    check(project_land_units.status_code == 200, "Project land unit override returns 200", project_land_units.text[:400])
    project_land_payload = project_land_units.json()
    check(project_land_payload["version"] == "project-test-1", "Project land unit override version is returned")
    check({item["value"] for item in project_land_payload["options"]} == {"ACRE", "HECTARE"}, "Project land unit override replaces default values")
    check(project_land_payload["metadata"]["source"] == "project", "Project land unit override exposes source metadata")

    db.query(ProjectAppConfigAuditEvent).filter(ProjectAppConfigAuditEvent.project_id == project.id).delete(synchronize_session=False)
    db.query(CompanyDiscoveryCandidate).filter(CompanyDiscoveryCandidate.tenant_id == "default").delete(synchronize_session=False)
    db.query(CompanyProfileAuditEvent).filter(CompanyProfileAuditEvent.tenant_id == "default").delete(synchronize_session=False)
    db.query(CompanyProfile).filter(CompanyProfile.tenant_id == "default").delete(synchronize_session=False)
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
