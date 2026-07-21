"""Regression for backend-driven farmer/parcel/soil profile update endpoints."""

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
    print("PROFILE UPDATE ENDPOINTS REGRESSION")
    print("=" * 72)

    tenant_id = f"profile-update-{uuid.uuid4().hex[:8]}"
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    soil_profile_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Profile Update Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Profile Update Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={
                "profile_options": {
                    "overrides": {
                        "land_units": {"options": [{"value": "ACRE", "label": {"en": "Acre"}}]},
                        "ownership_types": {"options": [{"value": "OWNED", "label": {"en": "Owned"}}, {"value": "PART_OWNER", "label": {"en": "Part owner"}}]},
                        "soil_types": {"options": [{"value": "ALLUVIAL", "label": {"en": "Alluvial"}}]},
                        "soil_textures": {"options": [{"value": "LOAM", "label": {"en": "Loam"}}]},
                        "soil_colors": {"options": [{"value": "BROWN", "label": {"en": "Brown"}}]},
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
            mobile_number=f"+9185{uuid.uuid4().int % 100000000:08d}",
            display_name="Initial Farmer",
            village_name_manual="Initial Village",
            language_preference="hi",
            total_land_unit="ACRE",
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
            village_name_manual="Initial Village",
            pin_code="560001",
            location_scope={"primary_village": "Initial Village"},
            reported_area=1.0,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            soil_type_code="ALLUVIAL",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(SoilProfile(
            id=soil_profile_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            test_date=date.today(),
            soil_type_code="ALLUVIAL",
            soil_texture="LOAM",
            soil_color="BROWN",
            data_source="MANUAL",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(actor_id)}

    farmer_update = client.patch(f"/api/v1/farmers/{farmer_id}", headers=headers, json={
        "display_name": "Updated Farmer",
        "village_name_manual": "Updated Village",
        "total_land_unit": "ACRE",
        "language_preference": "hi",
        "assistance_mode": "FIELD_AGENT_ASSISTED",
    })
    check(farmer_update.status_code == 200, "Farmer update returns 200", farmer_update.text)
    check(farmer_update.json()["display_name"] == "Updated Farmer", "Farmer update changes display name")

    farmer_bad = client.patch(f"/api/v1/farmers/{farmer_id}", headers=headers, json={"total_land_unit": "BIGHA"})
    check(farmer_bad.status_code == 400, "Farmer update rejects invalid land unit", farmer_bad.text)


    conflict = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={
        "pin_code": "999999",
        "village_name_manual": "Different Village",
        "location_scope": {"type": "SAME_AS_HOME", "same_as_home_location": True},
    })
    check(conflict.status_code == 400, "same-as-home parcel rejects conflicting PIN", conflict.text)
    missing_land_location = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={
        "location_scope": {"same_as_home_location": False},
    })
    check(missing_land_location.status_code == 400, "different-location parcel requires PIN/village", missing_land_location.text)
    parcel_update = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={
        "reported_area": 2.5,
        "reported_area_unit": "ACRE",
        "soil_type_code": "ALLUVIAL",
        "local_name": "North Field",
        "pin_code": "560002",
        "location_scope": {"primary_village": "Updated Village", "secondary_villages": ["Neighbour Village"], "pin_codes": ["560002", "560003"], "scope_reason": "plot_spans_two_villages"},
        "ownership_type": "PART_OWNER",
        "share_percentage": 50,
    })
    check(parcel_update.status_code == 200, "Parcel update returns 200", parcel_update.text)
    check(float(parcel_update.json()["reported_area"]) == 2.5, "Parcel update changes reported area")
    check(parcel_update.json()["local_name"] == "North Field", "Parcel update changes local name")
    check(parcel_update.json()["pin_code"] == "560002", "Parcel update changes parcel pin code")
    check(parcel_update.json()["location_scope"]["secondary_villages"] == ["Neighbour Village"], "Parcel update stores multi-village location scope")
    check(parcel_update.json()["ownership_type"] == "PART_OWNER", "Parcel update accepts configured part-owner ownership type")

    parcel_list_by_pin = client.get("/api/v1/parcels?pin_code=560002", headers=headers)
    check(parcel_list_by_pin.status_code == 200, "Parcel list filters by pin code", parcel_list_by_pin.text)
    check(len(parcel_list_by_pin.json()) == 1 and parcel_list_by_pin.json()[0]["id"] == str(parcel_id), "Parcel pin-code filter returns updated parcel")

    parcel_bad = client.patch(f"/api/v1/parcels/{parcel_id}", headers=headers, json={"soil_type_code": "BLACK_COTTON"})
    check(parcel_bad.status_code == 400, "Parcel update rejects invalid soil type", parcel_bad.text)

    soil_update = client.patch(f"/api/v1/soil-profiles/{soil_profile_id}", headers=headers, json={
        "soil_texture": "LOAM",
        "soil_color": "BROWN",
        "soil_type_code": "ALLUVIAL",
        "ph": 7.1,
        "boron_b": 0.42,
    })
    check(soil_update.status_code == 200, "Soil profile update returns 200", soil_update.text)
    check(float(soil_update.json()["ph"]) == 7.1, "Soil profile update changes pH")
    check(float(soil_update.json()["boron_b"]) == 0.42, "Soil profile update accepts Android boron alias")

    soil_bad = client.patch(f"/api/v1/soil-profiles/{soil_profile_id}", headers=headers, json={"soil_texture": "CLAY"})
    check(soil_bad.status_code == 400, "Soil profile update rejects invalid texture", soil_bad.text)

    isolated_farmer = client.patch(f"/api/v1/farmers/{farmer_id}", headers={"X-Tenant-ID": "default", "X-Actor-ID": str(actor_id)}, json={"display_name": "Wrong Tenant"})
    check(isolated_farmer.status_code == 404, "Farmer update is tenant isolated", isolated_farmer.text)
    isolated_parcel = client.patch(f"/api/v1/parcels/{parcel_id}", headers={"X-Tenant-ID": "default", "X-Actor-ID": str(actor_id)}, json={"local_name": "Wrong Tenant"})
    check(isolated_parcel.status_code == 404, "Parcel update is tenant isolated", isolated_parcel.text)
    isolated_soil = client.patch(f"/api/v1/soil-profiles/{soil_profile_id}", headers={"X-Tenant-ID": "default", "X-Actor-ID": str(actor_id)}, json={"ph": 8})
    check(isolated_soil.status_code == 404, "Soil profile update is tenant isolated", isolated_soil.text)

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
    print("Profile update endpoints validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
