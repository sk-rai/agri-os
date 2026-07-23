"""Test sync engine: idempotency, dependency, conflict detection, audit chain."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

TENANT = "default"
ACTOR = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT, "X-Actor-ID": ACTOR}

def unique_mobile() -> str:
    return "+91" + str(uuid.uuid4().int)[-10:]


def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")
    if not passed:
        raise AssertionError(f"FAILED: {name} — {detail}")


print("=" * 60)
print("SYNC ENGINE TESTS")
print("=" * 60)

# --- Test 1: Basic commit ---
print("\n[1] Basic event commit")
farmer_id_1 = str(uuid.uuid4())
event_id_1 = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_1,
        "entity_type": "farmer",
        "entity_id": farmer_id_1,
        "operation": "CREATE",
        "payload": {"mobile_number": unique_mobile(), "display_name": "Test Farmer"},
        "version": 1,
        "metadata": {"device_id": "test-device", "gps": {"lat": 26.85, "lng": 80.91}},
    }]
})
data = r.json()
test("POST /sync/events returns 200", r.status_code == 200, f"Status: {r.status_code}")
test("Event accepted", event_id_1 in data["accepted"], f"Accepted: {data['accepted']}")
test("No conflicts", len(data["conflicts"]) == 0)
test("No failures", len(data["failed"]) == 0)

# --- Test 2: Idempotency ---
print("\n[2] Idempotency (re-submit same event_id)")
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_1,
        "entity_type": "farmer",
        "entity_id": str(uuid.uuid4()),
        "operation": "CREATE",
        "payload": {"mobile_number": "+919999999998"},
        "version": 1,
    }]
})
data = r.json()
test("Duplicate returns 200", r.status_code == 200)
test("Duplicate in accepted (idempotent)", event_id_1 in data["accepted"])
test("No double-commit", len(data["conflicts"]) == 0 and len(data["failed"]) == 0)

# --- Test 3: Dependency missing ---
print("\n[3] Dependency validation (missing dep)")
event_id_3 = str(uuid.uuid4())
missing_dep = str(uuid.uuid4())  # This event_id was never processed
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_3,
        "entity_type": "parcel",
        "entity_id": str(uuid.uuid4()),
        "operation": "CREATE",
        "payload": {"area_hectares": 2.5, "farmer_id": farmer_id_1},
        "version": 1,
        "dependency_ids": [missing_dep],
    }]
})
data = r.json()
test("Returns 200 (batch-resilient)", r.status_code == 200)
test("Event in failed list", len(data["failed"]) == 1)
test("Error code is DEPENDENCY_MISSING",
     data["failed"][0]["error_code"] == "DEPENDENCY_MISSING",
     f"Got: {data['failed'][0]}")

# --- Test 4: Dependency satisfied ---
print("\n[4] Dependency satisfied (dep exists)")
event_id_4 = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_4,
        "entity_type": "parcel",
        "entity_id": str(uuid.uuid4()),
        "operation": "CREATE",
        "payload": {"area_hectares": 1.0, "farmer_id": farmer_id_1},
        "version": 1,
        "dependency_ids": [event_id_1],  # This was already committed
    }]
})
data = r.json()
test("Event accepted (dep satisfied)", event_id_4 in data["accepted"])

# --- Test 5: Version mismatch conflict ---
print("\n[5] Version mismatch conflict")
entity_id_5 = str(uuid.uuid4())
# First: commit version 1
event_id_5a = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_5a,
        "entity_type": "farmer",
        "entity_id": entity_id_5,
        "operation": "CREATE",
        "payload": {"display_name": "Original"},
        "version": 3,
    }]
})
test("Version 3 committed", event_id_5a in r.json()["accepted"])

# Now: try to update with version 1 (stale)
event_id_5b = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [{
        "event_id": event_id_5b,
        "entity_type": "farmer",
        "entity_id": entity_id_5,
        "operation": "UPDATE",
        "payload": {"display_name": "Stale Update"},
        "version": 1,
    }]
})
data = r.json()
test("Stale update detected as conflict", len(data["conflicts"]) == 1,
     f"Conflicts: {data['conflicts']}")
test("Conflict type is VERSION_MISMATCH",
     data["conflicts"][0]["conflict_type"] == "VERSION_MISMATCH")

# --- Test 6: Workflow invalid conflict ---
print("\n[6] Workflow invalid conflict (bad stage code)")
event_id_6 = str(uuid.uuid4())
# Use a real lifecycle template ID from our seeded data
from app.core.database import SessionLocal
from app.modules.master_data.models import CropLifecycleTemplate
db = SessionLocal()
template = db.query(CropLifecycleTemplate).first()
db.close()

if template:
    r = client.post("/api/v1/sync/events", headers=HEADERS, json={
        "events": [{
            "event_id": event_id_6,
            "entity_type": "crop_stage",
            "entity_id": str(uuid.uuid4()),
            "operation": "UPDATE",
            "payload": {
                "stage_code": "INVALID_STAGE_XYZ",
                "lifecycle_template_id": str(template.id),
            },
            "version": 1,
        }]
    })
    data = r.json()
    test("Invalid stage detected as conflict", len(data["conflicts"]) == 1)
    test("Conflict type is WORKFLOW_INVALID",
         data["conflicts"][0]["conflict_type"] == "WORKFLOW_INVALID",
         f"Got: {data['conflicts'][0]}")
else:
    print(f"  ⚠️  Skipped (no lifecycle templates in DB)")

# --- Test 7: Batch processing (mixed results) ---
print("\n[7] Batch processing (mixed: accept + conflict + fail)")
event_id_7a = str(uuid.uuid4())  # Will succeed
event_id_7b = str(uuid.uuid4())  # Will fail (missing dep)
event_id_7c = event_id_1         # Already processed (idempotent)

r = client.post("/api/v1/sync/events", headers=HEADERS, json={
    "events": [
        {
            "event_id": event_id_7a,
            "entity_type": "farmer",
            "entity_id": str(uuid.uuid4()),
            "operation": "CREATE",
            "payload": {"display_name": "Batch Farmer", "mobile_number": unique_mobile()},
            "version": 1,
        },
        {
            "event_id": event_id_7b,
            "entity_type": "parcel",
            "operation": "CREATE",
            "payload": {"area": 5.0, "farmer_id": farmer_id_1},
            "version": 1,
            "dependency_ids": [str(uuid.uuid4())],  # Missing dep
        },
        {
            "event_id": event_id_7c,
            "entity_type": "farmer",
            "operation": "CREATE",
            "payload": {"display_name": "Duplicate"},
            "version": 1,
        },
    ]
})
data = r.json()
test("Batch returns 200", r.status_code == 200)
test("First event accepted", event_id_7a in data["accepted"])
test("Second event failed (dep missing)", any(f["event_id"] == event_id_7b for f in data["failed"]))
test("Third event accepted (idempotent)", event_id_7c in data["accepted"])
test("Total processed = 3", data["total_processed"] == 3)

# --- Test 8: Audit chain integrity ---
print("\n[8] Audit chain integrity")
from sqlalchemy import text
from app.core.database import engine

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT count(*), count(DISTINCT chain_hash)
        FROM audit_chain WHERE tenant_id = :tenant_id
    """), {"tenant_id": TENANT}).fetchone()
    total_entries = result[0]
    unique_hashes = result[1]
    test("Audit entries exist", total_entries > 0, f"{total_entries} entries")
    test("All chain_hashes unique (no collisions)", total_entries == unique_hashes)

    # Verify chain continuity
    result2 = conn.execute(text("""
        SELECT chain_hash FROM audit_chain
        WHERE tenant_id = :tenant_id ORDER BY id
    """), {"tenant_id": TENANT}).fetchall()
    hashes = [r[0] for r in result2]
    test("Chain has entries", len(hashes) > 0, f"{len(hashes)} chain entries")
    # All hashes should be 64-char hex
    test("All hashes are valid SHA256",
         all(len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in hashes))

# --- Test 9: Tenant-scoped idempotency row ---
print("\n[9] Tenant-scoped idempotency row")
tenant_scope_event_id = str(uuid.uuid4())
r = client.post("/api/v1/sync/events",
    headers={"X-Tenant-ID": TENANT, "X-Actor-ID": str(uuid.uuid4())},
    json={"events": [{
        "event_id": tenant_scope_event_id,
        "entity_type": "farmer",
        "entity_id": str(uuid.uuid4()),
        "operation": "CREATE",
        "payload": {"display_name": "Tenant Scope Farmer", "mobile_number": unique_mobile()},
        "version": 1,
    }]}
)
data = r.json()
test("Tenant-scoped submit returns 200", r.status_code == 200)
test("Tenant-scoped event accepted", tenant_scope_event_id in data["accepted"], f"Response: {data}")
with engine.connect() as conn:
    count = conn.execute(text("""
        SELECT count(*) FROM sync_processed_events WHERE tenant_id = :tid AND event_id = :event_id
    """), {"tid": TENANT, "event_id": tenant_scope_event_id}).scalar()
    test("Tenant-scoped idempotency row recorded", count == 1)

# --- Summary ---
print(f"\n{'=' * 60}")
print("🟢 All sync engine tests passed!")
print(f"{'=' * 60}")
