"""Focused regression for enrollment-report parcel derivation."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, Project, Tenant
from app.modules.workflow.reports_api import _project_enrollment_report_rows


def now():
    return datetime.now(timezone.utc)


def project(project_id, tenant_id, name):
    return Project(
        id=project_id,
        tenant_id=tenant_id,
        name=name,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
        status="ACTIVE",
        crop_scope=["RICE"],
        geography_scope={},
        created_at=now(),
        updated_at=now(),
    )


def parcel(parcel_id, tenant_id, farmer_id, project_id, survey, status="ACTIVE"):
    return Parcel(
        id=parcel_id,
        tenant_id=tenant_id,
        farmer_id=farmer_id,
        project_id=project_id,
        survey_number=survey,
        reported_area=1,
        reported_area_unit="ACRE",
        ownership_type="OWNED",
        status=status,
        created_at=now(),
        updated_at=now(),
    )


def main():
    tenant_id = f"derived-report-{uuid.uuid4().hex[:12]}"
    project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    derived_id = uuid.uuid4()
    explicit_legacy_id = uuid.uuid4()
    cross_project_id = uuid.uuid4()
    archived_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Derived Report Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()
        db.add_all([
            project(project_id, tenant_id, "Derived Parcel Project"),
            project(other_project_id, tenant_id, "Other Parcel Project"),
        ])
        db.flush()
        db.add(
            Farmer(
                id=farmer_id,
                tenant_id=tenant_id,
                project_id=project_id,
                mobile_number=f"+9197{uuid.uuid4().int % 100000000:08d}",
                display_name="Derived Parcel Farmer",
                village_name_manual="Regression Village",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add_all([
            parcel(derived_id, tenant_id, farmer_id, project_id, "DERIVED"),
            parcel(explicit_legacy_id, tenant_id, farmer_id, None, "EXPLICIT"),
            parcel(cross_project_id, tenant_id, farmer_id, other_project_id, "CROSS-PROJECT"),
            parcel(archived_id, tenant_id, farmer_id, project_id, "ARCHIVED", status="ARCHIVED"),
            FarmerProjectEnrollment(
                id=enrollment_id,
                tenant_id=tenant_id,
                farmer_id=farmer_id,
                project_id=project_id,
                enrollment_method="SYNC_MATERIALIZED",
                enrollment_source="derived_parcel_regression",
                status="ACTIVE",
                parcel_ids=[str(explicit_legacy_id), str(derived_id)],
                assigned_user_ids=[],
                metadata_={},
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.flush()

        rows = _project_enrollment_report_rows(
            db=db,
            tenant_id=tenant_id,
            project_id=project_id,
            farmer_id=farmer_id,
            status="ACTIVE",
            enrollment_source=None,
            q=None,
            limit=10,
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == str(enrollment_id)
        assert row["parcel_ids"] == [str(explicit_legacy_id), str(derived_id)]
        assert row["parcel_labels"] == ["EXPLICIT", "DERIVED"]
        assert row["parcel_ids"].count(str(derived_id)) == 1
        assert str(cross_project_id) not in row["parcel_ids"]
        assert str(archived_id) not in row["parcel_ids"]
        print("PASS project enrollment derived parcel regression: 7 assertions")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
