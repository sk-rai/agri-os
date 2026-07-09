"""Regression for project workflow override create/delete endpoints."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Project, Tenant
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateEnablement, WorkflowTemplateOverride, WorkflowTemplateVersion
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
TENANT_ID = "default"


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    icon = f"{GREEN}✅{RESET}" if condition else f"{RED}❌{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def ensure_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        db.add(Tenant(id=TENANT_ID, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def cleanup(db, project_id):
    db.query(WorkflowTemplateOverride).filter(WorkflowTemplateOverride.project_id == project_id).delete(synchronize_session=False)
    db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def stage_codes(preview_payload):
    return [stage["code"] for stage in preview_payload["android_preview"]["stages"]]


def stage_by_code(preview_payload, code):
    return next(stage for stage in preview_payload["android_preview"]["stages"] if stage["code"] == code)


def recommendation_by_target(preview_payload, target_code):
    for stage in preview_payload["android_preview"]["stages"]:
        stage_code = stage["code"]
        for rec in stage.get("recommended_activities", []):
            input_name = (rec.get("input_name") or "").strip()
            activity_type = (rec.get("activity_type") or "").strip().upper()
            candidates = {
                input_name,
                input_name.lower(),
                f"{stage_code}|{input_name}",
                f"{stage_code}|{activity_type}|{input_name}",
            }
            input_code = rec.get("input_code")
            if input_code:
                candidates.add(str(input_code))
                candidates.add(f"{stage_code}|{input_code}")
            if target_code in candidates:
                return rec
    raise AssertionError(f"Recommendation target not found: {target_code}")


def create_override(client, project_id, version_id, payload):
    response = client.post(
        f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides",
        headers={"X-Tenant-ID": TENANT_ID},
        json={"template_version_id": str(version_id), **payload},
    )
    check(response.status_code == 200, f"{payload['operation']} override returns 200", f"Status: {response.status_code}")
    return response.json()


def main():
    print("=" * 72)
    print("PROJECT WORKFLOW OVERRIDE REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    project_id = uuid.uuid4()
    admin_user = None
    try:
        ensure_tenant(db)
        admin_user, admin_headers = create_test_admin(db)
        rice = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
        version = db.query(WorkflowTemplateVersion).filter(
            WorkflowTemplateVersion.template_id == rice.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
        ).first()
        check(rice is not None and version is not None, "Rice workflow/version exist")

        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Override Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        ))
        db.add(WorkflowTemplateEnablement(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            template_id=rice.id,
            enabled=True,
            display_order=1,
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        client = TestClient(app)
        client.headers.update(admin_headers)
        base = client.get(
            f"/api/v1/workflow-catalog/workflow-preview/{version.id}?project_id={project_id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(base.status_code == 200, "Base project preview returns 200", f"Status: {base.status_code}")
        check("FLOWERING" in stage_codes(base.json()), "FLOWERING stage initially visible")

        created_payload = create_override(client, project_id, version.id, {
            "target_type": "STAGE",
            "target_code": "FLOWERING",
            "operation": "HIDE",
            "override_payload": {},
            "priority": 10,
            "reason": "Regression hide flowering",
        })
        check("FLOWERING" not in stage_codes(created_payload), "FLOWERING hidden after override")
        check(len(created_payload["applied_overrides"]) == 1, "Preview reports applied override")
        override_id = created_payload["applied_overrides"][0]["id"]

        deleted = client.delete(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides/{override_id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(deleted.status_code == 200, "Delete override returns 200", f"Status: {deleted.status_code}")
        deleted_payload = deleted.json()
        check("FLOWERING" in stage_codes(deleted_payload), "FLOWERING visible again after override removal")
        check(len(deleted_payload["applied_overrides"]) == 0, "Preview has no applied overrides after delete")

        history_after_delete = client.get(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides?template_version_id={version.id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(history_after_delete.status_code == 200, "Override history returns 200", f"Status: {history_after_delete.status_code}")
        history_payload = history_after_delete.json()
        check(history_payload["counts"]["inactive"] == 1, "History includes removed override")
        removed_override = next(row for row in history_payload["overrides"] if row["id"] == override_id)
        check(removed_override["is_active"] is False, "Removed override is inactive in history")
        check(removed_override["payload"] == {}, "History includes override payload")
        check(bool(removed_override["created_at"]) and bool(removed_override["updated_at"]), "History includes created/updated timestamps")

        base_payload = base.json()
        nursery = stage_by_code(base_payload, "NURSERY")
        nursery_rec = nursery["recommended_activities"][0]
        rec_target = f"NURSERY|{nursery_rec['input_code']}" if nursery_rec.get("input_code") else f"NURSERY|{nursery_rec['activity_type']}|{nursery_rec['input_name']}"

        renamed = create_override(client, project_id, version.id, {
            "target_type": "STAGE",
            "target_code": "NURSERY",
            "operation": "RENAME",
            "override_payload": {"name": {"en": "Custom Nursery", "hi": "Custom Nursery"}},
            "priority": 20,
            "reason": "Regression rename stage",
        })
        check(stage_by_code(renamed, "NURSERY")["name"]["en"] == "Custom Nursery", "Stage rename appears in preview")

        duration_changed = create_override(client, project_id, version.id, {
            "target_type": "STAGE",
            "target_code": "NURSERY",
            "operation": "CHANGE_DURATION",
            "override_payload": {"duration_days": 17},
            "priority": 30,
            "reason": "Regression duration change",
        })
        check(stage_by_code(duration_changed, "NURSERY")["duration_days"] == 17, "Stage duration change appears in preview")

        offset_changed = create_override(client, project_id, version.id, {
            "target_type": "RECOMMENDATION",
            "target_code": rec_target,
            "operation": "CHANGE_OFFSET",
            "override_payload": {"day_offset": 9},
            "priority": 40,
            "reason": "Regression recommendation offset change",
        })
        check(recommendation_by_target(offset_changed, rec_target)["day_offset"] == 9, "Recommendation offset change appears in preview")

        quantity_changed = create_override(client, project_id, version.id, {
            "target_type": "RECOMMENDATION",
            "target_code": rec_target,
            "operation": "CHANGE_QUANTITY",
            "override_payload": {"typical_quantity": "custom quantity"},
            "priority": 50,
            "reason": "Regression recommendation quantity change",
        })
        check(recommendation_by_target(quantity_changed, rec_target)["typical_quantity"] == "custom quantity", "Recommendation quantity change appears in preview")
        check(len(quantity_changed["applied_overrides"]) == 4, "Preview reports all non-hide applied overrides")

        added = create_override(client, project_id, version.id, {
            "target_type": "STAGE",
            "target_code": "NURSERY",
            "operation": "ADD_RECOMMENDATION",
            "override_payload": {
                "day_offset": 6,
                "activity_type": "LABOR",
                "input_source": "CUSTOM",
                "input_name": "Custom nursery labour",
                "typical_quantity": "2 labour-days/acre",
                "typical_cost_per_acre": 900,
                "is_critical": False,
                "description": {"en": "Client-specific nursery labour line item"},
            },
            "priority": 60,
            "reason": "Regression add custom recommendation",
        })
        custom_rec = recommendation_by_target(added, "NURSERY|CUSTOM_CUSTOM_NURSERY_LABOUR")
        check(custom_rec["input_name"] == "Custom nursery labour", "Added recommendation appears in preview")
        check(custom_rec["day_offset"] == 6, "Added recommendation keeps day offset")
        check(custom_rec["typical_quantity"] == "2 labour-days/acre", "Added recommendation keeps quantity")
        check(custom_rec["metadata"]["source"] == "project_override", "Added recommendation is marked as project override sourced")
        check(custom_rec["metadata"]["input_source"] == "CUSTOM", "Project custom recommendation records custom source")
        check(custom_rec["input_code"] == "CUSTOM_CUSTOM_NURSERY_LABOUR", "Project custom recommendation receives stable code")
        check(len(added["applied_overrides"]) == 5, "Preview reports added recommendation override")

        history_with_active = client.get(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides?template_version_id={version.id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(history_with_active.status_code == 200, "Override history with active rows returns 200", f"Status: {history_with_active.status_code}")
        history_active_payload = history_with_active.json()
        check(history_active_payload["counts"]["active"] == 5, "History active count includes current overrides")
        check(history_active_payload["counts"]["inactive"] == 1, "History inactive count keeps removed override")
        added_history = next(row for row in history_active_payload["overrides"] if row["operation"] == "ADD_RECOMMENDATION")
        check(added_history["payload"]["input_name"] == "Custom nursery labour", "History includes add recommendation payload")
        check(bool(added_history["created_at"]) and bool(added_history["updated_at"]), "Active history rows include timestamps")

        active_only_history = client.get(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides?template_version_id={version.id}&include_inactive=false",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(active_only_history.status_code == 200, "Active-only override history returns 200", f"Status: {active_only_history.status_code}")
        check(active_only_history.json()["counts"]["inactive"] == 0, "Active-only history excludes removed overrides")

        invalid_add = client.post(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides",
            headers={"X-Tenant-ID": TENANT_ID},
            json={
                "template_version_id": str(version.id),
                "target_type": "RECOMMENDATION",
                "target_code": rec_target,
                "operation": "ADD_RECOMMENDATION",
                "override_payload": {"day_offset": 3, "activity_type": "LABOR", "input_name": "Bad add"},
                "priority": 65,
            },
        )
        check(invalid_add.status_code == 400, "ADD_RECOMMENDATION rejects recommendation target", f"Status: {invalid_add.status_code}")

        invalid = client.post(
            f"/api/v1/workflow-catalog/projects/{project_id}/workflow-overrides",
            headers={"X-Tenant-ID": TENANT_ID},
            json={
                "template_version_id": str(version.id),
                "target_type": "STAGE",
                "target_code": "NURSERY",
                "operation": "CHANGE_OFFSET",
                "override_payload": {"day_offset": 3},
                "priority": 70,
            },
        )
        check(invalid.status_code == 400, "Invalid operation/target combination is rejected", f"Status: {invalid.status_code}")
    finally:
        cleanup(db, project_id)
        if admin_user:
            delete_test_admin(db, admin_user.id)
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Project workflow override editor and history actions validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
