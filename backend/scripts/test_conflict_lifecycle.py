"""E2E test: Full conflict lifecycle (detect → queue → list → resolve → audit).

Simulates the offline chaos scenario:
1. Device A commits farmer v3
2. Device B (offline) tries to update with stale v1
3. Server detects VERSION_MISMATCH → queues conflict
4. Operator lists pending conflicts
5. Operator resolves conflict (accept_client)
6. Audit chain records the resolution

This validates Task 4.3 (dashboard) and Task 4.2 (conflict resolution).
"""

import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

TENANT = "lifecycle-test-tenant"
ACTOR_A = str(uuid.uuid4())
ACTOR_B = str(uuid.uuid4())
OPERATOR = str(uuid.uuid4())
HEADERS_A = {"X-Tenant-ID": TENANT, "X-Actor-ID": ACTOR_A}
HEADERS_B = {"X-Tenant-ID": TENANT, "X-Actor-ID": ACTOR_B}
HEADERS_OP = {"X-Tenant-ID": TENANT, "X-Actor-ID": OPERATOR}


def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")
    if not passed:
        raise AssertionError(f"FAILED: {name}")


print("=" * 60)
print("E2E CONFLICT LIFECYCLE TEST")
print("=" * 60)

# --- Step 1: Device A commits farmer entity at version 3 ---
print("\n[1] Device A commits farmer (v3)")
entity_id = str(uuid.uuid4())
event_a = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS_A, json={
    "events": [{
        "event_id": event_a,
        "entity_type": "farmer",
        "entity_id": entity_id,
        "operation": "CREATE",
        "payload": {"display_name": "Ram Kumar", "village": "Ayodhya"},
        "version": 3,
        "metadata": {"device_id": "device-A", "gps": {"lat": 26.79, "lng": 82.19}},
    }]
})
test("Device A commit succeeds", r.status_code == 200 and event_a in r.json()["accepted"])

# --- Step 2: Device B (was offline) tries stale update (v1) ---
print("\n[2] Device B submits stale update (v1 — was offline)")
event_b = str(uuid.uuid4())
r = client.post("/api/v1/sync/events", headers=HEADERS_B, json={
    "events": [{
        "event_id": event_b,
        "entity_type": "farmer",
        "entity_id": entity_id,
        "operation": "UPDATE",
        "payload": {"display_name": "Ram Kumar Singh", "village": "Ayodhya"},
        "version": 1,
        "metadata": {"device_id": "device-B", "gps": {"lat": 26.79, "lng": 82.19}},
    }]
})
data = r.json()
test("Conflict detected", len(data["conflicts"]) == 1)
test("Conflict type is VERSION_MISMATCH",
     data["conflicts"][0]["conflict_type"] == "VERSION_MISMATCH")
conflict_event_id = data["conflicts"][0]["event_id"]

# --- Step 3: Check dashboard shows the conflict ---
print("\n[3] Dashboard shows pending conflict")
r = client.get("/api/v1/dashboard/operational", headers={"X-Tenant-ID": TENANT})
test("Dashboard returns 200", r.status_code == 200)
dashboard = r.json()
test("Conflicts pending = 1", dashboard["sync_health"]["conflicts_pending"] == 1)
test("Committed events > 0", dashboard["sync_health"]["committed"] > 0)
test("Audit chain has entries", dashboard["sync_health"]["audit_chain_length"] > 0)

# --- Step 4: Operator lists pending conflicts ---
print("\n[4] Operator lists pending conflicts")
r = client.get("/api/v1/sync/conflicts", headers=HEADERS_OP)
test("List conflicts returns 200", r.status_code == 200)
conflicts = r.json()
test("One conflict in list", len(conflicts) == 1)
conflict_id = conflicts[0]["id"]
test("Conflict entity_type is farmer", conflicts[0]["entity_type"] == "farmer")
test("Status is PENDING_REVIEW", conflicts[0]["status"] == "PENDING_REVIEW")

# --- Step 5: Operator views conflict detail ---
print("\n[5] Operator views conflict detail")
r = client.get(f"/api/v1/sync/conflicts/{conflict_id}", headers=HEADERS_OP)
test("Detail returns 200", r.status_code == 200)
detail = r.json()
test("Client payload present", "display_name" in detail["client_payload"])
test("Server payload has conflict info", detail["server_payload"] is not None)
test("Conflict type in detail", detail["conflict_type"] == "VERSION_MISMATCH")

# --- Step 6: Operator resolves conflict (accept client) ---
print("\n[6] Operator resolves conflict (ACCEPT_CLIENT)")
r = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers=HEADERS_OP,
    json={"strategy": "ACCEPT_CLIENT", "comment": "Farmer updated name in person"},
)
test("Resolution returns 200", r.status_code == 200)
resolution = r.json()
test("Status is resolved", resolution["status"] == "resolved")
test("Strategy is ACCEPT_CLIENT", resolution["strategy"] == "ACCEPT_CLIENT")

# --- Step 7: Verify conflict is no longer pending ---
print("\n[7] Verify conflict resolved")
r = client.get("/api/v1/sync/conflicts", headers=HEADERS_OP)
test("No more pending conflicts", len(r.json()) == 0)

# Check with status filter for resolved
r = client.get("/api/v1/sync/conflicts?status=RESOLVED_CLIENT", headers=HEADERS_OP)
test("Resolved conflict visible with filter", len(r.json()) == 1)

# --- Step 8: Dashboard updated ---
print("\n[8] Dashboard reflects resolution")
r = client.get("/api/v1/dashboard/operational", headers={"X-Tenant-ID": TENANT})
dashboard = r.json()
test("Conflicts pending = 0", dashboard["sync_health"]["conflicts_pending"] == 0)
test("Conflicts resolved = 1", dashboard["sync_health"]["conflicts_resolved"] == 1)

# --- Step 9: Audit chain records resolution ---
print("\n[9] Audit chain integrity after resolution")
from sqlalchemy import text
from app.core.database import engine

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT action, chain_hash FROM audit_chain
        WHERE tenant_id = :tid ORDER BY id
    """), {"tid": TENANT}).fetchall()
    actions = [r[0] for r in result]
    test("SYNC_COMMIT in audit", "SYNC_COMMIT" in actions)
    test("SYNC_CONFLICT in audit", "SYNC_CONFLICT" in actions)
    test("CONFLICT_RESOLVED in audit", "CONFLICT_RESOLVED" in actions)
    test("All hashes unique", len(set(r[1] for r in result)) == len(result))

# --- Step 10: Idempotency on resolution (can't resolve twice) ---
print("\n[10] Can't resolve same conflict twice")
r = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers=HEADERS_OP,
    json={"strategy": "ACCEPT_SERVER"},
)
test("Double-resolve returns 404", r.status_code == 404)

# --- Summary ---
print(f"\n{'=' * 60}")
print("🟢 Full conflict lifecycle validated!")
print("   Detect → Queue → List → Detail → Resolve → Audit → Idempotent")
print(f"{'=' * 60}")
