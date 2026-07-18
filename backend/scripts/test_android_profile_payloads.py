"""Regression for Android-aligned farmer/parcel/soil profile payloads."""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.farmer.soil_profile import SoilProfile


client = TestClient(app)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("ANDROID PROFILE PAYLOAD REGRESSION")
    print("=" * 72)

    tenant_id = f"android-profile-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Android Profile Payload Tenant",
            type="ENTERPRISE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
    finally:
        db.close()

    print("\n[1] Farmer payload aliases")
    farmer_response = client.post("/api/v1/farmers", headers=headers, json={
        "mobile_number": f"+9198{uuid.uuid4().int % 100000000:08d}",
        "village_name_manual": "Android Profile Village",
        "pin_code": "560001",
        "display_name": "Android Payload Farmer",
        "father_name": "Android Payload Father",
        "aadhaar_number": "123456789012",
        "language_preference": "kn",
        "assistance_mode": "DEALER_ASSISTED",
    })
    check(farmer_response.status_code == 201, "Android farmer payload creates farmer", farmer_response.text)
    farmer = farmer_response.json()
    farmer_id = farmer["id"]
    check(farmer["pin_code"] == "560001", "Farmer response returns pin_code")

    db = SessionLocal()
    try:
        stored_farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(farmer_id), Farmer.tenant_id == tenant_id).first()
        check(stored_farmer is not None, "Farmer row stored")
        check(stored_farmer.pin_code == "560001", "Farmer PIN code stored")
        check(stored_farmer.enrollment_method == "ASSISTED", "Android assistance_mode normalized to enrollment_method")
    finally:
        db.close()

    print("\n[2] Parcel seasonal crop payload")
    parcel_response = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "reported_area": 2.5,
        "reported_area_unit": "ACRE",
        "ownership_type": "SHARECROP",
        "sharecrop_percentage": 40,
        "irrigation_source": "PURCHASED_WATER",
        "crops_by_season": {"KHARIF": ["RICE"], "RABI": ["WHEAT"], "ZAID": []},
    })
    check(parcel_response.status_code == 201, "Android parcel payload creates parcel", parcel_response.text)
    parcel = parcel_response.json()
    parcel_id = parcel["id"]

    db = SessionLocal()
    try:
        stored_parcel = db.query(Parcel).filter(Parcel.id == uuid.UUID(parcel_id), Parcel.tenant_id == tenant_id).first()
        check(stored_parcel is not None, "Parcel row stored")
        check(stored_parcel.sharecrop_percentage == 40, "Sharecrop percentage stored")
        check(stored_parcel.irrigation_source == "PURCHASED_WATER", "Configurable irrigation value stored")
        check((stored_parcel.crops_by_season or {}).get("KHARIF") == ["RICE"], "Seasonal crop payload stored")
    finally:
        db.close()

    print("\n[3] Soil boron_b alias")
    soil_response = client.post("/api/v1/soil-profiles", headers=headers, json={
        "parcel_id": parcel_id,
        "farmer_id": farmer_id,
        "soil_texture": "LOAM",
        "soil_color": "BROWN",
        "ph": 7.1,
        "boron_b": 0.42,
        "data_source": "SHC_CARD",
        "shc_card_number": "SHC-ANDROID-001",
    })
    check(soil_response.status_code == 201, "Android soil payload creates soil profile", soil_response.text)
    soil = soil_response.json()
    check(float(soil["boron_b"]) == 0.42, "Soil response returns boron_b alias")

    db = SessionLocal()
    try:
        stored_soil = db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).first()
        check(stored_soil is not None, "Soil profile row stored")
        check(float(stored_soil.boron_bo) == 0.42, "Android boron_b stored as backend boron_bo")

        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Android profile payloads validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
