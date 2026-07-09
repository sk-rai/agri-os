"""Regression for crop-stage input compatibility and dosage rules."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from app.modules.master_data.models import CropStageInputRule, CropStageInputRuleAuditEvent
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

PROJECT = uuid.uuid4()
GLOBAL_STAGE = "REGRESSION_TILLERING"
PROJECT_STAGE = "REGRESSION_PROJECT_STAGE"


def now(): return datetime.now(timezone.utc)

def check(value, label):
    if not value: raise AssertionError(label)
    print("  OK", label)


def cleanup(db, admin=None):
    rule_ids = [r.id for r in db.query(CropStageInputRule).filter(CropStageInputRule.stage_code.in_([GLOBAL_STAGE, PROJECT_STAGE])).all()]
    if rule_ids:
        db.query(CropStageInputRuleAuditEvent).filter(CropStageInputRuleAuditEvent.rule_id.in_(rule_ids)).delete(synchronize_session=False)
        db.query(CropStageInputRule).filter(CropStageInputRule.id.in_(rule_ids)).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == PROJECT).delete(synchronize_session=False)
    db.commit()
    if admin: delete_test_admin(db, admin.id)


def main():
    db = SessionLocal(); admin, headers = create_test_admin(db); cleanup(db)
    try:
        if not db.query(Tenant).filter(Tenant.id == "default").first():
            db.add(Tenant(id="default", name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.add(Project(id=PROJECT, tenant_id="default", name="Input Rule Regression", start_date=date(2027,1,1), end_date=date(2027,12,31), status="PLANNED", crop_scope=["RICE"], created_at=now(), updated_at=now()))
        db.commit()
        client = TestClient(app, headers=headers)
        anonymous = TestClient(app)

        payload = {"crop_code":"rice", "season_code":"kharif", "stage_code":GLOBAL_STAGE, "activity_type":"fertilizer", "input_code":"UREA_46_N", "enabled":True, "priority":5, "dosage_quantity":"45", "dosage_unit":"kg", "dosage_area_unit":"acre", "min_quantity":"40", "max_quantity":"50", "application_method":"Broadcast after weeding", "timing_note":"Apply on moist soil", "safety_note":"Avoid standing water", "allowed_product_codes":[], "metadata":{"source":"regression"}, "reason":"Regression global dosage rule"}
        created = client.post("/api/v1/input-catalog/input-rules", json=payload)
        check(created.status_code == 200, f"global rule created: {created.status_code} {created.text}")
        rule = created.json(); rule_id = rule["id"]
        check(rule["crop_code"] == "RICE" and rule["dosage"]["quantity"] == "45.000", "rule normalizes codes and dosage")
        duplicate = client.post("/api/v1/input-catalog/input-rules", json=payload)
        check(duplicate.status_code == 409, "duplicate global rule is rejected")

        runtime = anonymous.get(f"/api/v1/input-catalog/input-rules?crop_code=RICE&stage_code={GLOBAL_STAGE}&activity_type=FERTILIZER", headers={"X-Tenant-ID":"default"})
        check(runtime.status_code == 200 and runtime.json()["count"] == 1, "runtime lists enabled global rule")
        check(runtime.json()["rules"][0]["input_code"] == "UREA_46_N", "runtime rule includes input code")

        project_payload = {**payload, "project_id": str(PROJECT), "stage_code": PROJECT_STAGE, "dosage_quantity":"38", "reason":"Regression project dosage rule"}
        project_rule = client.post("/api/v1/input-catalog/input-rules", json=project_payload)
        check(project_rule.status_code == 200 and project_rule.json()["rule_scope"] == "PROJECT", "project-specific rule is created")
        project_runtime = anonymous.get(f"/api/v1/input-catalog/input-rules?project_id={PROJECT}&crop_code=RICE", headers={"X-Tenant-ID":"default"})
        stages = {r["stage_code"] for r in project_runtime.json()["rules"]}
        check({GLOBAL_STAGE, PROJECT_STAGE}.issubset(stages), "project runtime includes global plus project rules")

        updated = client.patch(f"/api/v1/input-catalog/input-rules/{rule_id}", json={"enabled":False, "dosage_quantity":"42", "reason":"Regression disable rule"})
        check(updated.status_code == 200 and updated.json()["enabled"] is False and updated.json()["dosage"]["quantity"] == "42.000", "rule can be updated and disabled")
        hidden = anonymous.get(f"/api/v1/input-catalog/input-rules?crop_code=RICE&stage_code={GLOBAL_STAGE}", headers={"X-Tenant-ID":"default"})
        check(hidden.json()["count"] == 0, "disabled rule is hidden from runtime")
        forbidden = anonymous.get(f"/api/v1/input-catalog/input-rules?crop_code=RICE&stage_code={GLOBAL_STAGE}&include_disabled=true", headers={"X-Tenant-ID":"default"})
        check(forbidden.status_code == 403, "include_disabled requires admin")
        admin_disabled = client.get(f"/api/v1/input-catalog/input-rules?crop_code=RICE&stage_code={GLOBAL_STAGE}&include_disabled=true")
        check(admin_disabled.json()["count"] == 1, "admin can inspect disabled rules")

        audit = client.get(f"/api/v1/input-catalog/input-rules/audit?stage_code={GLOBAL_STAGE}")
        actions = {e["action"] for e in audit.json()["events"]}
        check({"CREATE_INPUT_RULE", "UPDATE_INPUT_RULE"}.issubset(actions), "rule create/update audit is recorded")
        print("PASS")
    finally:
        cleanup(db, admin); db.close()

if __name__ == "__main__": main()