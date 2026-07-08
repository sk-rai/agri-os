"""Regression for safe publishing when existing cycles are pinned to a workflow version."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateRecommendation,
    WorkflowTemplateStage,
    WorkflowTemplateVersion,
)

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


def ensure_default_tenant(db):
    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        db.add(Tenant(id=TENANT_ID, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()


def get_rice_workflow(db):
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
    check(version is not None, "Rice workflow has a current published version")
    return template, version


def cleanup(db, *, farmer_id, parcel_id, project_id, cycle_id, draft_version_id, previous_snapshots):
    db.rollback()
    if cycle_id:
        db.query(CropActivity).filter(CropActivity.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.crop_cycle_id == cycle_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.id == cycle_id).delete(synchronize_session=False)
    if draft_version_id:
        stage_ids = [row.id for row in db.query(WorkflowTemplateStage.id).filter(WorkflowTemplateStage.template_version_id == draft_version_id).all()]
        if stage_ids:
            db.query(WorkflowTemplateRecommendation).filter(WorkflowTemplateRecommendation.template_stage_id.in_(stage_ids)).delete(synchronize_session=False)
            db.query(WorkflowTemplateStage).filter(WorkflowTemplateStage.id.in_(stage_ids)).delete(synchronize_session=False)
        db.query(WorkflowTemplateAuditEvent).filter(WorkflowTemplateAuditEvent.template_version_id == draft_version_id).delete(synchronize_session=False)
        db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == draft_version_id).delete(synchronize_session=False)
    for version_id, snapshot in previous_snapshots.items():
        version = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == version_id).first()
        if version:
            version.status = snapshot["status"]
            version.effective_to = snapshot["effective_to"]
            version.metadata_ = snapshot["metadata"]
            version.updated_at = now()
    db.query(Parcel).filter(Parcel.id == parcel_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.id == farmer_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW PUBLISH SAFEGUARD REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    actor_id = str(uuid.uuid4())
    headers = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": actor_id}
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    project_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    draft_version_id = None
    previous_snapshots = {}

    db = SessionLocal()
    try:
        ensure_default_tenant(db)
        template, published_version = get_rice_workflow(db)
        previous_versions = db.query(WorkflowTemplateVersion).filter(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        ).all()
        previous_snapshots = {
            version.id: {
                "status": version.status,
                "effective_to": version.effective_to,
                "metadata": dict(version.metadata_ or {}),
            }
            for version in previous_versions
        }

        db.add(Project(
            id=project_id,
            tenant_id=TENANT_ID,
            name="Publish Safeguard Test Project",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=TENANT_ID,
            project_id=project_id,
            mobile_number="997" + str(farmer_id.int)[-7:],
            village_name_manual="Publish Safeguard Village",
            primary_crop_code="RICE",
            display_name="Publish Safeguard Test Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Parcel(
            id=parcel_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            project_id=project_id,
            village_name_manual="Publish Safeguard Village",
            reported_area=1,
            reported_area_unit="ACRE",
            survey_number="PUBLISH-SAFE-" + str(parcel_id)[:8],
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(CropCycle(
            id=cycle_id,
            tenant_id=TENANT_ID,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            project_id=project_id,
            crop_code="RICE",
            season_code="KHARIF",
            lifecycle_template_id=template.lifecycle_template_id,
            workflow_template_version_id=published_version.id,
            planned_sowing_date=date(2027, 7, 15),
            status="PLANNED",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()

        clone = client.post(
            f"/api/v1/workflow-catalog/templates/{template.id}/versions/{published_version.id}/clone-draft",
            headers=headers,
            json={},
        )
        check(clone.status_code == 200, "Clone draft returns 200", f"Status: {clone.status_code}, Body: {clone.text[:300]}")
        draft_version_id = uuid.UUID(clone.json()["draft_version_id"])

        impact = client.get(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/publish-impact?archive_previous=true",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(impact.status_code == 200, "Publish impact endpoint returns 200", f"Status: {impact.status_code}")
        impact_payload = impact.json()
        current_row = next((row for row in impact_payload["impacted_published_versions"] if row["workflow_template_version_id"] == str(published_version.id)), None)
        check(current_row is not None, "Impact includes current published version")
        check(current_row["pinned_cycle_count"] >= 1, "Impact reports pinned cycles on current version", current_row)
        check(current_row["retention_policy"] == "ARCHIVED_VERSIONS_REMAIN_RENDERABLE_FOR_PINNED_CYCLES", "Impact documents retention policy")

        publish = client.post(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/publish",
            headers=headers,
            json={"archive_previous": True},
        )
        check(publish.status_code == 200, "Publish draft returns 200", f"Status: {publish.status_code}, Body: {publish.text[:300]}")
        publish_payload = publish.json()
        check(publish_payload.get("publish_impact", {}).get("counts", {}).get("pinned_cycles_impacted", 0) >= 1, "Publish response includes pinned-cycle impact")

        db.expire_all()
        archived_previous = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == published_version.id).first()
        check(archived_previous.status == "ARCHIVED", "Previous published version is archived for new catalog selection")
        check((archived_previous.metadata_ or {}).get("archived_for_new_catalog_only") is True, "Archived version metadata marks catalog-only archive")

        archived_preview = client.get(
            f"/api/v1/workflow-catalog/workflow-preview/{published_version.id}",
            headers={"X-Tenant-ID": TENANT_ID},
        )
        check(archived_preview.status_code == 200, "Archived pinned version remains previewable", f"Status: {archived_preview.status_code}")
        check(archived_preview.json()["status"] == "ARCHIVED", "Archived preview reports ARCHIVED status")
    finally:
        cleanup(
            db,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            project_id=project_id,
            cycle_id=cycle_id,
            draft_version_id=draft_version_id,
            previous_snapshots=previous_snapshots,
        )
        db.close()

    print("\n" + "=" * 72)
    print("🟢 Workflow publish safeguards validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
