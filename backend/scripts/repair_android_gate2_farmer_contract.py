#!/usr/bin/env python3
"""Fail-closed repair for the reviewed Gate 2 farmer contract fields."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Parcel, ProjectRole
from app.modules.farmer.soil_profile import SoilEnrichmentSnapshot, SoilProfile
from app.modules.master_data import models as _master_data_models  # noqa: F401
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
USER_ID = uuid.UUID("192b6593-aee6-4b12-8ac6-7d3caeffabd6")
MOBILE = "+919900000002"
FARMER_ID = uuid.UUID("107d7261-ca96-4e95-bb1a-8eb837f3388b")
ENROLLMENT_ID = uuid.UUID("42495747-53ad-4e00-a0be-5fbfcaf904ea")
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-farmer-id")
    args = parser.parse_args()
    if args.apply:
        require(
            args.confirm_farmer_id == str(FARMER_ID),
            "Apply requires the exact reviewed --confirm-farmer-id.",
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == USER_ID).one()
        farmer = db.query(Farmer).filter(Farmer.id == FARMER_ID).one()
        enrollment = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.id == ENROLLMENT_ID
        ).one()

        require(user.mobile_number == MOBILE, "Reviewed user mobile changed.")
        require(user.tenant_id == TENANT_ID, "Reviewed user tenant changed.")
        require(user.role == "FARMER" and user.is_active is True, "Reviewed user state changed.")
        require(farmer.tenant_id == TENANT_ID, "Reviewed farmer tenant changed.")
        require(farmer.user_id == USER_ID, "Reviewed farmer/user linkage changed.")
        require(farmer.mobile_number == MOBILE, "Reviewed farmer mobile changed.")
        require(farmer.project_id == PROJECT_ID, "Reviewed farmer project changed.")
        require(farmer.status == "ACTIVE" and farmer.is_active is True, "Reviewed farmer state changed.")
        require(farmer.pin_code is None, "Farmer PIN no longer matches reviewed precondition.")
        require(farmer.enrollment_method == "ASSISTED", "Farmer enrollment method changed.")
        require(enrollment.tenant_id == TENANT_ID, "Reviewed enrollment tenant changed.")
        require(enrollment.farmer_id == FARMER_ID, "Reviewed enrollment farmer changed.")
        require(enrollment.project_id == PROJECT_ID, "Reviewed enrollment project changed.")
        require(enrollment.status == "ACTIVE" and enrollment.is_active is True, "Reviewed enrollment state changed.")
        require(enrollment.enrollment_method == "ASSISTED", "Enrollment method changed.")
        require(enrollment.enrollment_source == "ANDROID_SYNC_FARMER_CREATE", "Enrollment source changed.")
        require(not (enrollment.assigned_user_ids or []), "Reviewed enrollment gained assignments.")
        require(
            db.query(ProjectRole).filter(
                ProjectRole.project_id == PROJECT_ID,
                ProjectRole.user_id == USER_ID,
                ProjectRole.is_active == True,
            ).count() == 0,
            "Reviewed user gained a project role.",
        )

        counts = {
            "parcels": db.query(Parcel).filter(Parcel.farmer_id == FARMER_ID).count(),
            "soil_profiles": db.query(SoilProfile).filter(SoilProfile.farmer_id == FARMER_ID).count(),
            "enrichment_snapshots": db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.farmer_id == FARMER_ID).count(),
            "crop_cycles": db.query(CropCycle).filter(CropCycle.farmer_id == FARMER_ID).count(),
            "stages": db.query(CropStageInstance).filter(
                CropStageInstance.crop_cycle_id.in_(
                    db.query(CropCycle.id).filter(CropCycle.farmer_id == FARMER_ID)
                )
            ).count(),
            "activities": db.query(CropActivity).filter(CropActivity.farmer_id == FARMER_ID).count(),
        }
        require(all(value == 0 for value in counts.values()), "Operational child counts changed.")

        before = {
            "farmer_pin_present": farmer.pin_code is not None,
            "farmer_enrollment_method": farmer.enrollment_method,
            "project_enrollment_method": enrollment.enrollment_method,
        }
        after = {
            "farmer_pin_present": True,
            "farmer_enrollment_method": "SELF",
            "project_enrollment_method": "SELF",
        }
        if args.apply:
            farmer.pin_code = "560001"
            farmer.enrollment_method = "SELF"
            enrollment.enrollment_method = "SELF"
            db.commit()
        else:
            db.rollback()

        print({
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "farmer_id": str(FARMER_ID),
            "enrollment_id": str(ENROLLMENT_ID),
            "affected_rows": {"farmers": 1, "farmer_project_enrollments": 1},
            "operational_child_counts": counts,
            "before": before,
            "after": after,
            "historical_sync_or_audit_rows_modified": False,
        })
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
