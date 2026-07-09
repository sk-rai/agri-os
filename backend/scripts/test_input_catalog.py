"""Regression for agricultural input catalog and workflow recommendation mapping."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Project, Tenant
from app.modules.master_data.models import AgriculturalInput, AgriculturalInputAuditEvent, ProjectInputAssignment, ProjectInputAssignmentAuditEvent
from app.modules.workflow.models import WorkflowTemplateRecommendation

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def now():
    return datetime.now(timezone.utc)


def ensure_default_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == "default").first()
    if not tenant:
        db.add(Tenant(id="default", name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def cleanup_project(db, project_id):
    db.query(ProjectInputAssignmentAuditEvent).filter(ProjectInputAssignmentAuditEvent.project_id == project_id).delete(synchronize_session=False)
    db.query(ProjectInputAssignment).filter(ProjectInputAssignment.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def check(condition, label, detail=None):
    icon = f"{GREEN}✅{RESET}" if condition else f"{RED}❌{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("INPUT CATALOG / WORKFLOW MAPPING REGRESSION")
    print("=" * 72)

    client = TestClient(app)

    print("\n[1] Input categories API")
    categories_response = client.get("/api/v1/input-catalog/categories")
    check(categories_response.status_code == 200, "Categories endpoint returns 200", f"Status: {categories_response.status_code}")
    category_codes = {c["code"] for c in categories_response.json()["categories"]}
    for code in ["SEED", "FERTILIZER", "ORGANIC_MANURE", "FUNGICIDE", "HERBICIDE", "LABOR", "MACHINERY", "IRRIGATION"]:
        check(code in category_codes, f"Category includes {code}")

    print("\n[2] Input search/filter API")
    fertilizer_response = client.get("/api/v1/input-catalog/inputs?category=FERTILIZER&crop_code=RICE")
    check(fertilizer_response.status_code == 200, "Fertilizer filter returns 200", f"Status: {fertilizer_response.status_code}")
    fertilizer_codes = {i["code"] for i in fertilizer_response.json()["inputs"]}
    check("UREA_46_N" in fertilizer_codes, "Rice fertilizer filter includes Urea")
    check("DAP_18_46_0" in fertilizer_codes, "Rice fertilizer filter includes DAP")

    urea_response = client.get("/api/v1/input-catalog/inputs/UREA_46_N")
    check(urea_response.status_code == 200, "Input detail returns 200", f"Status: {urea_response.status_code}")
    urea = urea_response.json()
    check(urea["canonical_name"] == "Urea", "Input detail returns canonical name")
    check("RICE" in urea["applicable_crops"], "Input detail includes applicable crop")

    references_response = client.get("/api/v1/input-catalog/inputs/UREA_46_N/references")
    check(references_response.status_code == 200, "Input references return 200")
    references_payload = references_response.json()
    check(
        references_payload["references"]["total"]
        == len(references_payload["usage"]["workflow_recommendations"])
        + len(references_payload["usage"]["project_assignments"]),
        "Input reference counts match detailed usage rows",
    )
    check(
        all(
            row.get("workflow_template_version_id") and row.get("stage_code")
            for row in references_payload["usage"]["workflow_recommendations"]
        ),
        "Workflow usage rows include version and stage identity",
    )
    check(
        all(
            row.get("project_id") and row.get("project_name")
            for row in references_payload["usage"]["project_assignments"]
        ),
        "Project usage rows include project identity",
    )

    print("\n[3] Input catalog admin create/update API")
    temp_code = "REGRESSION_TEST_INPUT"
    db = SessionLocal()
    try:
        db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code == temp_code).delete(synchronize_session=False)
        db.query(AgriculturalInput).filter(AgriculturalInput.code == temp_code).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    create_response = client.post("/api/v1/input-catalog/inputs", json={
        "code": temp_code,
        "category_code": "FERTILIZER",
        "canonical_name": "Regression Test Input",
        "unit": "kg",
        "composition": "Test composition",
        "standard_weight": "1",
        "applicable_crops": ["RICE"],
        "change_reason": "Regression test input create",
    })
    check(create_response.status_code == 200, "Input catalog create returns 200", f"Status: {create_response.status_code}")
    check(create_response.json()["code"] == temp_code, "Input catalog create returns created code")
    duplicate_response = client.post("/api/v1/input-catalog/inputs", json={
        "code": temp_code,
        "category_code": "FERTILIZER",
        "canonical_name": "Duplicate",
        "unit": "kg",
    })
    check(duplicate_response.status_code == 409, "Input catalog create rejects duplicate code", f"Status: {duplicate_response.status_code}")
    create_audit = client.get(f"/api/v1/input-catalog/inputs/{temp_code}/audit")
    check(create_audit.status_code == 200, "Created input audit returns 200", f"Status: {create_audit.status_code}")
    check(any(event["action"] == "CREATE_INPUT" for event in create_audit.json()["events"]), "Created input audit records CREATE_INPUT")
    archive_referenced = client.post("/api/v1/input-catalog/inputs/UREA_46_N/archive", json={"reason": "Regression referenced archive guard"})
    check(archive_referenced.status_code == 409, "Referenced input archive is blocked", f"Status: {archive_referenced.status_code}")
    archive_response = client.post(f"/api/v1/input-catalog/inputs/{temp_code}/archive", json={"reason": "Regression test archive"})
    check(archive_response.status_code == 200, "Unreferenced input archive returns 200", f"Status: {archive_response.status_code}")
    check(archive_response.json()["is_active"] is False, "Archived input reports inactive")
    active_search = client.get(f"/api/v1/input-catalog/inputs?q={temp_code}")
    check(active_search.status_code == 200, "Active catalog search after archive returns 200")
    check(active_search.json()["count"] == 0, "Archived input is hidden from active catalog")
    inactive_search = client.get(f"/api/v1/input-catalog/inputs?q={temp_code}&include_inactive=true")
    check(inactive_search.status_code == 200, "Include inactive catalog search returns 200")
    check(inactive_search.json()["count"] == 1, "Archived input appears when include_inactive=true")
    restore_response = client.post(f"/api/v1/input-catalog/inputs/{temp_code}/restore", json={"reason": "Regression test restore archived input"})
    check(restore_response.status_code == 200, "Archived input restore returns 200", f"Status: {restore_response.status_code}")
    check(restore_response.json()["is_active"] is True, "Restored input reports active")
    post_archive_audit = client.get(f"/api/v1/input-catalog/inputs/{temp_code}/audit")
    temp_actions = {event["action"] for event in post_archive_audit.json()["events"]}
    check({"CREATE_INPUT", "ARCHIVE_INPUT", "RESTORE_INPUT"}.issubset(temp_actions), "Input audit records create/archive/restore")
    db = SessionLocal()
    try:
        db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code == temp_code).delete(synchronize_session=False)
        db.query(AgriculturalInput).filter(AgriculturalInput.code == temp_code).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    update_payload = {
        "canonical_name": "Urea",
        "brand_name": "Regression Test Brand",
        "composition": urea.get("composition"),
        "unit": urea.get("unit"),
        "standard_weight": urea.get("standard_weight"),
        "applicable_crops": urea.get("applicable_crops", []),
        "application_method": urea.get("application_method"),
        "safety_instructions": urea.get("safety_instructions"),
        "aliases": urea.get("aliases", []),
        "change_reason": "Regression test metadata edit",
    }
    update_response = client.put("/api/v1/input-catalog/inputs/UREA_46_N", json=update_payload)
    check(update_response.status_code == 200, "Input catalog update returns 200", f"Status: {update_response.status_code}")
    check(update_response.json()["brand_name"] == "Regression Test Brand", "Input catalog update saves editable metadata")
    input_audit = client.get("/api/v1/input-catalog/inputs/UREA_46_N/audit")
    check(input_audit.status_code == 200, "Input catalog audit returns 200", f"Status: {input_audit.status_code}")
    audit_events = input_audit.json()["events"]
    check(any(event["action"] == "UPDATE_INPUT" for event in audit_events), "Input catalog audit records update action")
    check(any(event.get("reason") == "Regression test metadata edit" for event in audit_events), "Input catalog audit records change reason")
    restore_payload = {
        "canonical_name": urea.get("canonical_name"),
        "brand_name": urea.get("brand_name"),
        "composition": urea.get("composition"),
        "unit": urea.get("unit"),
        "standard_weight": urea.get("standard_weight"),
        "applicable_crops": urea.get("applicable_crops", []),
        "application_method": urea.get("application_method"),
        "safety_instructions": urea.get("safety_instructions"),
        "aliases": urea.get("aliases", []),
        "change_reason": "Regression test restore",
    }
    restore_response = client.put("/api/v1/input-catalog/inputs/UREA_46_N", json=restore_payload)
    check(restore_response.status_code == 200, "Input catalog test restore returns 200", f"Status: {restore_response.status_code}")
    db = SessionLocal()
    try:
        db.query(AgriculturalInputAuditEvent).filter(
            AgriculturalInputAuditEvent.input_code == "UREA_46_N",
            AgriculturalInputAuditEvent.reason.in_(["Regression test metadata edit", "Regression test restore"]),
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    print("\n[4] Project-aware input filter")
    db = SessionLocal()
    project_id = uuid.uuid4()
    try:
        ensure_default_tenant(db)
        db.add(Project(
            id=project_id,
            tenant_id="default",
            name="Input Catalog Project Scope Test",
            crop_scope=["RICE"],
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
        project_inputs = client.get(f"/api/v1/input-catalog/inputs?project_id={project_id}")
        check(project_inputs.status_code == 200, "Project-scoped input catalog returns 200", f"Status: {project_inputs.status_code}")
        project_payload = project_inputs.json()
        project_codes = {item["code"] for item in project_payload["inputs"]}
        check(project_payload["filter_policy"] == "PROJECT_ASSIGNMENT", "Project input catalog reports assignment policy")
        check("UREA_46_N" in project_codes, "Project Rice input catalog includes Urea")
        check("HEALTHY_CANE_SETTS" not in project_codes, "Project Rice input catalog excludes Sugarcane cane setts")
        blocked_crop = client.get(f"/api/v1/input-catalog/inputs?project_id={project_id}&crop_code=SUGARCANE")
        check(blocked_crop.status_code == 200, "Out-of-scope crop input filter returns 200", f"Status: {blocked_crop.status_code}")
        check(blocked_crop.json()["count"] == 0, "Out-of-scope crop input filter returns no inputs")

        assignments = client.get(f"/api/v1/input-catalog/projects/{project_id}/input-assignments")
        check(assignments.status_code == 200, "Project input assignment summary returns 200", f"Status: {assignments.status_code}")
        check(assignments.json()["counts"]["implicit_crop_scope"] > 0, "Summary reports implicit crop-scope visible inputs")

        enable_urea = client.put(
            f"/api/v1/input-catalog/projects/{project_id}/input-assignments/UREA_46_N",
            json={"enabled": True, "display_order": 1, "reason": "Preferred project fertilizer"},
        )
        check(enable_urea.status_code == 200, "Project input enablement returns 200", f"Status: {enable_urea.status_code}")
        enable_payload = enable_urea.json()
        check(enable_payload["explicit_assignment_scope"] is True, "Enabled assignment activates explicit input allow-list")
        urea_row = next(row for row in enable_payload["inputs"] if row["code"] == "UREA_46_N")
        dap_row = next(row for row in enable_payload["inputs"] if row["code"] == "DAP_18_46_0")
        check(urea_row["assignment_rule"] == "ANDROID_VISIBLE", "Enabled input is Android-visible")
        check(dap_row["assignment_rule"] == "NOT_ASSIGNED", "Unassigned input hidden in explicit allow-list mode")

        explicit_inputs = client.get(f"/api/v1/input-catalog/inputs?project_id={project_id}&crop_code=RICE")
        explicit_codes = {item["code"] for item in explicit_inputs.json()["inputs"]}
        check("UREA_46_N" in explicit_codes, "Explicit project input catalog includes enabled Urea")
        check("DAP_18_46_0" not in explicit_codes, "Explicit project input catalog excludes unassigned DAP")

        disable_urea = client.put(
            f"/api/v1/input-catalog/projects/{project_id}/input-assignments/UREA_46_N",
            json={"enabled": False, "display_order": 1, "reason": "Temporarily blocked"},
        )
        check(disable_urea.status_code == 200, "Project input disablement returns 200", f"Status: {disable_urea.status_code}")
        disabled_row = next(row for row in disable_urea.json()["inputs"] if row["code"] == "UREA_46_N")
        check(disabled_row["assignment_rule"] == "DISABLED_BY_PROJECT", "Disabled input reports DISABLED_BY_PROJECT")

        audit = client.get(f"/api/v1/input-catalog/projects/{project_id}/input-assignments/audit")
        check(audit.status_code == 200, "Project input assignment audit returns 200", f"Status: {audit.status_code}")
        audit_payload = audit.json()
        check(audit_payload["count"] >= 2, "Project input audit records enable/disable events", audit_payload)
        audit_actions = {event["action"] for event in audit_payload["events"]}
        check("CREATE_INPUT_ASSIGNMENT" in audit_actions or "ENABLE_INPUT" in audit_actions, "Audit includes create/enable action")
        check("DISABLE_INPUT" in audit_actions, "Audit includes disable action")
        urea_audit = client.get(f"/api/v1/input-catalog/projects/{project_id}/input-assignments/audit?input_code=UREA_46_N")
        check(urea_audit.status_code == 200, "Input-specific audit returns 200", f"Status: {urea_audit.status_code}")
        check(all(event["input_code"] == "UREA_46_N" for event in urea_audit.json()["events"]), "Input-specific audit is filtered")
        check(any(event.get("before") is not None and event.get("after") is not None for event in urea_audit.json()["events"]), "Audit includes before/after payloads")
    finally:
        cleanup_project(db, project_id)
        db.close()

    print("\n[5] Workflow recommendation mapping")
    db = SessionLocal()
    try:
        total = db.query(WorkflowTemplateRecommendation).count()
        mapped = db.query(WorkflowTemplateRecommendation).filter(WorkflowTemplateRecommendation.input_code.isnot(None)).count()
        check(total >= 50, "Workflow recommendations exist", f"Total: {total}")
        check(mapped >= 50, "Workflow recommendations have input_code mappings", f"Mapped: {mapped}")
    finally:
        db.close()

    rice_template = client.get("/api/v1/crop-cycles/templates/RICE?season=KHARIF")
    check(rice_template.status_code == 200, "Rice template returns 200", f"Status: {rice_template.status_code}")
    recommendations = [
        rec
        for stage in rice_template.json()["stages"]
        for rec in stage.get("recommended_activities", [])
    ]
    check(any(rec.get("input_code") == "UREA_46_N" for rec in recommendations), "Rice template recommendations include UREA_46_N")
    check(any(rec.get("input_code") == "FYM_COMPOST" for rec in recommendations), "Rice template recommendations include FYM_COMPOST")

    sugar_template = client.get("/api/v1/crop-cycles/templates/SUGARCANE?season=KHARIF")
    check(sugar_template.status_code == 200, "Sugarcane template returns 200", f"Status: {sugar_template.status_code}")
    sugar_recs = [
        rec
        for stage in sugar_template.json()["stages"]
        for rec in stage.get("recommended_activities", [])
    ]
    check(any(rec.get("input_code") == "HEALTHY_CANE_SETTS" for rec in sugar_recs), "Sugarcane recommendations include cane sett input code")
    check(any(rec.get("input_code") == "IRRIGATION_MOISTURE" for rec in sugar_recs), "Sugarcane recommendations include irrigation input code")

    print("\n" + "=" * 72)
    print("🟢 Input catalog and recommendation mappings validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
