"""Regression for backend-owned soil type profile option contract."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.farmer.soil_profile import SoilProfile
from app.modules.master_data.models.crop import Crop, CropCategory


def now():
    return datetime.now(timezone.utc)


def check(condition, label, payload=None):
    if not condition:
        print(f"  FAIL {label}")
        if payload is not None:
            print(f"       {payload}")
        raise AssertionError(label)
    print(f"  PASS {label}")
    if payload is not None:
        print(f"       {payload}")


def main():
    print("=" * 72)
    print("PROFILE SOIL TYPE OPTION CONTRACT REGRESSION")
    print("=" * 72)

    tenant_id = f"profile-soil-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    crop_category_id = uuid.uuid4()
    crop_id = uuid.uuid4()
    test_crop_code = "PROFILE_TEST_RICE"

    db = SessionLocal()
    try:
        category = db.query(CropCategory).filter(CropCategory.code == "PROFILE_OPTION_TEST").first()
        if category is None:
            category = CropCategory(
                id=crop_category_id,
                code="PROFILE_OPTION_TEST",
                canonical_name="Profile Option Test Crops",
                created_at=now(),
                updated_at=now(),
            )
            db.add(category)
            db.flush()
        crop = db.query(Crop).filter(Crop.code == test_crop_code).first()
        if crop is None:
            db.add(Crop(
                id=crop_id,
                code=test_crop_code,
                category_id=category.id,
                canonical_name="Profile Test Rice",
                suitable_seasons=["KHARIF"],
                suitable_soil_types=["ALLUVIAL"],
                created_at=now(),
                updated_at=now(),
            ))
            db.flush()
        db.add(Tenant(
            id=tenant_id,
            name="Profile Soil Option Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Profile Soil Option Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            status="ACTIVE",
            geography_scope={},
            crop_scope=[test_crop_code],
            config={
                "profile_options": {
                    "overrides": {
                        "soil_types": {
                            "version": "project-soil-types.v1",
                            "title": {"en": "Project Soil Types"},
                            "options": [
                                {"value": "ALLUVIAL", "label": {"en": "Alluvial only"}}
                            ],
                            "metadata": {"reason": "regression"},
                        }
                    }
                }
            },
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9186{uuid.uuid4().int % 100000000:08d}",
            display_name="Soil Option Farmer",
            village_name_manual="Soil Village",
            language_preference="hi",
            total_land_unit="ACRE",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(actor_id)}

    options = client.get(f"/api/v1/forms/options/soil_types?project_id={project_id}", headers=headers)
    check(options.status_code == 200, "Project soil type option set returns 200", options.text)
    option_body = options.json()
    check(option_body["option_set"] == "soil_types", "Soil type option set key stable")
    check(option_body["version"] == "project-soil-types.v1", "Project soil type override version applied")
    check([row["value"] for row in option_body["options"]] == ["ALLUVIAL"], "Project soil type override narrows choices")
    check(option_body["metadata"]["source"] == "project", "Soil type option source is project")

    form = client.get("/api/v1/forms/soil_profile", headers=headers)
    check(form.status_code == 200, "Soil profile form returns 200", form.text)
    soil_type_field = next(row for row in form.json()["fields"] if row["id"] == "soil_type_code")
    check(soil_type_field["source"] == "profile_options.soil_types", "Soil profile form points to backend soil type options")

    parcel_bad = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": str(farmer_id),
        "village_name_manual": "Soil Village",
        "reported_area": 1.2,
        "reported_area_unit": "ACRE",
        "soil_type_code": "BLACK_COTTON",
    })
    check(parcel_bad.status_code == 400, "Parcel rejects soil type outside project option set", parcel_bad.text)

    parcel_bad_crop = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": str(farmer_id),
        "village_name_manual": "Soil Village",
        "reported_area": 1.2,
        "reported_area_unit": "ACRE",
        "soil_type_code": "ALLUVIAL",
        "current_crop_code": "NOT_A_CROP",
    })
    check(parcel_bad_crop.status_code == 400, "Parcel rejects crop outside backend crop catalog", parcel_bad_crop.text)

    parcel_bad_season = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": str(farmer_id),
        "village_name_manual": "Soil Village",
        "reported_area": 1.2,
        "reported_area_unit": "ACRE",
        "soil_type_code": "ALLUVIAL",
        "crops_by_season": {"MONSOON": [test_crop_code]},
    })
    check(parcel_bad_season.status_code == 400, "Parcel rejects season outside backend season options", parcel_bad_season.text)

    parcel_good = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": str(farmer_id),
        "village_name_manual": "Soil Village",
        "reported_area": 1.2,
        "reported_area_unit": "ACRE",
        "soil_type_code": "ALLUVIAL",
        "current_crop_code": test_crop_code,
        "crops_by_season": {"KHARIF": [test_crop_code]},
    })
    check(parcel_good.status_code == 201, "Parcel accepts backend crop catalog and season options", parcel_good.text)
    parcel_id = parcel_good.json()["id"]

    parcel_bad_patch_crop = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={"current_crop_code": "NOT_A_CROP"})
    check(parcel_bad_patch_crop.status_code == 400, "Parcel update rejects crop outside backend crop catalog", parcel_bad_patch_crop.text)

    parcel_bad_patch_season = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={"crops_by_season": {"MONSOON": [test_crop_code]}})
    check(parcel_bad_patch_season.status_code == 400, "Parcel update rejects season outside backend season options", parcel_bad_patch_season.text)

    soil_bad = client.post("/api/v1/soil-profiles", headers=headers, json={
        "farmer_id": str(farmer_id),
        "parcel_id": parcel_id,
        "soil_type_code": "BLACK_COTTON",
        "data_source": "MANUAL",
    })
    check(soil_bad.status_code == 400, "Soil profile rejects soil type outside project option set", soil_bad.text)

    soil_good = client.post("/api/v1/soil-profiles", headers=headers, json={
        "farmer_id": str(farmer_id),
        "parcel_id": parcel_id,
        "soil_type_code": "ALLUVIAL",
        "soil_texture": "LOAM",
        "soil_color": "BROWN",
        "data_source": "MANUAL",
    })
    check(soil_good.status_code == 201, "Soil profile accepts project soil type option", soil_good.text)

    db = SessionLocal()
    try:
        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Profile soil type option contract validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
