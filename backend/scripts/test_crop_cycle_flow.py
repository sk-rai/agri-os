"""Test: Full crop cycle operational loop.

Create cycle → Start stages → Log activities → Complete → Verify audit.
Validates state machine, auto-aggregation, and audit chain.
"""
import sys
import uuid
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.modules.master_data.models import CropLifecycleTemplate, GeographyVillage
from app.modules.farmer.models import Tenant, Farmer, Parcel

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

TENANT_ID = "crop-test-tenant"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Actor-ID": ACTOR_ID}


def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")
    if not passed:
        raise AssertionError(f"FAILED: {name} — {detail}")


print("=" * 60)
print("CROP CYCLE OPERATIONAL LOOP TEST")
print("=" * 60)

# Setup: create tenant, farmer, parcel
db = SessionLocal()
village = db.query(GeographyVillage).first()
template = db.query(CropLifecycleTemplate).filter(
    CropLifecycleTemplate.crop_id.isnot(None)
).first()
db.close()

if not template:
    print("ERROR: No lifecycle templates found. Run seed_crops_up.py first.")
    sys.exit(1)

VILLAGE_ID = str(village.id)
TEMPLATE_ID = str(template.id)
CROP_CODE = template.code.split("_")[0]  # e.g., "RICE" from "RICE_KHARIF_DEFAULT"

# Create tenant
print("\n[Setup] Creating tenant + farmer + parcel...")
client.post("/api/v1/tenants", json={"id": TENANT_ID, "name": "Crop Test Corp", "type": "ENTERPRISE"})

# Create farmer
r = client.post("/api/v1/farmers", headers=HEADERS, json={
    "mobile_number": "+919800000001",
    "village_id": VILLAGE_ID,
    "primary_crop_code": CROP_CODE,
    "display_name": "Suresh Kumar",
})
FARMER_ID = r.json()["id"]

# Create parcel
r = client.post("/api/v1/parcels", headers=HEADERS, json={
    "farmer_id": FARMER_ID,
    "village_id": VILLAGE_ID,
    "reported_area": 4.0,
    "reported_area_unit": "BIGHA",
    "current_crop_code": CROP_CODE,
})
PARCEL_ID = r.json()["id"]
print(f"  Farmer: {FARMER_ID[:8]}..., Parcel: {PARCEL_ID[:8]}...")

# --- Test 1: Create crop cycle ---
print("\n[1] Create crop cycle (auto-instantiate stages from template)")
r = client.post("/api/v1/crop-cycles", headers=HEADERS, json={
    "farmer_id": FARMER_ID,
    "parcel_id": PARCEL_ID,
    "crop_code": CROP_CODE,
    "season_code": "KHARIF",
    "lifecycle_template_id": TEMPLATE_ID,
    "planned_sowing_date": "2026-06-15",
})
test("Cycle created", r.status_code == 201, f"Status: {r.status_code}")
cycle = r.json()
CYCLE_ID = cycle["id"]
test("Status is PLANNED", cycle["status"] == "PLANNED")
test("Stages instantiated", len(cycle["stages"]) > 0, f"{len(cycle['stages'])} stages")
test("Events published", "crop_cycle_created.v1" in cycle["events_published"])

# Get first and second stage IDs
stages = cycle["stages"]
STAGE_1_ID = stages[0]["id"]
STAGE_2_ID = stages[1]["id"] if len(stages) > 1 else None
print(f"       Stages: {[s['code'] for s in stages]}")

# --- Test 2: Invalid transition (can't COMPLETE a PENDING stage) ---
print("\n[2] Invalid transition (COMPLETE on PENDING stage)")
r = client.patch(
    f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_1_ID}",
    headers=HEADERS,
    json={"action": "COMPLETE", "gps_lat": 26.79, "gps_lng": 82.19},
)
test("Invalid transition returns 409", r.status_code == 409)

# --- Test 3: Start first stage ---
print("\n[3] Start first stage")
r = client.patch(
    f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_1_ID}",
    headers=HEADERS,
    json={"action": "START", "gps_lat": 26.79, "gps_lng": 82.19},
)
test("Stage started", r.status_code == 200)
result = r.json()
test("Stage status is ACTIVE", result["new_status"] == "ACTIVE")
test("Cycle status is ACTIVE", result["cycle_status"] == "ACTIVE")

# --- Test 4: Log activity against active stage ---
print("\n[4] Log fertilizer activity")
r = client.post(
    f"/api/v1/crop-cycles/{CYCLE_ID}/activities",
    headers=HEADERS,
    json={
        "activity_type": "FERTILIZER",
        "input_code": "DAP",
        "input_name": "DAP 50kg",
        "quantity": 2.0,
        "quantity_unit": "BAG",
        "cost_amount": 2700.00,
        "activity_date": "2026-06-20",
        "gps_lat": 26.79,
        "gps_lng": 82.19,
    },
)
test("Activity logged", r.status_code == 201)
activity = r.json()
test("Linked to active stage", activity["stage_code"] == stages[0]["code"])
test("Cost tracked", float(activity["cycle_total_input_cost"]) == 2700.0)
test("Events published", "crop_activity_logged.v1" in activity["events_published"])

# --- Test 5: Log second activity (cost accumulates) ---
print("\n[5] Log irrigation activity (cost accumulates)")
r = client.post(
    f"/api/v1/crop-cycles/{CYCLE_ID}/activities",
    headers=HEADERS,
    json={
        "activity_type": "IRRIGATION",
        "quantity": 1.0,
        "quantity_unit": "SESSION",
        "cost_amount": 500.00,
        "activity_date": "2026-06-22",
    },
)
test("Second activity logged", r.status_code == 201)
test("Cost accumulated", float(r.json()["cycle_total_input_cost"]) == 3200.0)

# --- Test 6: Complete first stage ---
print("\n[6] Complete first stage")
r = client.patch(
    f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_1_ID}",
    headers=HEADERS,
    json={"action": "COMPLETE", "gps_lat": 26.79, "gps_lng": 82.19},
)
test("Stage completed", r.status_code == 200)
result = r.json()
test("Stage status is COMPLETED", result["new_status"] == "COMPLETED")
test("crop_stage_completed event published", "crop_stage_completed.v1" in result["events_published"])

# --- Test 7: Start and complete second stage ---
if STAGE_2_ID:
    print("\n[7] Start + complete second stage")
    r = client.patch(
        f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_2_ID}",
        headers=HEADERS,
        json={"action": "START"},
    )
    test("Stage 2 started", r.status_code == 200)

    r = client.patch(
        f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_2_ID}",
        headers=HEADERS,
        json={"action": "COMPLETE"},
    )
    test("Stage 2 completed", r.status_code == 200)

# --- Test 8: Skip remaining stages (simulate partial tracking) ---
print("\n[8] Skip remaining stages")
for stage in stages[2:]:
    r = client.patch(
        f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{stage['id']}",
        headers=HEADERS,
        json={"action": "SKIP", "skip_reason": "Season ended early"},
    )
    test(f"Stage {stage['code']} skipped", r.status_code == 200)

# Check final cycle status
final_result = r.json() if stages[2:] else result
test("Cycle status is COMPLETED", final_result["cycle_status"] == "COMPLETED",
     f"Got: {final_result['cycle_status']}")

# --- Test 9: Can't transition a completed stage ---
print("\n[9] Can't re-start a completed stage")
r = client.patch(
    f"/api/v1/crop-cycles/{CYCLE_ID}/stages/{STAGE_1_ID}",
    headers=HEADERS,
    json={"action": "START"},
)
test("Completed stage rejects START", r.status_code == 409)

# --- Test 10: Audit chain has crop events ---
print("\n[10] Audit chain integrity")
from sqlalchemy import text
from app.core.database import engine

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT action FROM audit_chain
        WHERE tenant_id = :tid AND entity_type IN ('crop_cycle', 'crop_stage', 'crop_activity')
        ORDER BY id
    """), {"tid": TENANT_ID}).fetchall()
    actions = [r[0] for r in result]
    test("CROP_CYCLE_CREATED in audit", "CROP_CYCLE_CREATED" in actions)
    test("STAGE_START in audit", "STAGE_START" in actions)
    test("STAGE_COMPLETE in audit", "STAGE_COMPLETE" in actions)
    test("ACTIVITY_LOGGED in audit", "ACTIVITY_LOGGED" in actions)
    test("Multiple audit entries", len(actions) >= 5, f"{len(actions)} entries")

# --- Summary ---
print(f"\n{'=' * 60}")
print("🟢 Crop cycle operational loop validated!")
print("   Create → Start → Activity → Complete → Skip → Audit")
print(f"{'=' * 60}")
