"""Regression for DigiPin generation during offline sync materialization."""

import sys
import uuid
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


def main():
    print("=" * 72)
    print("SYNC DIGIPIN MATERIALIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"sync-digipin-{uuid.uuid4().hex[:8]}"
    actor_id = str(uuid.uuid4())
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": actor_id}

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Sync DigiPin Test Tenant", type="ENTERPRISE"))
        db.commit()
    finally:
        db.close()

    farmer_id = str(uuid.uuid4())
    farmer_event_id = str(uuid.uuid4())
    farmer_sync = client.post("/api/v1/sync/events", headers=headers, json={
        "events": [{
            "event_id": farmer_event_id,
            "entity_type": "farmer",
            "entity_id": farmer_id,
            "operation": "CREATE",
            "payload": {
                "mobile_number": "+919455555555",
                "display_name": "Sync DigiPin Farmer",
                "village_name_manual": "Sync DigiPin Village",
                "pin_code": "560001",
                "total_land_unit": "ACRE",
                "enrollment_gps_lat": 28.6139,
                "enrollment_gps_lng": 77.2090,
            },
            "version": 1,
        }]
    })
    check(farmer_sync.status_code == 200, "Farmer sync returns 200", farmer_sync.text)
    check(farmer_event_id in farmer_sync.json()["accepted"], "Farmer sync accepted", farmer_sync.json())

    parcel_id = str(uuid.uuid4())
    parcel_event_id = str(uuid.uuid4())
    parcel_sync = client.post("/api/v1/sync/events", headers=headers, json={
        "events": [{
            "event_id": parcel_event_id,
            "entity_type": "parcel",
            "entity_id": parcel_id,
            "operation": "CREATE",
            "payload": {
                "farmer_id": farmer_id,
                "village_name_manual": "Sync DigiPin Village",
                "pin_code": "560001",
                "reported_area": 1.25,
                "reported_area_unit": "ACRE",
                "geometry_source": "PIN_DROP",
                "centroid_lat": 28.6140,
                "centroid_lng": 77.2091,
            },
            "version": 1,
            "dependency_ids": [farmer_event_id],
        }]
    })
    check(parcel_sync.status_code == 200, "Parcel sync returns 200", parcel_sync.text)
    check(parcel_event_id in parcel_sync.json()["accepted"], "Parcel sync accepted", parcel_sync.json())

    geometry_event_id = str(uuid.uuid4())
    geometry_sync = client.post("/api/v1/sync/events", headers=headers, json={
        "events": [{
            "event_id": geometry_event_id,
            "entity_type": "parcel_geometry",
            "entity_id": parcel_id,
            "operation": "UPDATE",
            "payload": {
                "geometry_source": "PIN_DROP",
                "centroid_lat": 12.9716,
                "centroid_lng": 77.5946,
                "accuracy_meters": 9.5,
            },
            "version": 2,
            "dependency_ids": [parcel_event_id],
        }]
    })
    check(geometry_sync.status_code == 200, "Parcel geometry sync returns 200", geometry_sync.text)
    check(geometry_event_id in geometry_sync.json()["accepted"], "Parcel geometry sync accepted", geometry_sync.json())

    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(farmer_id), Farmer.tenant_id == tenant_id).first()
        parcel = db.query(Parcel).filter(Parcel.id == uuid.UUID(parcel_id), Parcel.tenant_id == tenant_id).first()
        check(farmer is not None, "Farmer materialized")
        check(parcel is not None, "Parcel materialized")
        check(validate_digipin(farmer.home_digipin), "Sync farmer home DigiPin validates", farmer.home_digipin)
        check(validate_digipin(parcel.centroid_digipin), "Sync parcel centroid DigiPin validates", parcel.centroid_digipin)
        check(parcel.centroid_digipin == "4P3JK852C9", "Geometry sync recomputes parcel DigiPin from latest centroid", parcel.centroid_digipin)
    finally:
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print("=" * 72)
    print("Sync DigiPin materialization validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
