"""Regression for workflow CSV validation against DRAFT versions."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def check(condition: bool, label: str, detail=None):
    icon = f"{GREEN}?{RESET}" if condition else f"{RED}?{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def csv_text(response) -> str:
    return response.content.decode("utf-8-sig")


def find_published_rice(db):
    row = db.query(WorkflowTemplate, WorkflowTemplateVersion).join(
        WorkflowTemplateVersion,
        WorkflowTemplateVersion.template_id == WorkflowTemplate.id,
    ).filter(
        WorkflowTemplate.crop_code == "RICE",
        WorkflowTemplate.season_code == "KHARIF",
        WorkflowTemplateVersion.status == "PUBLISHED",
        WorkflowTemplate.is_active == True,
        WorkflowTemplateVersion.is_active == True,
    ).first()
    check(row is not None, "published Rice/Kharif workflow exists")
    return row


def upload_workflow_csv(client: TestClient, draft_id: str, content: str):
    return client.post(
        f"/api/v1/workflow-catalog/csv/workflows/drafts/{draft_id}/validate",
        files={"file": ("workflow.csv", io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def apply_workflow_csv(client: TestClient, draft_id: str, content: str, reason: str = "Regression apply"):
    return client.post(
        f"/api/v1/workflow-catalog/csv/workflows/drafts/{draft_id}/apply",
        data={"reason": reason},
        files={"file": ("workflow.csv", io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def main():
    print("=" * 72)
    print("WORKFLOW CSV DRAFT VALIDATION REGRESSION")
    print("=" * 72)

    anonymous = TestClient(app)
    denied = anonymous.post(
        "/api/v1/workflow-catalog/csv/workflows/drafts/00000000-0000-0000-0000-000000000000/validate",
        headers={"X-Tenant-ID": "default"},
        files={"file": ("workflow.csv", b"template_code,crop_code,season_code,stage_order,stage_code,stage_name_en,duration_days\n", "text/csv")},
    )
    check(denied.status_code == 401, "workflow CSV validation requires admin authentication", denied.text)

    db = SessionLocal()
    admin, headers = create_test_admin(db)
    try:
        template, source_version = find_published_rice(db)
        client = TestClient(app, headers=headers)

        clone = client.post(f"/api/v1/workflow-catalog/templates/{template.id}/versions/{source_version.id}/clone-draft", json={"version_number": "csv-validation-regression"})
        check(clone.status_code == 200, "clone draft for CSV validation returns 200", clone.text[:300])
        draft_id = clone.json()["draft_version_id"]

        export = client.get(f"/api/v1/workflow-catalog/csv/workflows/export?template_version_id={source_version.id}&status=ALL")
        check(export.status_code == 200, "source workflow CSV export returns 200", export.text[:200])
        valid_csv = csv_text(export)
        valid = upload_workflow_csv(client, draft_id, valid_csv)
        check(valid.status_code == 200, "valid workflow CSV validation returns 200", valid.text[:300])
        report = valid.json()
        check(report["schema_version"] == "workflow_csv_validation.v1", "workflow CSV validation schema version is stable")
        check(report["mode"] == "VALIDATE_ONLY", "workflow CSV validation is non-mutating")
        check(report["apply_available"] is True, "workflow CSV apply is available for valid draft uploads")
        check(report["can_apply"] is True, "exported workflow CSV validates against draft")
        check(report["summary"]["errors"] == 0, "valid workflow CSV has zero errors")
        check(report["summary"]["stages"] > 0, "valid workflow CSV counts stages")
        check(report["summary"]["recommendations"] > 0, "valid workflow CSV counts recommendations")
        check(report["workflow_template_version_id"] == draft_id, "validation report targets requested draft")

        edited_rows = list(csv.DictReader(io.StringIO(valid_csv)))
        first_stage = edited_rows[0]["stage_code"]
        for row in edited_rows:
            if row["stage_code"] == first_stage:
                row["stage_name_en"] = "CSV Applied Stage Name"
                row["duration_days"] = "17"
        edited_buffer = io.StringIO()
        writer = csv.DictWriter(edited_buffer, fieldnames=edited_rows[0].keys())
        writer.writeheader()
        writer.writerows(edited_rows)
        edited_csv = edited_buffer.getvalue()
        applied = apply_workflow_csv(client, draft_id, edited_csv, reason="Regression CSV apply")
        check(applied.status_code == 200, "valid workflow CSV apply returns 200", applied.text[:500])
        apply_report = applied.json()
        check(apply_report["mode"] == "APPLY", "apply report is returned in APPLY mode")
        check(apply_report["can_apply"] is True, "valid workflow CSV apply report remains clean")
        check(apply_report["file_name"] == "workflow.csv", "apply report includes uploaded file name")
        required_summary_keys = {"total_rows", "stages", "recommendations", "errors", "warnings", "stage_create", "stage_update", "stage_unchanged"}
        check(required_summary_keys.issubset(set(apply_report["summary"].keys())), "apply response summary exposes admin UI contract", sorted(apply_report["summary"].keys()))
        check(apply_report["summary"]["total_rows"] == len(edited_rows), "apply response summary counts uploaded rows")
        check(apply_report["summary"]["stages"] > 0, "apply response summary counts stages")
        check(apply_report["summary"]["recommendations"] > 0, "apply response summary counts recommendations")
        check(apply_report["summary"]["errors"] == 0, "apply response summary has zero errors after clean apply")
        check(apply_report["summary"]["stage_update"] >= 1, "apply response summary captures updated stages")
        preview = client.get(f"/api/v1/workflow-catalog/draft-preview/{draft_id}")
        check(preview.status_code == 200, "draft preview after CSV apply returns 200", preview.text[:300])
        first_preview_stage = next(stage for stage in preview.json()["android_preview"]["stages"] if stage["code"] == first_stage)
        check(first_preview_stage["name"]["en"] == "CSV Applied Stage Name", "CSV apply updates stage name")
        check(first_preview_stage["duration_days"] == 17, "CSV apply updates stage duration")
        audit = client.get(f"/api/v1/workflow-catalog/templates/{template.id}/audit?version_id={draft_id}&limit=20")
        check(audit.status_code == 200, "workflow audit after CSV apply returns 200", audit.text[:300])
        actions = [event["action"] for event in audit.json()["events"]]
        check("APPLY_WORKFLOW_CSV" in actions, "workflow audit records CSV apply")
        filtered_audit = client.get(f"/api/v1/workflow-catalog/templates/{template.id}/audit?version_id={draft_id}&action=APPLY_WORKFLOW_CSV&limit=20")
        check(filtered_audit.status_code == 200, "workflow audit action filter returns 200", filtered_audit.text[:300])
        filtered_events = filtered_audit.json()["events"]
        check(filtered_events and all(event["action"] == "APPLY_WORKFLOW_CSV" for event in filtered_events), "workflow audit action filter returns only CSV apply events")
        csv_event = filtered_events[0]
        check(csv_event["metadata"]["file_name"] == "workflow.csv", "filtered CSV apply audit includes file name")
        check(csv_event["metadata"]["summary"]["total_rows"] == apply_report["summary"]["total_rows"], "filtered CSV apply audit includes row count")

        header = ["template_code", "crop_code", "season_code", "propagation_type_code", "version_number", "version_status", "stage_order", "stage_code", "stage_name_en", "stage_name_hi", "duration_days", "stage_type", "phase", "description_en", "description_hi", "farmer_actions_json", "typical_inputs_json", "key_observations_json", "recommendation_sort_order", "recommendation_day_offset", "activity_type", "input_code", "input_name", "typical_quantity", "typical_cost_per_acre", "is_critical", "recommendation_description_en", "recommendation_description_hi", "recommendation_metadata_json"]
        invalid_buffer = io.StringIO()
        writer = csv.DictWriter(invalid_buffer, fieldnames=header)
        writer.writeheader()
        writer.writerow({
            "template_code": template.code,
            "crop_code": "WRONG_CROP",
            "season_code": template.season_code,
            "propagation_type_code": template.propagation_type_code or "",
            "version_number": "csv-validation-regression",
            "version_status": "DRAFT",
            "stage_order": "1",
            "stage_code": "BAD STAGE!",
            "stage_name_en": "Bad Stage",
            "duration_days": "-1",
            "farmer_actions_json": "not-json",
            "typical_inputs_json": "[]",
            "key_observations_json": "[]",
            "recommendation_sort_order": "1",
            "recommendation_day_offset": "0",
            "activity_type": "FERTILIZER",
            "input_code": "NO_SUCH_INPUT",
            "input_name": "Bad Input",
            "is_critical": "maybe",
            "recommendation_metadata_json": "[]",
        })
        invalid = upload_workflow_csv(client, draft_id, invalid_buffer.getvalue())
        check(invalid.status_code == 200, "invalid workflow CSV returns validation report", invalid.text[:500])
        invalid_report = invalid.json()
        check(invalid_report["can_apply"] is False, "invalid workflow CSV cannot apply")
        error_codes = {error["code"] for row in invalid_report["rows"] for error in row["errors"]}
        expected = {"CROP_MISMATCH", "INVALID_STAGE_CODE", "INVALID_INTEGER", "INVALID_JSON", "UNKNOWN_INPUT_CODE", "INVALID_BOOLEAN", "INVALID_JSON_TYPE"}
        check(expected.issubset(error_codes), "invalid workflow CSV reports expected diagnostics", sorted(error_codes))

        invalid_apply = apply_workflow_csv(client, draft_id, invalid_buffer.getvalue(), reason="Regression invalid apply")
        check(invalid_apply.status_code == 200, "invalid workflow CSV apply returns validation report", invalid_apply.text[:500])
        check(invalid_apply.json()["can_apply"] is False, "invalid workflow CSV apply does not mutate draft")

        print("=" * 72)
        print("Workflow CSV draft validation validated")
        print("=" * 72)
    finally:
        delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    main()
