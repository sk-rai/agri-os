"""Regression for provider-derived soil enrichment snapshots."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.farmer.soil_profile import SoilEnrichmentSnapshot


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
    print("SOIL ENRICHMENT SNAPSHOT REGRESSION")
    print("=" * 72)

    tenant_id = f"soil-enrich-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Soil Enrichment Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Soil Enrichment Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9187{uuid.uuid4().int % 100000000:08d}",
            display_name="Soil Enrichment Farmer",
            village_name_manual="Soil Grid Village",
            total_land_unit="ACRE",
            language_preference="hi",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            village_name_manual="Soil Grid Village",
            pin_code="560002",
            reported_area=1.4,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            centroid_lat=12.9716,
            centroid_lng=77.5946,
            geometry_source="PIN_DROP",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    headers = {"X-Tenant-ID": tenant_id}

    source_contract = client.get("/api/v1/soil-profiles/enrichments/source-contract", headers=headers)
    check(source_contract.status_code == 200, "Soil enrichment source contract returns 200", source_contract.text)
    source_payload = source_contract.json()
    check(source_payload["schema_version"] == "soil_enrichment_sources.v1", "Soil source contract schema stable")
    check("SOILGRIDS" in source_payload["sources"], "Source contract includes SoilGrids")
    check("SHC_SLUSI" in source_payload["sources"], "Source contract includes SHC/SLUSI visual baseline")
    check(source_payload["guidance"]["android_calls_provider_directly"] is False, "Source contract keeps provider calls backend-only")
    check(source_payload["guidance"]["slusi_scraping_allowed_by_default"] is False, "Source contract discourages default SLUSI scraping")

    soilgrids = client.post("/api/v1/soil-profiles/enrichments", headers=headers, json={
        "parcel_id": str(parcel_id),
        "provider": "SOILGRIDS",
        "provider_dataset": "soilgrids.v2.0",
        "snapshot_type": "BASELINE",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "depth_layer": "0-5cm",
        "resolution_meters": 250,
        "confidence": "MODELLED",
        "ph": 6.8,
        "organic_carbon": 1.23,
        "nitrogen": 0.18,
        "clay_percent": 31.2,
        "silt_percent": 24.5,
        "sand_percent": 44.3,
        "normalized_values": {"texture_class": "CLAY_LOAM"},
        "raw_payload": {"source": "regression-seed"},
        "metadata": {"provider_family": "OPEN_SOURCE_BASELINE"},
    })
    check(soilgrids.status_code == 201, "Create SoilGrids baseline snapshot returns 201", soilgrids.text)
    baseline = soilgrids.json()
    check(baseline["provider"] == "SOILGRIDS", "Provider normalized")
    check(baseline["farmer_id"] == str(farmer_id), "Farmer inferred from parcel")
    check(baseline["resolution_meters"] == 250, "Resolution stored")
    check(baseline["normalized_values"]["texture_class"] == "CLAY_LOAM", "Normalized provider values stored")
    check(baseline["metadata"]["provider_family"] == "OPEN_SOURCE_BASELINE", "SoilGrids provenance metadata stored")

    slusi = client.post("/api/v1/soil-profiles/enrichments/shc-slusi/manual-capture", headers=headers, json={
        "parcel_id": str(parcel_id),
        "state": "UTTAR PRADESH",
        "district": "AZAMGARH",
        "cycle": "2024-25",
        "parameter": "Manganese",
        "status_class": "SUFFICIENT",
        "value_text": ">= 2.0 ppm",
        "unit": "ppm",
        "raw_payload": {"source": "manual-map-observation"},
        "notes": "Captured from public SLUSI visualisation; no raw API discovered.",
    })
    check(slusi.status_code == 201, "Create SHC/SLUSI manual visual baseline snapshot returns 201", slusi.text)
    slusi_body = slusi.json()
    check(slusi_body["provider"] == "SHC_SLUSI", "SHC/SLUSI provider normalized")
    check(slusi_body["normalized_values"]["parameter"] == "MANGANESE", "SHC/SLUSI manual capture stores parameter")
    check(slusi_body["normalized_values"]["status_class"] == "SUFFICIENT", "SHC/SLUSI manual capture stores class")
    check(slusi_body["metadata"]["provider_family"] == "GOVT_VISUAL_BASELINE", "SHC/SLUSI provenance metadata stored")
    check(slusi_body["metadata"]["automation_mode"] == "MANUAL_OR_IMPORT_UNTIL_OFFICIAL_API", "SHC/SLUSI automation mode documented")


    fake_soilgrids_payload = {
        "provider_dataset": "soilgrids.v2.0",
        "layers": [
            {"name": "phh2o", "depths": [{"label": "0-5cm", "values": {"Q0.5": 68}}]},
            {"name": "soc", "depths": [{"label": "0-5cm", "values": {"Q0.5": 123}}]},
            {"name": "nitrogen", "depths": [{"label": "0-5cm", "values": {"Q0.5": 18}}]},
            {"name": "clay", "depths": [{"label": "0-5cm", "values": {"Q0.5": 312}}]},
            {"name": "silt", "depths": [{"label": "0-5cm", "values": {"Q0.5": 245}}]},
            {"name": "sand", "depths": [{"label": "0-5cm", "values": {"Q0.5": 443}}]},
        ],
    }
    fetched = client.post("/api/v1/soil-profiles/enrichments/soilgrids/fetch", headers=headers, json={
        "parcel_id": str(parcel_id),
        "depth_layer": "0-5cm",
        "provider_payload": fake_soilgrids_payload,
    })
    check(fetched.status_code == 201, "SoilGrids fetch endpoint stores normalized baseline", fetched.text)
    fetched_body = fetched.json()
    check(fetched_body["provider"] == "SOILGRIDS", "SoilGrids fetch normalizes provider")
    check(fetched_body["ph"] == 6.8, "SoilGrids fetch scales pH x10 value")
    check(fetched_body["clay_percent"] == 31.2, "SoilGrids fetch scales texture percentage")
    check(fetched_body["metadata"]["coordinate_source"] == "PARCEL_CENTROID", "SoilGrids fetch records coordinate source")

    fetch_without_payload = client.post("/api/v1/soil-profiles/enrichments/soilgrids/fetch", headers=headers, json={
        "parcel_id": str(parcel_id),
    })
    check(fetch_without_payload.status_code == 400, "SoilGrids fetch requires payload unless live provider enabled", fetch_without_payload.text)

    moisture = client.post("/api/v1/soil-profiles/enrichments", headers=headers, json={
        "parcel_id": str(parcel_id),
        "farmer_id": str(farmer_id),
        "provider": "OPEN_METEO",
        "provider_dataset": "forecast-soil-api",
        "snapshot_type": "MOISTURE",
        "depth_layer": "9-27cm",
        "surface_soil_moisture": 0.22,
        "root_zone_soil_moisture": 0.31,
        "soil_temperature_c": 24.7,
        "evapotranspiration_mm": 3.1,
        "expires_at": (now() + timedelta(hours=6)).isoformat(),
    })
    check(moisture.status_code == 201, "Create dynamic moisture snapshot returns 201", moisture.text)

    latest_baseline = client.get(f"/api/v1/soil-profiles/enrichments/latest?parcel_id={parcel_id}&provider=soilgrids&snapshot_type=baseline", headers=headers)
    check(latest_baseline.status_code == 200, "Latest SoilGrids baseline returns 200", latest_baseline.text)
    check(latest_baseline.json()["id"] == fetched_body["id"], "Latest baseline returns most recent SoilGrids row")

    listing = client.get(f"/api/v1/soil-profiles/enrichments?parcel_id={parcel_id}", headers=headers)
    check(listing.status_code == 200, "List enrichment snapshots returns 200", listing.text)
    check(len(listing.json()) == 4, "List returns direct baseline, SHC/SLUSI baseline, fetched SoilGrids baseline, and moisture snapshots")

    mismatch = client.post("/api/v1/soil-profiles/enrichments", headers=headers, json={
        "parcel_id": str(parcel_id),
        "farmer_id": str(uuid.uuid4()),
        "provider": "SOILGRIDS",
    })
    check(mismatch.status_code == 400, "Snapshot rejects mismatched farmer/parcel linkage", mismatch.text)

    isolated = client.get(f"/api/v1/soil-profiles/enrichments/latest?parcel_id={parcel_id}", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Latest enrichment is tenant isolated", isolated.text)

    db = SessionLocal()
    try:
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
    print("Soil enrichment snapshots validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
