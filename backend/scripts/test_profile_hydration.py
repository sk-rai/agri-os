"""Regression test for Android profile hydration after login.

Validates:
- /api/v1/farmers/by-mobile/{mobile}
- /api/v1/farmers/me/profile
- duplicate farmer selection prefers the richer profile
- duplicate direct enrollment is rejected
- hydration includes parcel geometry fields and crop-cycle summaries
- PARCEL_GEOMETRY sync stores GPS_WALK polygon GeoJSON, centroid, and area
- duplicate farmer cleanup endpoints list and archive empty duplicates
"""

import sys
import uuid
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import User
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.master_data.models import Crop, CropLifecycleTemplate
from app.modules.media.models import WeatherSnapshot
from app.modules.workflow.models import CropCycle, CropStageInstance


client = TestClient(app)

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"


def test(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")
    if not passed:
        raise AssertionError(name)


def ensure_tenant(db, tenant_id: str):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        tenant = Tenant(
            id=tenant_id,
            name="Hydration Test Tenant",
            type="ENTERPRISE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.flush()
    return tenant


def first_crop_and_template(db):
    template = db.query(CropLifecycleTemplate).first()
    if not template:
        raise RuntimeError("No crop lifecycle template found. Seed master data first.")
    crop = db.query(Crop).filter(Crop.id == template.crop_id).first()
    if not crop:
        raise RuntimeError("Lifecycle template has no crop row")
    return crop, template


print("=" * 72)
print("PROFILE HYDRATION REGRESSION")
print("=" * 72)

suffix = uuid.uuid4().hex[:8]
tenant_id = f"hydration-test-{suffix}"
mobile_10 = f"98{uuid.uuid4().int % 100000000:08d}"
mobile = f"+91{mobile_10}"
headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(uuid.uuid4())}
rich_farmer_id = None
empty_duplicate_id = None
parcel_id = None

db = SessionLocal()
try:
    ensure_tenant(db, tenant_id)
    crop, template = first_crop_and_template(db)

    empty_duplicate = Farmer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        mobile_number=mobile,
        display_name="Empty Duplicate",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    rich_farmer = Farmer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        mobile_number=mobile,
        display_name="Hydrated Farmer",
        village_name_manual="Hydration Village",
        language_preference="en",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add_all([empty_duplicate, rich_farmer])
    db.flush()

    user = User(
        id=uuid.UUID(headers["X-Actor-ID"]),
        mobile_number=mobile,
        role="FARMER",
        display_name="Hydrated Farmer",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    parcel = Parcel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        farmer_id=rich_farmer.id,
        village_name_manual="Hydration Village",
        reported_area=5,
        reported_area_unit="BISWA",
        survey_number="HYD-001",
        ownership_type="OWNED",
        geometry_source="PIN_DROP",
        centroid_lat=19.03747,
        centroid_lng=72.877737,
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    cycle = CropCycle(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        farmer_id=rich_farmer.id,
        parcel_id=parcel.id,
        crop_code=crop.code,
        season_code=template.season_code,
        lifecycle_template_id=template.id,
        planned_sowing_date=date(2026, 7, 1),
        actual_sowing_date=date(2026, 7, 1),
        expected_harvest_date=date(2026, 10, 1),
        actual_harvest_date=date(2026, 10, 1),
        status="COMPLETED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    stage = CropStageInstance(
        id=uuid.uuid4(),
        crop_cycle_id=cycle.id,
        tenant_id=tenant_id,
        stage_code="HARVEST",
        stage_name="Harvest",
        stage_order=1,
        expected_duration_days=1,
        planned_start_date=date(2026, 10, 1),
        actual_start_date=date(2026, 10, 1),
        actual_end_date=date(2026, 10, 1),
        status="COMPLETED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    weather_snapshot = WeatherSnapshot(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        farmer_id=rich_farmer.id,
        parcel_id=parcel.id,
        location_scope="VILLAGE",
        location_key="Hydration Village",
        fetched_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        summary="Hydration readiness weather snapshot",
        condition_code="CLEAR",
        risk_flags=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add_all([user, parcel, cycle, stage, weather_snapshot])
    rich_farmer_id = str(rich_farmer.id)
    empty_duplicate_id = str(empty_duplicate.id)
    parcel_id = str(parcel.id)
    db.commit()
finally:
    db.close()

print("\n[1] Hydrate by 10-digit mobile")
r = client.get(f"/api/v1/farmers/by-mobile/{mobile_10}", headers={"X-Tenant-ID": tenant_id})
test("Hydration by mobile returns 200", r.status_code == 200, f"Status: {r.status_code}")
body = r.json()
test("Hydration includes schema version", body["schema_version"] == "profile_hydration.v1")
test("Selects richer farmer over empty duplicate", body["farmer"]["id"] == rich_farmer_id)
test("Reports duplicate farmer", body["summary"]["duplicate_farmer_count"] == 1)
test("Includes parcel", body["summary"]["parcel_count"] == 1)
test("Includes completed crop-cycle summary", body["summary"]["completed_crop_cycle_count"] == 1)
test("PIN_DROP returns centroid", body["parcels"][0]["centroid_lat"] is not None)
test("PIN_DROP does not return GeoJSON for MVP", body["parcels"][0]["geojson"] is None)
completion = body["profile_completion"]
test("Hydration includes profile completion schema", completion["schema_version"] == "profile_completion.v1")
test("Profile completion marks home ready", completion["is_complete_for_home"] is True)
test("Profile completion includes farmer section", completion["sections"]["farmer"]["status"] == "COMPLETE")
test("Profile completion includes land section", completion["sections"]["land"]["status"] == "COMPLETE")
test("Profile completion recommends soil capture", any(action["code"] == "ADD_SOIL_PROFILE" for action in completion["next_actions"]))
test("Profile completion exposes weather snapshot readiness", completion["enrichment_readiness"]["has_weather_snapshot"] is True)
test("Profile completion marks weather advisory ready", completion["enrichment_readiness"]["ready_for_weather_advisory"] is True)
test("Profile completion marks soil moisture enrichment ready when land location exists", completion["enrichment_readiness"]["ready_for_soil_moisture_enrichment"] is True)
test("Hydration summary mirrors home readiness", body["summary"]["profile_ready_for_home"] is True)
test("Default hydration omits heavy form contract", body.get("form_contract") is None)

print("\n[1a] Profile readiness summary")
readiness = client.get("/api/v1/farmers/profile-readiness", headers={"X-Tenant-ID": tenant_id})
test("Profile readiness returns 200", readiness.status_code == 200, f"Status: {readiness.status_code} Body: {readiness.text[:300]}")
readiness_body = readiness.json()
test("Profile readiness schema stable", readiness_body["schema_version"] == "farmer_profile_readiness.v1")
test("Profile readiness counts active farmers", readiness_body["summary"]["farmer_count"] == 2)
test("Profile readiness counts home-ready farmer", readiness_body["summary"]["home_ready_count"] == 1)
test("Profile readiness counts missing parcel", readiness_body["summary"]["missing_parcel_count"] == 1)
test("Profile readiness counts weather snapshot availability", readiness_body["summary"]["weather_snapshot_available_count"] == 1)
test("Profile readiness counts weather advisory readiness", readiness_body["summary"]["weather_advisory_ready_count"] == 1)
test("Profile readiness counts satellite enrichment readiness", readiness_body["summary"]["satellite_enrichment_ready_count"] == 1)
test("Profile readiness exposes per-farmer completion", any(row["farmer"]["id"] == rich_farmer_id and row["profile_completion"]["is_complete_for_home"] for row in readiness_body["farmers"]))

print("\n[1b] Hydrate with backend-owned profile form contract")
r = client.get(f"/api/v1/farmers/by-mobile/{mobile_10}?include_form_contract=true", headers={"X-Tenant-ID": tenant_id})
test("Hydration with form contract returns 200", r.status_code == 200, f"Status: {r.status_code}")
contract_body = r.json()
form_contract = contract_body["form_contract"]
test("Hydration form contract schema stable", form_contract["schema_version"] == "profile_form_contract_bundle.v1")
test("Hydration includes farmer form schema", "farmer_registration" in form_contract["forms"])
test("Hydration includes parcel form schema", "parcel_registration" in form_contract["forms"])
test("Hydration includes soil form schema", "soil_profile" in form_contract["forms"])
test("Hydration includes configurable land units", "land_units" in form_contract["option_sets"])
test("Hydration includes configurable soil textures", "soil_textures" in form_contract["option_sets"])
test("Form contract keeps canonical farmer mapping", any(field.get("canonical_field") == "farmer.total_land_unit" for field in form_contract["forms"]["farmer_registration"]["fields"]))
test("Form contract keeps canonical parcel mapping", any(field.get("canonical_field") == "parcel.reported_area_unit" for field in form_contract["forms"]["parcel_registration"]["fields"]))
test("Form contract keeps canonical soil mapping", any(field.get("canonical_field") == "soil_profile.soil_texture" for field in form_contract["forms"]["soil_profile"]["fields"]))

print("\n[2] Hydrate via logged-in actor")
r = client.get("/api/v1/farmers/me/profile?include_form_contract=true", headers=headers)
test("/farmers/me/profile returns 200", r.status_code == 200, f"Status: {r.status_code}")
actor_body = r.json()
test("Actor hydration returns same farmer", actor_body["farmer"]["id"] == rich_farmer_id)
test("Actor hydration can include form contract", actor_body["form_contract"]["schema_version"] == "profile_form_contract_bundle.v1")

print("\n[3] Duplicate direct enrollment guard")
r = client.post(
    "/api/v1/farmers",
    headers=headers,
    json={
        "mobile_number": mobile,
        "village_name_manual": "Hydration Village",
        "display_name": "Should Not Create",
    },
)
test("Duplicate enrollment rejected", r.status_code == 409, f"Status: {r.status_code}")

print("\n[4] Duplicate farmer cleanup endpoints")
r = client.get(f"/api/v1/farmers/duplicates?mobile_number={mobile_10}", headers={"X-Tenant-ID": tenant_id})
test("Duplicate list returns 200", r.status_code == 200, f"Status: {r.status_code}")
dup_body = r.json()
test("Duplicate list has one group", dup_body["group_count"] == 1)
test("Duplicate list recommends richer farmer", dup_body["groups"][0]["recommended_primary_farmer_id"] == rich_farmer_id)

r = client.post(
    f"/api/v1/farmers/{rich_farmer_id}/duplicates/archive",
    headers=headers,
    json={
        "duplicate_farmer_ids": [empty_duplicate_id],
        "reason": "profile hydration regression cleanup",
    },
)
test("Empty duplicate archived", r.status_code == 200, f"Status: {r.status_code}")
test("Archive response contains duplicate", r.json()["archived"][0]["id"] == empty_duplicate_id)

r = client.get(f"/api/v1/farmers/by-mobile/{mobile_10}", headers={"X-Tenant-ID": tenant_id})
test("Hydration still returns primary after archive", r.status_code == 200)
test("Archived duplicate no longer counted", r.json()["summary"]["duplicate_farmer_count"] == 0)

print("\n[5] PARCEL_GEOMETRY sync stores GPS_WALK polygon")
polygon = {
    "type": "Polygon",
    "coordinates": [[
        [72.87770, 19.03740],
        [72.87810, 19.03740],
        [72.87810, 19.03780],
        [72.87770, 19.03780],
    ]],
}
r = client.post(
    "/api/v1/sync/events",
    headers=headers,
    json={
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "entity_type": "PARCEL_GEOMETRY",
                "entity_id": parcel_id,
                "operation": "UPDATE",
                "payload": {
                    "geometry_source": "GPS_WALK",
                    "geojson": polygon,
                    "accuracy_meters": 6.5,
                },
                "version": 1,
                "dependency_ids": [],
                "metadata": {"source": "profile_hydration_regression"},
            }
        ]
    },
)
test("PARCEL_GEOMETRY sync accepted", r.status_code == 200 and len(r.json()["accepted"]) == 1, f"Status: {r.status_code} Body: {r.text}")

r = client.get(f"/api/v1/farmers/by-mobile/{mobile_10}", headers={"X-Tenant-ID": tenant_id})
parcel_body = r.json()["parcels"][0]
test("GPS_WALK source returned in hydration", parcel_body["geometry_source"] == "GPS_WALK")
test("GPS_WALK returns Polygon GeoJSON", parcel_body["geojson_type"] == "Polygon")
test("GPS_WALK computes centroid", parcel_body["centroid_lat"] is not None and parcel_body["centroid_lng"] is not None)
test("GPS_WALK computes area", parcel_body["computed_area_hectares"] is not None and parcel_body["computed_area_hectares"] > 0)

print("\n[6] Cleanup temporary hydration test data")
db = SessionLocal()
try:
    db.query(CropStageInstance).filter(CropStageInstance.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(CropCycle).filter(CropCycle.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(User).filter(User.mobile_number == mobile).delete(synchronize_session=False)
    db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
    db.commit()
    test("Temporary rows cleaned up", True)
finally:
    db.close()

print(f"\n{'=' * 72}")
print("🟢 Profile hydration regression validated")
print(f"{'=' * 72}")
