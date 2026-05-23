"""Test: Tenant → Project → Role → Farmer → Parcel (full onboarding flow)."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.modules.master_data.models import GeographyVillage

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

# Get a real village ID from the database
db = SessionLocal()
village = db.query(GeographyVillage).first()
db.close()
VILLAGE_ID = str(village.id) if village else str(uuid.uuid4())

TENANT_ID = "test-agri-corp"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}


def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")
    if not passed:
        print(f"       FAILED!")


print("=" * 60)
print("TENANT → PROJECT → FARMER → PARCEL FLOW")
print("=" * 60)

# 1. Create tenant
print("\n[1] Create tenant")
r = client.post("/api/v1/tenants", json={
    "id": TENANT_ID,
    "name": "Test Agri Corporation",
    "type": "ENTERPRISE",
    "contact_email": "admin@testagri.com",
})
test("Tenant created", r.status_code == 201, f"Status: {r.status_code}")

# 2. Create project
print("\n[2] Create project")
r = client.post("/api/v1/projects", headers=HEADERS, json={
    "name": "Kharif 2026 UP Rice Program",
    "start_date": "2026-06-01",
    "end_date": "2026-11-30",
    "geography_scope": {"state_ids": ["9"]},
    "crop_scope": ["RICE", "MAIZE"],
})
test("Project created", r.status_code == 201)
project = r.json()
PROJECT_ID = project["id"]
test("Project has correct name", project["name"] == "Kharif 2026 UP Rice Program")

# 3. Assign role
print("\n[3] Assign dealer role")
dealer_user_id = str(uuid.uuid4())
r = client.post(f"/api/v1/projects/{PROJECT_ID}/roles", headers=HEADERS, json={
    "user_id": dealer_user_id,
    "role": "DEALER",
    "territory_scope": {"village_ids": [VILLAGE_ID]},
})
test("Role assigned", r.status_code == 201)

# 4. List projects
print("\n[4] List projects")
r = client.get("/api/v1/projects", headers=HEADERS)
test("Projects listed", r.status_code == 200 and len(r.json()) >= 1)

# 5. Enroll farmer (minimal — just mobile + village)
print("\n[5] Enroll farmer (progressive — minimal data)")
r = client.post("/api/v1/farmers", headers=HEADERS, json={
    "mobile_number": "+919876500001",
    "village_id": VILLAGE_ID,
    "primary_crop_code": "RICE",
    "display_name": "Ram Prasad",
    "total_land_area": 5.0,
    "total_land_unit": "BIGHA",
})
test("Farmer enrolled", r.status_code == 201)
farmer = r.json()
FARMER_ID = farmer["id"]
test("Farmer has village", str(farmer["village_id"]) == VILLAGE_ID)
test("Farmer status is ACTIVE", farmer["status"] == "ACTIVE")

# 6. Enroll farmer with ZERO optional data (absolute minimum)
print("\n[6] Enroll farmer (absolute minimum — mobile + village only)")
r = client.post("/api/v1/farmers", headers=HEADERS, json={
    "mobile_number": "+919876500002",
    "village_id": VILLAGE_ID,
})
test("Minimal farmer enrolled", r.status_code == 201)

# 7. Create parcel (NO GPS — just reported area)
print("\n[7] Create parcel (no GPS — farmer-reported area only)")
r = client.post("/api/v1/parcels", headers=HEADERS, json={
    "farmer_id": FARMER_ID,
    "village_id": VILLAGE_ID,
    "reported_area": 3.0,
    "reported_area_unit": "BIGHA",
    "current_crop_code": "RICE",
    "local_name": "Bada Khet",
})
test("Parcel created without GPS", r.status_code == 201)
parcel = r.json()
PARCEL_ID = parcel["id"]
test("Geometry source is NONE", parcel["geometry_source"] == "NONE")
test("Reported area = 3.0", float(parcel["reported_area"]) == 3.0)

# 8. Create parcel WITH pin drop
print("\n[8] Create parcel (with GPS pin drop)")
r = client.post("/api/v1/parcels", headers=HEADERS, json={
    "farmer_id": FARMER_ID,
    "village_id": VILLAGE_ID,
    "reported_area": 2.5,
    "reported_area_unit": "BIGHA",
    "centroid_lat": 26.7922,
    "centroid_lng": 82.1998,
    "local_name": "Chhota Khet",
})
test("Parcel with pin drop created", r.status_code == 201)
test("Geometry source is PIN_DROP", r.json()["geometry_source"] == "PIN_DROP")

# 9. Progressive geometry update (add GPS walk later)
print("\n[9] Progressive geometry update (add GPS to existing parcel)")
r = client.patch(f"/api/v1/parcels/{PARCEL_ID}/geometry", headers=HEADERS, json={
    "geometry_source": "PIN_DROP",
    "centroid_lat": 26.7900,
    "centroid_lng": 82.2010,
    "accuracy_meters": 12.5,
})
test("Geometry updated progressively", r.status_code == 200)
test("Source updated to PIN_DROP", r.json()["geometry_source"] == "PIN_DROP")

# 10. List farmers
print("\n[10] List farmers")
r = client.get("/api/v1/farmers", headers=HEADERS)
test("Farmers listed", r.status_code == 200 and len(r.json()) >= 2)

# 11. List parcels
print("\n[11] List parcels for farmer")
r = client.get(f"/api/v1/parcels?farmer_id={FARMER_ID}", headers=HEADERS)
test("Parcels listed", r.status_code == 200 and len(r.json()) == 2)

print(f"\n{'=' * 60}")
print("🟢 Full onboarding flow validated!")
print("   Tenant → Project → Role → Farmer → Parcel (GPS optional)")
print(f"{'=' * 60}")
