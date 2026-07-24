"""Regression for runtime DigiPin persistence on farmer home and parcel centroid."""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.master_data.digipin import validate_digipin


client = TestClient(app)
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(condition, label, detail=""):
    print(f"  {PASS if condition else FAIL} {label}")
    if detail:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def mobile():
    return "+9194" + f"{uuid.uuid4().int % 100000000:08d}"


def main():
    print("=" * 72)
    print("DIGIPIN FARMER/PARCEL FIELD REGRESSION")
    print("=" * 72)

    tenant_id = f"digipin-runtime-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            name="DigiPin Runtime Test Tenant",
            type="ENTERPRISE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
    finally:
        db.close()

    try:
        farmer_with_gps = client.post("/api/v1/farmers", headers=headers, json={
            "mobile_number": mobile(),
            "display_name": "DigiPin GPS Farmer",
            "village_name_manual": "DigiPin Village",
            "pin_code": "560001",
            "total_land_unit": "ACRE",
            "enrollment_gps_lat": 28.6139,
            "enrollment_gps_lng": 77.2090,
        })
        check(farmer_with_gps.status_code == 201, "Farmer with GPS create returns 201", farmer_with_gps.text)
        farmer_with_gps_body = farmer_with_gps.json()
        farmer_id = farmer_with_gps_body["id"]
        check(validate_digipin(farmer_with_gps_body["home_digipin"]), "Farmer response includes valid home DigiPin", farmer_with_gps_body)
        check(farmer_with_gps_body["pin_code"] == "560001", "PIN code remains separate from DigiPin")

        farmer_without_gps = client.post("/api/v1/farmers", headers=headers, json={
            "mobile_number": mobile(),
            "display_name": "DigiPin Null Farmer",
            "village_name_manual": "DigiPin Village",
            "pin_code": "560001",
            "total_land_unit": "ACRE",
        })
        check(farmer_without_gps.status_code == 201, "Farmer without GPS create returns 201", farmer_without_gps.text)
        farmer_without_gps_body = farmer_without_gps.json()
        farmer_without_gps_id = farmer_without_gps_body["id"]
        check(farmer_without_gps_body["home_digipin"] is None, "Farmer without GPS has null home DigiPin", farmer_without_gps_body)

        patched_farmer = client.patch(f"/api/v1/farmers/{farmer_without_gps_id}", headers=headers, json={
            "enrollment_gps_lat": 12.9716,
            "enrollment_gps_lng": 77.5946,
        })
        check(patched_farmer.status_code == 200, "Farmer GPS update returns 200", patched_farmer.text)
        check(validate_digipin(patched_farmer.json()["home_digipin"]), "Farmer GPS update computes home DigiPin", patched_farmer.json())

        parcel_with_centroid = client.post("/api/v1/parcels", headers=headers, json={
            "farmer_id": farmer_id,
            "village_name_manual": "DigiPin Village",
            "pin_code": "560001",
            "reported_area": 1.25,
            "reported_area_unit": "ACRE",
            "ownership_type": "OWNED",
            "centroid_lat": 28.6140,
            "centroid_lng": 77.2091,
        })
        check(parcel_with_centroid.status_code == 201, "Parcel with centroid create returns 201", parcel_with_centroid.text)
        parcel_with_centroid_body = parcel_with_centroid.json()
        check(validate_digipin(parcel_with_centroid_body["centroid_digipin"]), "Parcel response includes valid centroid DigiPin", parcel_with_centroid_body)

        parcel_without_centroid = client.post("/api/v1/parcels", headers=headers, json={
            "farmer_id": farmer_id,
            "village_name_manual": "DigiPin Village",
            "pin_code": "560001",
            "reported_area": 0.75,
            "reported_area_unit": "ACRE",
            "ownership_type": "OWNED",
        })
        check(parcel_without_centroid.status_code == 201, "Parcel without centroid create returns 201", parcel_without_centroid.text)
        parcel_without_centroid_body = parcel_without_centroid.json()
        check(parcel_without_centroid_body["centroid_digipin"] is None, "Parcel without centroid has null DigiPin", parcel_without_centroid_body)

        geometry_update = client.patch(f"/api/v1/parcels/{parcel_without_centroid_body['id']}/geometry", headers=headers, json={
            "geometry_source": "PIN_DROP",
            "centroid_lat": 12.9716,
            "centroid_lng": 77.5946,
            "accuracy_meters": 10,
        })
        check(geometry_update.status_code == 200, "Parcel geometry update returns 200", geometry_update.text)
        check(validate_digipin(geometry_update.json()["centroid_digipin"]), "Parcel geometry update computes centroid DigiPin", geometry_update.json())

        db = SessionLocal()
        try:
            stored_farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(farmer_id), Farmer.tenant_id == tenant_id).first()
            stored_parcel = db.query(Parcel).filter(Parcel.id == uuid.UUID(parcel_with_centroid_body["id"]), Parcel.tenant_id == tenant_id).first()
            check(validate_digipin(stored_farmer.home_digipin), "Stored farmer home DigiPin validates")
            check(validate_digipin(stored_parcel.centroid_digipin), "Stored parcel centroid DigiPin validates")
        finally:
            db.close()

    finally:
        db = SessionLocal()
        try:
            db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    print("=" * 72)
    print("DigiPin farmer/parcel fields validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
