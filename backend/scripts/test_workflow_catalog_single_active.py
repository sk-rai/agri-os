"""Regression for single active Android workflow catalog selection."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
TENANT_ID = "default"


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    icon = f"{GREEN}?{RESET}" if condition else f"{RED}?{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def get_rice_template_and_version(db):
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
    check(template is not None, "Rice workflow template exists")
    version = db.query(WorkflowTemplateVersion).filter(
        WorkflowTemplateVersion.template_id == template.id,
        WorkflowTemplateVersion.status == "PUBLISHED",
        WorkflowTemplateVersion.is_active == True,
    ).order_by(
        WorkflowTemplateVersion.published_at.desc().nullslast(),
        WorkflowTemplateVersion.created_at.desc(),
    ).first()
    check(version is not None, "Rice workflow has a published version")
    return template, version


def rice_workflows(client, headers):
    response = client.get(
        "/api/v1/workflow-catalog/enabled-crop-workflows?crop_code=RICE&season=KHARIF",
        headers=headers,
    )
    check(response.status_code == 200, "Rice/Kharif catalog returns 200", f"Status: {response.status_code}")
    workflows = [item for item in response.json()["workflows"] if item["crop_code"] == "RICE" and item["season_code"] == "KHARIF"]
    return workflows


def cleanup(db, version_id):
    db.rollback()
    if version_id:
        db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == version_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW CATALOG SINGLE ACTIVE VERSION REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    headers = {"X-Tenant-ID": TENANT_ID}
    db = SessionLocal()
    test_version_id = uuid.uuid4()
    try:
        template, current_version = get_rice_template_and_version(db)
        baseline = rice_workflows(client, headers)
        check(len(baseline) == 1, "Baseline Android catalog exposes one Rice/Kharif workflow", baseline)
        check(
            baseline[0]["workflow_template_version_id"] == str(current_version.id),
            "Baseline catalog uses current published Rice version",
        )

        published_at = now() + timedelta(minutes=5)
        test_version = WorkflowTemplateVersion(
            id=test_version_id,
            template_id=template.id,
            version_number=f"catalog-single-active-{test_version_id.hex[:8]}",
            status="PUBLISHED",
            effective_from=current_version.effective_from,
            effective_to=current_version.effective_to,
            total_duration_days=current_version.total_duration_days,
            schema_version=current_version.schema_version,
            metadata_={"test_marker": "catalog_single_active"},
            published_at=published_at,
            created_at=published_at,
            updated_at=published_at,
        )
        db.add(test_version)
        db.commit()

        with_newer_version = rice_workflows(client, headers)
        check(len(with_newer_version) == 1, "Android catalog still exposes exactly one Rice/Kharif workflow")
        check(
            with_newer_version[0]["workflow_template_version_id"] == str(test_version_id),
            "Android catalog selects newest published version",
            with_newer_version[0],
        )
        check(
            with_newer_version[0]["catalog_selection_policy"] == "LATEST_PUBLISHED_PER_CROP_SEASON",
            "Catalog response documents the selection policy",
        )

        test_version = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == test_version_id).first()
        test_version.status = "ARCHIVED"
        test_version.updated_at = now()
        db.commit()

        after_archive = rice_workflows(client, headers)
        check(len(after_archive) == 1, "Archived newer version is hidden from Android catalog")
        check(
            after_archive[0]["workflow_template_version_id"] == str(current_version.id),
            "Android catalog falls back to published current version after archive",
        )

        archived_preview = client.get(
            f"/api/v1/workflow-catalog/workflow-preview/{test_version_id}",
            headers=headers,
        )
        check(archived_preview.status_code == 200, "Archived version remains previewable by explicit ID", f"Status: {archived_preview.status_code}")
        check(
            archived_preview.json()["workflow_template_version_id"] == str(test_version_id),
            "Archived preview returns requested historical version",
        )
    finally:
        cleanup(db, test_version_id)
        db.close()

    print("\nAll workflow catalog single-active checks passed.")


if __name__ == "__main__":
    main()