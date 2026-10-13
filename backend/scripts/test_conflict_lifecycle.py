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

import atexit
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Tenant
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

TENANT = f"sync-conflict-{uuid.uuid4().hex[:8]}"

_auth_db = SessionLocal()
try:
    _auth_db.add(Tenant(
        id=TENANT,
        name="Sync Conflict Lifecycle Tenant",
        type="ENTERPRISE",
    ))
    _auth_db.commit()
    _user_a, HEADERS_A = create_test_admin(
        _auth_db,
        tenant_id=TENANT,
    )
    _user_b, HEADERS_B = create_test_admin(
        _auth_db,
        tenant_id=TENANT,
    )
    _operator_user, HEADERS_OP = create_test_admin(
        _auth_db,
        tenant_id=TENANT,
    )
    _viewer_user, HEADERS_VIEWER = create_test_admin(
        _auth_db,
        tenant_id=TENANT,
        role="ADMIN_VIEWER",
    )
    ACTOR_A = str(_user_a.id)
    ACTOR_B = str(_user_b.id)
    OPERATOR = str(_operator_user.id)
    _auth_user_ids = [
        _user_a.id,
        _user_b.id,
        _operator_user.id,
        _viewer_user.id,
    ]
finally:
    _auth_db.close()


def _cleanup_auth_users():
    db = SessionLocal()
    try:
        db.execute(
            text("DELETE FROM sync_conflicts WHERE tenant_id = :tenant_id"),
            {"tenant_id": TENANT},
        )
        db.execute(
            text(
                "DELETE FROM sync_processed_events "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": TENANT},
        )
        db.execute(
            text("DELETE FROM audit_chain WHERE tenant_id = :tenant_id"),
            {"tenant_id": TENANT},
        )
        db.execute(
            text("DELETE FROM farmers WHERE tenant_id = :tenant_id"),
            {"tenant_id": TENANT},
        )
        db.commit()
        for user_id in _auth_user_ids:
            delete_test_admin(db, user_id)
        db.query(Tenant).filter(
            Tenant.id == TENANT
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


atexit.register(_cleanup_auth_users)


def unique_mobile() -> str:
    return "+91" + str(uuid.uuid4().int)[-10:]


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
        "payload": {"display_name": "Ram Kumar", "village": "Ayodhya", "mobile_number": unique_mobile()},
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

# --- Step 3: Check authenticated read boundaries and dashboard ---
print("\n[3] Authenticated read boundaries and dashboard")

missing_dashboard = client.get(
    "/api/v1/dashboard/operational",
    headers={"X-Tenant-ID": TENANT},
)
test(
    "Operational dashboard rejects missing bearer",
    missing_dashboard.status_code == 401,
    missing_dashboard.text,
)

dashboard_impersonation = client.get(
    "/api/v1/dashboard/operational",
    headers={**HEADERS_VIEWER, "X-Actor-ID": str(uuid.uuid4())},
)
test(
    "Operational dashboard rejects actor impersonation",
    dashboard_impersonation.status_code == 403,
    dashboard_impersonation.text,
)

missing_conflicts = client.get(
    "/api/v1/sync/conflicts",
    headers={"X-Tenant-ID": TENANT},
)
test(
    "Conflict administration rejects missing bearer",
    missing_conflicts.status_code == 401,
    missing_conflicts.text,
)

mobile_missing = client.get(
    "/api/v1/sync/conflicts/pending",
    headers={"X-Tenant-ID": TENANT},
)
test(
    "Android pending conflicts reject missing bearer",
    mobile_missing.status_code == 401,
    mobile_missing.text,
)

mobile_impersonation = client.get(
    "/api/v1/sync/conflicts/pending",
    headers={**HEADERS_B, "X-Actor-ID": str(uuid.uuid4())},
)
test(
    "Android pending conflicts reject actor impersonation",
    mobile_impersonation.status_code == 403,
    mobile_impersonation.text,
)

mobile_tenant_mismatch = client.get(
    "/api/v1/sync/conflicts/pending",
    headers={**HEADERS_B, "X-Tenant-ID": "sync-conflict-foreign"},
)
test(
    "Android pending conflicts reject tenant mismatch",
    mobile_tenant_mismatch.status_code == 403,
    mobile_tenant_mismatch.text,
)

mobile_owner = client.get(
    "/api/v1/sync/conflicts/pending",
    headers=HEADERS_B,
)
test(
    "Submitting human can read own pending conflict",
    mobile_owner.status_code == 200,
    mobile_owner.text,
)
mobile_owner_payload = mobile_owner.json()
test(
    "Own pending feed contains submitted conflict",
    any(
        item["event_id"] == conflict_event_id
        for item in mobile_owner_payload["conflicts"]
    ),
    str(mobile_owner_payload),
)

mobile_other = client.get(
    "/api/v1/sync/conflicts/pending",
    headers=HEADERS_A,
)
test(
    "Different human receives pending-conflict feed",
    mobile_other.status_code == 200,
    mobile_other.text,
)
test(
    "Different human cannot read submitter conflict",
    all(
        item["event_id"] != conflict_event_id
        for item in mobile_other.json()["conflicts"]
    ),
    mobile_other.text,
)

r = client.get("/api/v1/dashboard/operational", headers=HEADERS_VIEWER)
test("Dashboard returns 200", r.status_code == 200)
dashboard = r.json()
pending_before_resolution = dashboard["sync_health"]["conflicts_pending"]
resolved_before_resolution = dashboard["sync_health"]["conflicts_resolved"]
test("Conflicts pending >= 1", pending_before_resolution >= 1, f"Pending: {pending_before_resolution}")
test("Committed events > 0", dashboard["sync_health"]["committed"] > 0)
test("Audit chain has entries", dashboard["sync_health"]["audit_chain_length"] > 0)

# --- Step 4: Operator lists pending conflicts ---
print("\n[4] Operator lists pending conflicts")
r = client.get("/api/v1/sync/conflicts", headers=HEADERS_OP)
test("List conflicts returns 200", r.status_code == 200)
conflicts = r.json()
test("Conflict list includes pending items", len(conflicts) >= 1, f"Count: {len(conflicts)}")
matching_conflicts = [item for item in conflicts if item["event_id"] == conflict_event_id]
test("Conflict event_id present", len(matching_conflicts) == 1)
conflict = matching_conflicts[0]
conflict_id = conflicts[0]["id"]
test("Conflict entity_type is farmer", conflicts[0]["entity_type"] == "farmer")
test("Status is PENDING_REVIEW", conflicts[0]["status"] == "PENDING_REVIEW")

# --- Step 5: Operator views conflict detail ---
print("\n[5] Operator views conflict detail")
r = client.get(f"/api/v1/sync/conflicts/{conflict_id}", headers=HEADERS_VIEWER)
test("Detail returns 200", r.status_code == 200)
detail = r.json()
test("Client payload present", "display_name" in detail["client_payload"])
test("Server payload has conflict info", detail["server_payload"] is not None)
test("Conflict type in detail", detail["conflict_type"] == "VERSION_MISMATCH")

# --- Step 6: Operator resolves conflict (accept client) ---
print("\n[6] Operator resolves conflict (ACCEPT_CLIENT)")

missing_bearer = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers={"X-Tenant-ID": TENANT},
    json={"strategy": "ACCEPT_CLIENT"},
)
test(
    "Conflict resolution rejects missing bearer",
    missing_bearer.status_code == 401,
    missing_bearer.text,
)

view_only = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers=HEADERS_VIEWER,
    json={"strategy": "ACCEPT_CLIENT"},
)
test(
    "Conflict resolution rejects view-only administrator",
    view_only.status_code == 403,
    view_only.text,
)

actor_impersonation = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers={**HEADERS_OP, "X-Actor-ID": str(uuid.uuid4())},
    json={"strategy": "ACCEPT_CLIENT"},
)
test(
    "Conflict resolution rejects actor impersonation",
    actor_impersonation.status_code == 403
    and actor_impersonation.json().get("detail", {}).get("error")
    == "ACTOR_ID_MISMATCH",
    actor_impersonation.text,
)

tenant_mismatch = client.patch(
    f"/api/v1/sync/conflicts/{conflict_id}",
    headers={**HEADERS_OP, "X-Tenant-ID": "sync-conflict-tenant-mismatch"},
    json={"strategy": "ACCEPT_CLIENT"},
)
test(
    "Conflict resolution rejects tenant mismatch",
    tenant_mismatch.status_code == 403,
    tenant_mismatch.text,
)

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
remaining_conflicts = r.json()
remaining_matching = [item for item in remaining_conflicts if item["event_id"] == conflict_event_id]
test("Resolved conflict no longer pending", len(remaining_matching) == 0, f"Remaining matching: {remaining_matching}")

# Check with status filter for resolved
r = client.get("/api/v1/sync/conflicts?status=RESOLVED_CLIENT", headers=HEADERS_OP)
resolved_conflicts = r.json()
resolved_matching = [item for item in resolved_conflicts if item["event_id"] == conflict_event_id]
test("Resolved conflict visible with filter", len(resolved_matching) == 1, f"Resolved matching: {resolved_matching}")

# --- Step 8: Dashboard updated ---
print("\n[8] Dashboard reflects resolution")
r = client.get("/api/v1/dashboard/operational", headers=HEADERS_VIEWER)
dashboard = r.json()
pending_after_resolution = dashboard["sync_health"]["conflicts_pending"]
test("Conflicts pending decremented", pending_after_resolution == pending_before_resolution - 1, f"Before: {pending_before_resolution}, after: {pending_after_resolution}")
resolved_after_resolution = dashboard["sync_health"]["conflicts_resolved"]
test("Conflicts resolved incremented", resolved_after_resolution == resolved_before_resolution + 1, f"Before: {resolved_before_resolution}, after: {resolved_after_resolution}")

# --- Step 9: Audit chain records resolution ---
print("\n[9] Audit chain integrity after resolution")
from app.core.database import engine

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT action, chain_hash, actor_id FROM audit_chain
        WHERE tenant_id = :tid ORDER BY id
    """), {"tid": TENANT}).fetchall()
    actions = [r[0] for r in result]
    test("SYNC_COMMIT in audit", "SYNC_COMMIT" in actions)
    test("SYNC_CONFLICT in audit", "SYNC_CONFLICT" in actions)
    test("CONFLICT_RESOLVED in audit", "CONFLICT_RESOLVED" in actions)
    test("All hashes unique", len(set(r[1] for r in result)) == len(result))
    resolution_audit = [
        row for row in result if row[0] == "CONFLICT_RESOLVED"
    ]
    test(
        "Conflict resolution audit records authenticated administrator",
        len(resolution_audit) == 1
        and str(resolution_audit[0][2]) == OPERATOR,
        resolution_audit,
    )

    resolved_by = conn.execute(text("""
        SELECT resolved_by
        FROM sync_conflicts
        WHERE tenant_id = :tid
          AND id = :conflict_id
    """), {
        "tid": TENANT,
        "conflict_id": conflict_id,
    }).scalar()
    test(
        "Conflict row records authenticated administrator",
        str(resolved_by) == OPERATOR,
        resolved_by,
    )

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
