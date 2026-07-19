"""Regression for Android-aligned farmer/parcel/soil profile payloads."""

import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.farmer.soil_profile import SoilEnrichmentSnapshot, SoilProfile


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

    invalid_farmer = client.post("/api/v1/farmers", headers=headers, json={
        "mobile_number": f"+9197{uuid.uuid4().int % 100000000:08d}",
        "village_name_manual": "Android Profile Village",
        "total_land_unit": "ANDROID_ONLY_UNIT",
    })
    check(invalid_farmer.status_code == 400, "Invalid farmer profile option is rejected", invalid_farmer.text)
    check(invalid_farmer.json()["detail"]["error"] == "INVALID_PROFILE_OPTION_VALUE", "Invalid farmer option returns structured error")

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

    invalid_parcel = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "reported_area": 1,
        "reported_area_unit": "ACRE",
        "ownership_type": "ANDROID_ONLY_OWNERSHIP",
    })
    check(invalid_parcel.status_code == 400, "Invalid parcel profile option is rejected", invalid_parcel.text)
    check(invalid_parcel.json()["detail"]["path"] == "ownership_type", "Invalid parcel option identifies field path")

    print("\n[2b] Project-effective parcel option override")
    project_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Android Profile Override Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={"profile_options": {"overrides": {"ownership_types": {"version": "project-owned-only", "title": {"en": "Project Ownership"}, "options": [{"value": "OWNED", "label": {"en": "Owned"}}]}}}},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.flush()
        stored_farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(farmer_id), Farmer.tenant_id == tenant_id).first()
        stored_farmer.project_id = project_id
        stored_farmer.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    project_invalid_parcel = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "reported_area": 1,
        "reported_area_unit": "ACRE",
        "ownership_type": "SHARECROP",
    })
    check(project_invalid_parcel.status_code == 400, "Project ownership override rejects default option", project_invalid_parcel.text)
    check(project_invalid_parcel.json()["detail"]["allowed_values"] == ["OWNED"], "Project option validation uses override values")

    project_valid_parcel = client.post("/api/v1/parcels", headers=headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "reported_area": 1,
        "reported_area_unit": "ACRE",
        "ownership_type": "OWNED",
    })
    check(project_valid_parcel.status_code == 201, "Project ownership override accepts allowed option", project_valid_parcel.text)
    project_parcel_id = project_valid_parcel.json()["id"]
    db = SessionLocal()
    try:
        stored_project_parcel = db.query(Parcel).filter(Parcel.id == uuid.UUID(project_parcel_id), Parcel.tenant_id == tenant_id).first()
        check(str(stored_project_parcel.project_id) == str(project_id), "Project context is stored on inferred parcel")
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

    invalid_soil = client.post("/api/v1/soil-profiles", headers=headers, json={
        "parcel_id": parcel_id,
        "farmer_id": farmer_id,
        "soil_texture": "ANDROID_ONLY_TEXTURE",
        "data_source": "MANUAL",
    })
    check(invalid_soil.status_code == 400, "Invalid soil profile option is rejected", invalid_soil.text)
    check(invalid_soil.json()["detail"]["option_set"] == "soil_textures", "Invalid soil option identifies option set")

    print("\n[4] Profile readiness includes backend soil enrichment snapshots")
    db = SessionLocal()
    try:
        db.add_all([
            SoilEnrichmentSnapshot(
                id=uuid.uuid4(), tenant_id=tenant_id, parcel_id=uuid.UUID(parcel_id), farmer_id=uuid.UUID(farmer_id),
                provider="SOILGRIDS", provider_dataset="soilgrids.v2.0", snapshot_type="BASELINE", status="AVAILABLE",
                depth_layer="0-5cm", resolution_meters=250, confidence="MODELLED", observed_at=datetime.now(timezone.utc), fetched_at=datetime.now(timezone.utc),
                ph=6.8, organic_carbon=1.2, nitrogen=0.18, normalized_values={"texture_class": "CLAY_LOAM"}, raw_payload={}, metadata_={},
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ),
            SoilEnrichmentSnapshot(
                id=uuid.uuid4(), tenant_id=tenant_id, parcel_id=uuid.UUID(parcel_id), farmer_id=uuid.UUID(farmer_id),
                provider="OPEN_METEO", provider_dataset="open-meteo.soil", snapshot_type="MOISTURE", status="AVAILABLE",
                depth_layer="9-27cm", resolution_meters=10000, confidence="FORECAST_MODEL", observed_at=datetime.now(timezone.utc), fetched_at=datetime.now(timezone.utc),
                surface_soil_moisture=0.22, root_zone_soil_moisture=0.31, normalized_values={}, raw_payload={}, metadata_={},
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ),
        ])
        db.commit()
    finally:
        db.close()

    readiness_response = client.get("/api/v1/farmers/profile-readiness", headers=headers)
    check(readiness_response.status_code == 200, "Profile readiness returns 200", readiness_response.text)
    readiness = readiness_response.json()
    readiness_row = next(row for row in readiness["farmers"] if row["farmer"]["id"] == farmer_id)
    enrichment = readiness_row["profile_completion"]["enrichment_readiness"]
    check(enrichment["has_soil_baseline_snapshot"] is True, "Readiness detects SoilGrids baseline snapshot")
    check(enrichment["has_soil_moisture_snapshot"] is True, "Readiness detects soil moisture snapshot")
    check(enrichment["soil_baseline_snapshot_count"] == 1, "Readiness counts baseline snapshots")
    check(enrichment["soil_moisture_snapshot_count"] == 1, "Readiness counts moisture snapshots")
    check(readiness["summary"]["soil_baseline_snapshot_available_count"] >= 1, "Readiness summary counts baseline availability")
    check(readiness["summary"]["soil_moisture_snapshot_available_count"] >= 1, "Readiness summary counts moisture availability")

    db = SessionLocal()
    try:
        stored_soil = db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).first()
        check(stored_soil is not None, "Soil profile row stored")
        check(float(stored_soil.boron_bo) == 0.42, "Android boron_b stored as backend boron_bo")

        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
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
