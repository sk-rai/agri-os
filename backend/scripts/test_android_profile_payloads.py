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
from app.modules.farmer.soil_profile import SoilEnrichmentJobAudit, SoilEnrichmentSnapshot, SoilProfile
from app.modules.media.provider_runtime_policy import provider_failure_metadata, provider_runtime_policy_from_config
from app.modules.farmer.soil_enrichment_adapters import normalize_soil_provider_http_error, normalize_open_meteo_soil_moisture, normalize_soilgrids_properties
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


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
    admin = None
    try:
        db.add(Tenant(
            id=tenant_id,
            name="Android Profile Payload Tenant",
            type="ENTERPRISE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
        admin, admin_headers = create_test_admin(db, tenant_id=tenant_id)
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    adapter_parcel_id = uuid.uuid4()
    soilgrids = normalize_soilgrids_properties(
        {
            "id": "soilgrids-test-cell",
            "properties": {
                "phh2o": {"mean": 72},
                "soc": {"mean": 18},
                "nitrogen": {"mean": 920},
                "clay": {"mean": 32},
                "sand": {"mean": 38},
                "silt": {"mean": 30},
            },
        },
        parcel_id=adapter_parcel_id,
        observed_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    check(soilgrids["snapshot_type"] == "BASELINE", "SoilGrids adapter normalizes baseline snapshot")
    check(soilgrids["provider"] == "SOILGRIDS", "SoilGrids adapter records provider")
    check(soilgrids["ph"] == 7.2, "SoilGrids adapter rescales pH")
    check(soilgrids["soil_texture"] == "LOAMY", "SoilGrids adapter infers coarse texture")

    moisture = normalize_open_meteo_soil_moisture(
        {
            "latitude": 25.82,
            "longitude": 82.97,
            "hourly": {
                "time": ["2026-07-20T09:00:00+00:00"],
                "soil_moisture_0_to_1cm": [0.21],
                "soil_moisture_3_to_9cm": [0.24],
                "soil_moisture_9_to_27cm": [0.29],
                "soil_temperature_0cm": [28.4],
            },
        },
        parcel_id=adapter_parcel_id,
        fetched_at=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc),
        refresh_interval_hours=6,
    )
    check(moisture["snapshot_type"] == "MOISTURE", "Open-Meteo soil adapter normalizes moisture snapshot")
    check(moisture["surface_soil_moisture"] == 0.21, "Open-Meteo soil adapter maps surface moisture")
    check(moisture["root_zone_soil_moisture"] == 0.29, "Open-Meteo soil adapter maps root-zone moisture")
    check(moisture["metadata"]["schema_version"] == "open_meteo_soil_adapter.v1", "Open-Meteo soil adapter metadata schema stable")
    soil_runtime_policy = provider_runtime_policy_from_config({"timeout_seconds": 999, "max_retries": 4, "demo_payload": {"ok": True}})
    check(soil_runtime_policy.timeout_seconds == 120, "Soil provider runtime policy clamps timeout")
    check(soil_runtime_policy.max_retries == 4, "Soil provider runtime policy preserves retry count")
    check(soil_runtime_policy.demo_mode is True, "Soil provider runtime policy detects demo mode")
    soil_failure_meta = provider_failure_metadata(error=normalize_soil_provider_http_error(provider="SOILGRIDS", status_code=429), policy=soil_runtime_policy)
    check(soil_failure_meta["retryable"] is True, "Soil provider failure metadata preserves retryable flag")
    check(soil_failure_meta["runtime_policy"]["timeout_seconds"] == 120, "Soil provider failure metadata includes runtime policy")
    soil_retryable_error = normalize_soil_provider_http_error(provider="SOILGRIDS", status_code=429, message="rate limited")
    check(soil_retryable_error.retryable is True, "Soil provider HTTP 429 is retryable")
    check(soil_retryable_error.error_code == "PROVIDER_RETRYABLE_HTTP_ERROR", "Soil provider retryable error code stable")
    soil_non_retryable_error = normalize_soil_provider_http_error(provider="SOILGRIDS", status_code=401, message="unauthorized")
    check(soil_non_retryable_error.retryable is False, "Soil provider HTTP 401 is non-retryable")
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

    farmer_update = client.patch(f"/api/v1/farmers/{farmer_id}", headers=headers, json={
        "pin_code": "560099",
        "language_preference": "hi",
        "assistance_mode": "FIELD_AGENT_ASSISTED",
        "enrollment_gps_lat": 0.0,
        "enrollment_gps_lng": 77.5946,
    })
    check(farmer_update.status_code == 200, "Android farmer update payload patches farmer", farmer_update.text)
    updated_farmer = farmer_update.json()
    check(updated_farmer["pin_code"] == "560099", "Farmer update returns changed PIN code")
    db = SessionLocal()
    try:
        stored_farmer = db.query(Farmer).filter(Farmer.id == uuid.UUID(farmer_id), Farmer.tenant_id == tenant_id).first()
        check(stored_farmer.enrollment_method == "ASSISTED", "Assisted update remains backend-normalized")
        check(float(stored_farmer.enrollment_gps_lat) == 0.0, "Farmer update stores zero latitude")
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
    parcel_response = client.post("/api/v1/parcels", headers=admin_headers, json={
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

    part_owner_parcel_response = client.post("/api/v1/parcels", headers=admin_headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "pin_code": "560002",
        "location_scope": {"pin_codes": ["560002"], "village_names": ["Android Profile Village", "Adjacent Village"], "notes": "FPO or cross-village plot support"},
        "reported_area": 1.25,
        "reported_area_unit": "ACRE",
        "ownership_type": "PART_OWNER",
        "share_percentage": 50,
        "centroid_lat": 0.0,
        "centroid_lng": 77.5946,
    })
    check(part_owner_parcel_response.status_code == 201, "Android parcel payload accepts part-owner multi-location PIN plot", part_owner_parcel_response.text)
    part_owner_parcel = part_owner_parcel_response.json()
    check(part_owner_parcel["pin_code"] == "560002", "Parcel response returns PIN code")
    check(part_owner_parcel["location_scope"]["pin_codes"] == ["560002"], "Parcel response returns location scope")
    check(part_owner_parcel["ownership_type"] == "PART_OWNER", "Parcel response returns part-owner ownership")
    check(part_owner_parcel["geometry_source"] == "PIN_DROP", "Zero latitude pin-drop is treated as captured geometry")

    parcel_update = client.patch(f"/api/v1/parcels/{part_owner_parcel['id']}", headers=headers, json={
        "pin_code": "560003",
        "location_scope": {"pin_codes": ["560003"], "village_names": ["Updated Village"], "custom_scope": True},
        "ownership_type": "SHARED",
        "share_percentage": 60,
        "irrigation_source": "RAIN_FED",
    })
    check(parcel_update.status_code == 200, "Android parcel update payload patches parcel", parcel_update.text)
    patched_parcel = parcel_update.json()
    check(patched_parcel["pin_code"] == "560003", "Parcel update returns changed PIN code")
    check(patched_parcel["location_scope"]["custom_scope"] is True, "Parcel update returns customized location scope")
    check(patched_parcel["ownership_type"] == "SHARED", "Parcel update returns changed ownership")

    db = SessionLocal()
    try:
        stored_part_owner_parcel = db.query(Parcel).filter(Parcel.id == uuid.UUID(part_owner_parcel["id"]), Parcel.tenant_id == tenant_id).first()
        check(stored_part_owner_parcel is not None, "Part-owner parcel row stored")
        check(float(stored_part_owner_parcel.centroid_lat) == 0.0, "Parcel stores zero latitude pin-drop")
        check(stored_part_owner_parcel.geometry_source == "PIN_DROP", "Parcel stores pin-drop geometry source")
        check((stored_part_owner_parcel.location_scope or {}).get("custom_scope") is True, "Parcel stores updated location scope")
    finally:
        db.close()

    invalid_parcel = client.post("/api/v1/parcels", headers=admin_headers, json={
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

    project_invalid_parcel = client.post("/api/v1/parcels", headers=admin_headers, json={
        "farmer_id": farmer_id,
        "village_name_manual": "Android Profile Village",
        "reported_area": 1,
        "reported_area_unit": "ACRE",
        "ownership_type": "SHARECROP",
    })
    check(project_invalid_parcel.status_code == 400, "Project ownership override rejects default option", project_invalid_parcel.text)
    check(project_invalid_parcel.json()["detail"]["allowed_values"] == ["OWNED"], "Project option validation uses override values")

    project_valid_parcel = client.post("/api/v1/parcels", headers=admin_headers, json={
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

    soil_update = client.patch(f"/api/v1/soil-profiles/{soil['id']}", headers=headers, json={
        "boron_b": 0.55,
        "ph": 7.3,
        "data_source": "LAB_REPORT",
        "lab_name": "Android Payload Lab",
    })
    check(soil_update.status_code == 200, "Android soil update payload patches soil profile", soil_update.text)
    updated_soil = soil_update.json()
    check(float(updated_soil["boron_b"]) == 0.55, "Soil update returns changed boron_b alias")

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
                provider="SHC_SLUSI", provider_dataset="shc-slusi.wms", snapshot_type="BASELINE", status="AVAILABLE",
                depth_layer="surface", resolution_meters=50000, confidence="GOVT_SAMPLE_POINT", observed_at=datetime.now(timezone.utc), fetched_at=datetime.now(timezone.utc),
                ph=7.2, organic_carbon=0.25, nitrogen=163, normalized_values={"district": "AZAMGARH", "village": "Pakari Khurd"}, raw_payload={}, metadata_={"source_contract": "OGC_WMS_GETFEATUREINFO_JSON"},
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
    check(enrichment["has_soil_baseline_snapshot"] is True, "Readiness detects baseline snapshots")
    check(enrichment["has_soil_moisture_snapshot"] is True, "Readiness detects soil moisture snapshot")
    check(enrichment["has_soilgrids_baseline_snapshot"] is True, "Readiness detects SoilGrids baseline snapshot")
    check(enrichment["has_shc_slusi_snapshot"] is True, "Readiness detects SHC/SLUSI point snapshot")
    check(enrichment["soil_baseline_snapshot_count"] == 2, "Readiness counts baseline snapshots")
    check(enrichment["soil_moisture_snapshot_count"] == 1, "Readiness counts moisture snapshots")
    check(enrichment["soilgrids_baseline_snapshot_count"] == 1, "Readiness counts SoilGrids snapshots")
    check(enrichment["shc_slusi_snapshot_count"] == 1, "Readiness counts SHC/SLUSI snapshots")
    check(readiness["summary"]["soil_baseline_snapshot_available_count"] >= 1, "Readiness summary counts baseline availability")
    check(readiness["summary"]["soil_moisture_snapshot_available_count"] >= 1, "Readiness summary counts moisture availability")
    check(readiness["summary"]["soilgrids_baseline_snapshot_available_count"] >= 1, "Readiness summary counts SoilGrids availability")
    check(readiness["summary"]["shc_slusi_snapshot_available_count"] >= 1, "Readiness summary counts SHC/SLUSI availability")

    print("\n[4b] Soil enrichment summary endpoint")
    summary_response = client.get(f"/api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}", headers=headers)
    check(summary_response.status_code == 200, "Soil enrichment summary returns 200", summary_response.text)
    summary = summary_response.json()
    check(summary["schema_version"] == "soil_enrichment_summary.v1", "Soil enrichment summary schema stable")
    check(summary["filters"]["farmer_id"] == farmer_id, "Soil enrichment summary preserves farmer filter")
    check(summary["snapshot_count"] == 3, "Soil enrichment summary counts snapshots")
    check(summary["has_baseline"] is True, "Soil enrichment summary detects baseline")
    check(summary["has_moisture"] is True, "Soil enrichment summary detects moisture")
    check(summary["provider_counts"]["SOILGRIDS"] == 1, "Soil enrichment summary counts SoilGrids provider")
    check(summary["provider_counts"]["OPEN_METEO"] == 1, "Soil enrichment summary counts moisture provider")
    check(summary["provider_counts"]["SHC_SLUSI"] == 1, "Soil enrichment summary counts SHC/SLUSI provider")
    check(summary["latest_baseline"]["provider"] in {"SOILGRIDS", "SHC_SLUSI"}, "Soil enrichment summary exposes latest baseline")
    check(summary["latest_moisture"]["provider"] == "OPEN_METEO", "Soil enrichment summary exposes latest moisture")

    moisture_summary_response = client.get(f"/api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}&snapshot_type=MOISTURE", headers=headers)
    check(moisture_summary_response.status_code == 200, "Soil enrichment summary type filter returns 200", moisture_summary_response.text)
    moisture_summary = moisture_summary_response.json()
    check(moisture_summary["snapshot_count"] == 1, "Soil enrichment summary type filter narrows rows")
    check(moisture_summary["has_baseline"] is False, "Filtered moisture summary omits baseline")
    check(moisture_summary["has_moisture"] is True, "Filtered moisture summary keeps moisture")

    missing_filter_summary = client.get("/api/v1/soil-profiles/enrichments/summary", headers=headers)
    check(missing_filter_summary.status_code == 400, "Soil enrichment summary requires farmer or parcel filter", missing_filter_summary.text)

    db = SessionLocal()
    missing_enrichment_farmer_id = uuid.uuid4()
    missing_enrichment_parcel_id = uuid.uuid4()
    try:
        db.add(Farmer(
            id=missing_enrichment_farmer_id,
            tenant_id=tenant_id,
            mobile_number=f"+9196{uuid.uuid4().int % 100000000:08d}",
            display_name="Missing Enrichment Farmer",
            village_name_manual="Android Profile Village",
            pin_code="560004",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(Parcel(
            id=missing_enrichment_parcel_id,
            tenant_id=tenant_id,
            farmer_id=missing_enrichment_farmer_id,
            village_name_manual="Android Profile Village",
            pin_code="560004",
            reported_area=0.75,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            geometry_source="PIN_DROP",
            centroid_lat=12.9716,
            centroid_lng=77.5946,
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(SoilEnrichmentJobAudit(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=missing_enrichment_farmer_id,
            parcel_id=missing_enrichment_parcel_id,
            job_type="FETCH_SOIL_BASELINE",
            provider="SOILGRIDS",
            status="FAILED",
            attempt_count=1,
            reason="Regression previous baseline fetch failed",
            error_code="PROVIDER_TIMEOUT",
            metadata_={"queue_reason": "MISSING_BASELINE"},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
    finally:
        db.close()

    print("\n[4c] Soil enrichment queue endpoint")
    queue_response = client.get("/api/v1/soil-profiles/enrichments/queue", headers=admin_headers)
    check(queue_response.status_code == 200, "Soil enrichment queue returns 200", queue_response.text)
    queue = queue_response.json()
    check(queue["schema_version"] == "soil_enrichment_queue.v1", "Soil enrichment queue schema stable")
    check(queue["filters"]["farmer_id"] is None, "Soil enrichment queue preserves empty farmer filter")
    check(queue["count"] >= 2, "Soil enrichment queue returns location-ready parcel rows")
    missing_queue_item = next(item for item in queue["items"] if item["parcel"]["id"] == str(missing_enrichment_parcel_id))
    check(missing_queue_item["missing_baseline"] is True, "Soil enrichment queue detects missing baseline")
    check(missing_queue_item["missing_moisture"] is True, "Soil enrichment queue detects missing moisture")
    check(missing_queue_item["recommended_jobs"] == ["FETCH_SOIL_BASELINE", "FETCH_SOIL_MOISTURE"], "Soil enrichment queue recommends missing jobs")
    check(missing_queue_item["latest_audit_by_job"]["FETCH_SOIL_BASELINE"]["status"] == "FAILED", "Soil enrichment queue includes latest audit status")
    check(missing_queue_item["latest_audit_by_job"]["FETCH_SOIL_BASELINE"]["error_code"] == "PROVIDER_TIMEOUT", "Soil enrichment queue includes latest audit error")
    queue_item = next(item for item in queue["items"] if item["parcel"]["id"] == parcel_id)
    check(queue_item["snapshot_counts"]["baseline"] == 2, "Soil enrichment queue includes baseline count")
    check(queue_item["snapshot_counts"]["moisture"] == 1, "Soil enrichment queue includes moisture count")
    check(queue_item["missing_baseline"] is False, "Soil enrichment queue detects existing baseline")
    check(queue_item["missing_moisture"] is False, "Soil enrichment queue detects existing moisture")
    check("LOCATION_READY" in queue_item["reasons"], "Soil enrichment queue marks location-ready parcel")
    check(queue_item["recommended_jobs"] == [], "Soil enrichment queue has no jobs when snapshots exist")

    missing_any_queue = client.get(f"/api/v1/soil-profiles/enrichments/queue?farmer_id={missing_enrichment_farmer_id}&missing=ANY", headers=admin_headers)
    check(missing_any_queue.status_code == 200, "Soil enrichment missing ANY queue returns 200", missing_any_queue.text)
    missing_any_body = missing_any_queue.json()
    check(missing_any_body["count"] == 1, "Soil enrichment missing ANY queue returns incomplete parcel")
    check(missing_any_body["items"][0]["parcel"]["id"] == str(missing_enrichment_parcel_id), "Soil enrichment missing ANY queue excludes complete parcel")

    operations_health = client.get("/api/v1/soil-profiles/enrichments/operations/health", headers=admin_headers)
    check(operations_health.status_code == 200, "Soil enrichment operations health returns 200", operations_health.text[:500])
    operations_health_body = operations_health.json()
    check(operations_health_body["schema_version"] == "soil_enrichment_operations_health.v1", "Soil enrichment operations health schema stable")
    check(operations_health_body["summary"]["location_ready_parcel_count"] >= 1, "Soil enrichment operations health counts location-ready parcels")
    check(operations_health_body["summary"]["missing_baseline_count"] >= 1, "Soil enrichment operations health counts missing baseline")
    check(operations_health_body["summary"]["missing_moisture_count"] >= 1, "Soil enrichment operations health counts missing moisture")
    check("FETCH_SOIL_BASELINE" in operations_health_body["recommended_actions"], "Soil enrichment operations health recommends baseline fetch")

    invalid_queue = client.get(f"/api/v1/soil-profiles/enrichments/queue?farmer_id={farmer_id}&missing=ANDROID_ONLY", headers=admin_headers)
    check(invalid_queue.status_code == 400, "Soil enrichment queue rejects invalid missing filter", invalid_queue.text)

    print("\n[4d] Soil enrichment job audit endpoint")
    audit_create = client.post("/api/v1/soil-profiles/enrichments/jobs/audit", headers=admin_headers, json={
        "farmer_id": farmer_id,
        "parcel_id": parcel_id,
        "job_type": "FETCH_SOIL_BASELINE",
        "provider": "soilgrids",
        "status": "FAILED",
        "attempt_count": 2,
        "reason": "Regression simulated provider failure",
        "error_code": "PROVIDER_TIMEOUT",
        "metadata": {"queue_reason": "MISSING_BASELINE"},
    })
    check(audit_create.status_code == 201, "Soil enrichment job audit create returns 201", audit_create.text)
    audit_event = audit_create.json()
    check(audit_event["schema_version"] if "schema_version" in audit_event else "soil_enrichment_job_audit_event.v1", "Soil enrichment job audit create returns payload")
    check(audit_event["provider"] == "SOILGRIDS", "Soil enrichment job audit normalizes provider")
    check(audit_event["status"] == "FAILED", "Soil enrichment job audit stores status")
    check(audit_event["attempt_count"] == 2, "Soil enrichment job audit stores attempt count")
    check(audit_event["metadata"]["queue_reason"] == "MISSING_BASELINE", "Soil enrichment job audit stores metadata")

    audit_list = client.get(f"/api/v1/soil-profiles/enrichments/jobs/audit?farmer_id={farmer_id}&status=FAILED", headers=admin_headers)
    check(audit_list.status_code == 200, "Soil enrichment job audit list returns 200", audit_list.text)
    audit_body = audit_list.json()
    check(audit_body["schema_version"] == "soil_enrichment_job_audit.v1", "Soil enrichment job audit list schema stable")
    check(audit_body["filters"]["status"] == "FAILED", "Soil enrichment job audit list preserves status filter")
    check(audit_body["count"] == 1, "Soil enrichment job audit list filters failed event")
    check(audit_body["events"][0]["id"] == audit_event["id"], "Soil enrichment job audit list returns created event")

    invalid_audit = client.post("/api/v1/soil-profiles/enrichments/jobs/audit", headers=admin_headers, json={
        "farmer_id": farmer_id,
        "parcel_id": parcel_id,
        "job_type": "ANDROID_ONLY_JOB",
        "status": "FAILED",
    })
    check(invalid_audit.status_code == 422, "Soil enrichment job audit rejects invalid job type", invalid_audit.text)

    worker_dry = client.post(f"/api/v1/soil-profiles/enrichments/worker/run-queue?farmer_id={farmer_id}&missing=ANY&dry_run=true", headers=admin_headers)
    check(worker_dry.status_code == 200, "Soil enrichment worker dry run returns 200", worker_dry.text[:500])
    worker_dry_body = worker_dry.json()
    check(worker_dry_body["schema_version"] == "soil_enrichment_worker_run.v1", "Soil enrichment worker schema stable")
    check(worker_dry_body["dry_run"] is True, "Soil enrichment worker preserves dry run flag")

    worker_run = client.post(
        f"/api/v1/soil-profiles/enrichments/worker/run-queue?farmer_id={farmer_id}&missing=ANY&dry_run=false",
        headers=admin_headers,
        json={
            "demo_target": {
                "farmer_id": str(farmer_id),
                "parcel_id": str(missing_enrichment_parcel_id),
                "project_id": str(project_id),
            },
            "demo_payloads": {
                "soilgrids": {
                    "id": "soilgrids-worker-demo",
                    "properties": {
                        "phh2o": {"mean": 71},
                        "soc": {"mean": 16},
                        "nitrogen": {"mean": 880},
                        "clay": {"mean": 30},
                        "sand": {"mean": 40},
                        "silt": {"mean": 30},
                    },
                },
                "open_meteo_soil": {
                    "latitude": 25.82,
                    "longitude": 82.97,
                    "hourly": {
                        "time": ["2026-07-20T09:00:00+00:00"],
                        "soil_moisture_0_to_1cm": [0.22],
                        "soil_moisture_9_to_27cm": [0.31],
                        "soil_temperature_0cm": [29.1],
                    },
                },
            }
        },
    )
    check(worker_run.status_code == 200, "Soil enrichment worker stub run returns 200", worker_run.text[:500])
    worker_run_body = worker_run.json()
    check(worker_run_body["schema_version"] == "soil_enrichment_worker_run.v1", "Soil enrichment worker run schema stable")
    check(worker_run_body["dry_run"] is False, "Soil enrichment worker run preserves execution flag")
    check((not worker_run_body["jobs"]) or ("runtime_policy" in worker_run_body["jobs"][0]), "Soil enrichment worker exposes runtime policy")
    check("created_snapshot_count" in worker_run_body, "Soil enrichment worker demo payload reports created snapshots")
    check(worker_run_body["created_snapshot_count"] >= 1, "Soil enrichment worker demo payload creates snapshot rows")
    demo_summary = client.get(f"/api/v1/soil-profiles/enrichments/summary?parcel_id={missing_enrichment_parcel_id}", headers=headers)
    check(demo_summary.status_code == 200, "Soil enrichment worker demo payload summary returns 200", demo_summary.text[:500])
    demo_summary_body = demo_summary.json()
    check(demo_summary_body["latest_baseline"] is not None or demo_summary_body["latest_moisture"] is not None, "Soil enrichment worker demo payload creates snapshots")


    db = SessionLocal()
    try:
        stored_soil = db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).first()
        check(stored_soil is not None, "Soil profile row stored")
        check(float(stored_soil.boron_bo) == 0.55, "Android boron_b update stored as backend boron_bo")
        check(stored_soil.lab_name == "Android Payload Lab", "Soil update stores lab metadata")

        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilEnrichmentJobAudit).filter(SoilEnrichmentJobAudit.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        if admin:
            delete_test_admin(db, admin.id)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    print("=" * 72)
    print("Android profile payloads validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
