"""Regression for workflow CSV template/export endpoints."""

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


def parse_csv_response(response):
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    print("=" * 72)
    print("WORKFLOW CSV EXPORT REGRESSION")
    print("=" * 72)

    anonymous = TestClient(app)
    denied = anonymous.get("/api/v1/workflow-catalog/csv/workflows/export", headers={"X-Tenant-ID": "default"})
    check(denied.status_code == 401, "workflow CSV export requires admin authentication", denied.text)

    db = SessionLocal()
    admin, headers = create_test_admin(db)
    try:
        client = TestClient(app, headers=headers)

        template = client.get("/api/v1/workflow-catalog/csv/workflows/template")
        check(template.status_code == 200, "viewer can download workflow CSV template", template.text[:200])
        template_rows = parse_csv_response(template)
        check(len(template_rows) == 1, "template returns one sample row")
        required_columns = {"template_code", "crop_code", "season_code", "stage_code", "recommendation_day_offset", "input_name"}
        check(required_columns.issubset(template_rows[0].keys()), "template includes required workflow columns")

        published = client.get("/api/v1/workflow-catalog/csv/workflows/export")
        check(published.status_code == 200, "viewer can export published workflows", published.text[:200])
        rows = parse_csv_response(published)
        check(len(rows) > 0, "published workflow export returns rows")
        check(all(row["version_status"] == "PUBLISHED" for row in rows), "default export only includes published workflow versions")
        check(any(row["crop_code"] == "RICE" for row in rows), "published export includes Rice workflow rows")
        check(any(row["stage_code"] for row in rows), "export rows include stage codes")
        check(any(row["input_name"] for row in rows), "export rows include recommendation input names")

        rice = client.get("/api/v1/workflow-catalog/csv/workflows/export?crop_code=RICE&season_code=KHARIF")
        check(rice.status_code == 200, "filtered Rice/Kharif workflow export returns 200", rice.text[:200])
        rice_rows = parse_csv_response(rice)
        check(len(rice_rows) > 0, "filtered Rice/Kharif export returns rows")
        check(all(row["crop_code"] == "RICE" and row["season_code"] == "KHARIF" for row in rice_rows), "filtered export only includes Rice/Kharif rows")

        version = db.query(WorkflowTemplateVersion).join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id).filter(
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplate.crop_code == "RICE",
        ).first()
        check(version is not None, "published Rice workflow version exists for version filter")
        by_version = client.get(f"/api/v1/workflow-catalog/csv/workflows/export?template_version_id={version.id}&status=ALL")
        check(by_version.status_code == 200, "workflow export can filter by template version id", by_version.text[:200])
        version_rows = parse_csv_response(by_version)
        check(len(version_rows) > 0, "version-filtered export returns rows")
        check({row["version_number"] for row in version_rows} == {version.version_number}, "version-filtered export returns requested version")

        print("=" * 72)
        print("Workflow CSV export validated")
        print("=" * 72)
    finally:
        delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    main()
