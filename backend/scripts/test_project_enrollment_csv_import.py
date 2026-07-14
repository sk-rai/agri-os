"""Regression for project-led farmer enrollment CSV import lifecycle."""

from datetime import date, datetime, timezone
from pathlib import Path
import io
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, FarmerProjectEnrollmentImportBatch, Project, Tenant
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
    print("PROJECT ENROLLMENT CSV IMPORT REGRESSION")
    print("=" * 72)

    tenant_id = "default"
    project_id = uuid.uuid4()
    existing_farmer_id = uuid.uuid4()
    existing_mobile = f"+9195{uuid.uuid4().int % 100000000:08d}"
    new_mobile_10 = f"94{uuid.uuid4().int % 100000000:08d}"
    admin = None

    db = SessionLocal()
    try:
        if not db.query(Tenant).filter(Tenant.id == tenant_id).first():
            db.add(Tenant(id=tenant_id, name="Default", type="ENTERPRISE", created_at=now(), updated_at=now()))
            db.flush()
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Bulk Enrollment Regression Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        )
        existing_farmer = Farmer(
            id=existing_farmer_id,
            tenant_id=tenant_id,
            mobile_number=existing_mobile,
            display_name="Existing Bulk Farmer",
            village_name_manual="Old Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([project, existing_farmer])
        admin, headers = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=tenant_id)
        db.commit()

        client = TestClient(app)
        template = client.get(f"/api/v1/projects/{project_id}/farmer-enrollments/csv/template", headers=headers)
        check(template.status_code == 200, "CSV template returns 200", template.text[:200])
        check("mobile_number" in template.text and "display_name" in template.text, "Template includes required columns")

        csv_text = "\n".join([
            "mobile_number,display_name,father_name,village_name_manual,language_preference,primary_crop_code,enrollment_status,enrollment_source,notes,metadata_json",
            f"{existing_mobile},Existing Farmer Updated,Parent One,Updated Village,hi,RICE,ACTIVE,bulk_regression,Existing row,{{}}",
            f"{new_mobile_10},New Bulk Farmer,Parent Two,New Village,en,SUGARCANE,ACTIVE,bulk_regression,New row,{{}}",
        ])
        files = {"file": ("enrollments.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        validate = client.post(f"/api/v1/projects/{project_id}/farmer-enrollments/csv/validate", headers=headers, files=files)
        check(validate.status_code == 200, "CSV validate returns 200", validate.text[:500])
        batch = validate.json()
        check(batch["status"] == "VALIDATED", "Valid CSV creates VALIDATED batch")
        check(batch["can_apply"] is True, "Validated batch can apply")
        check(batch["report"]["summary"]["update"] == 1, "Validation detects existing farmer update")
        check(batch["report"]["summary"]["create"] == 1, "Validation detects new farmer create")
        batch_id = batch["batch_id"]

        history = client.get(f"/api/v1/projects/{project_id}/farmer-enrollments/csv/imports", headers=headers)
        check(history.status_code == 200, "Import history returns 200", history.text[:300])
        check(any(item["batch_id"] == batch_id for item in history.json()["imports"]), "Import history includes batch")

        apply = client.post(
            f"/api/v1/projects/{project_id}/farmer-enrollments/csv/imports/{batch_id}/apply",
            headers=headers,
            json={"reason": "Bulk enrollment regression apply"},
        )
        check(apply.status_code == 200, "CSV apply returns 200", apply.text[:500])
        applied = apply.json()
        check(applied["status"] == "APPLIED", "Batch is marked APPLIED")
        counts = applied["report"]["applied_counts"]
        check(counts["farmers_created"] == 1, "Apply creates one farmer")
        check(counts["farmers_updated"] == 1, "Apply updates one farmer")
        check(counts["enrollments_created"] == 2, "Apply creates two memberships")

        db.expire_all()
        new_mobile = f"+91{new_mobile_10}"
        existing = db.query(Farmer).filter(Farmer.id == existing_farmer_id).first()
        new_farmer = db.query(Farmer).filter(Farmer.tenant_id == tenant_id, Farmer.mobile_number == new_mobile).first()
        check(existing.display_name == "Existing Farmer Updated", "Existing farmer was updated")
        check(new_farmer is not None, "New farmer was created")
        memberships = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.project_id == project_id,
            FarmerProjectEnrollment.enrollment_batch_id == batch_id,
        ).all()
        check(len(memberships) == 2, "Two memberships are linked to import batch")

        second_apply = client.post(
            f"/api/v1/projects/{project_id}/farmer-enrollments/csv/imports/{batch_id}/apply",
            headers=headers,
            json={"reason": "Should be blocked"},
        )
        check(second_apply.status_code == 409, "Applied batch cannot be applied twice", second_apply.text)
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.project_id == project_id).delete(synchronize_session=False)
            cleanup.query(FarmerProjectEnrollmentImportBatch).filter(FarmerProjectEnrollmentImportBatch.project_id == project_id).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(Farmer.tenant_id == tenant_id, Farmer.mobile_number.like("+9194%")).delete(synchronize_session=False)
            cleanup.query(Farmer).filter(Farmer.id == existing_farmer_id).delete(synchronize_session=False)
            cleanup.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
            cleanup.commit()
            if admin:
                delete_test_admin(cleanup, admin.id)
        finally:
            cleanup.close()
        db.close()

    print("=" * 72)
    print("Project enrollment CSV import validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
