"""Quick integration test: start server, hit endpoints, verify responses."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"
results = []


def test(name, response, expected_status=200, min_items=None):
    ok = response.status_code == expected_status
    detail = f"HTTP {response.status_code}"
    if ok and min_items is not None:
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        ok = len(items) >= min_items
        detail += f", {len(items)} items"
    status = PASS if ok else FAIL
    results.append(ok)
    print(f"  {status} {name} — {detail}")
    if not ok:
        print(f"       Response: {response.text[:200]}")


print("=" * 60)
print("API INTEGRATION TESTS")
print("=" * 60)

# Health
print("\n[Health]")
test("GET /health", client.get("/health"))

# Geography cascade
print("\n[Geography]")
r = client.get("/api/v1/master-data/geography/states")
test("GET states", r, min_items=1)
states = r.json()
state_id = states[0]["id"] if states else None

if state_id:
    r = client.get(f"/api/v1/master-data/geography/districts?state_id={state_id}")
    test("GET districts (UP)", r, min_items=70)
    districts = r.json()
    district_id = districts[0]["id"] if districts else None

    if district_id:
        r = client.get(f"/api/v1/master-data/geography/blocks?district_id={district_id}")
        test("GET blocks", r, min_items=1)
        blocks = r.json()
        block_id = blocks[0]["id"] if blocks else None

        if block_id:
            r = client.get(f"/api/v1/master-data/geography/villages?block_id={block_id}")
            test("GET villages", r, min_items=1)

# Fuzzy search
r = client.get("/api/v1/master-data/geography/villages/search?q=lucknow")
test("GET village search 'lucknow'", r, min_items=1)

r = client.get("/api/v1/master-data/geography/villages/search?q=rampur")
test("GET village search 'rampur'", r, min_items=1)

# Crops
print("\n[Crops]")
r = client.get("/api/v1/master-data/crops/categories")
test("GET crop categories", r, min_items=5)

r = client.get("/api/v1/master-data/crops")
test("GET all crops", r, min_items=5)

r = client.get("/api/v1/master-data/crops?season=KHARIF")
test("GET kharif crops", r, min_items=1)

crops = client.get("/api/v1/master-data/crops").json()
if crops:
    crop_id = crops[0]["id"]
    r = client.get(f"/api/v1/master-data/crops/{crop_id}/varieties")
    test("GET varieties", r, min_items=1)

    r = client.get(f"/api/v1/master-data/crops/{crop_id}/lifecycle-templates")
    test("GET lifecycle templates", r, min_items=1)

# Delta sync
print("\n[Sync]")
r = client.post("/api/v1/master-data/sync", json={"versions": {}})
test("POST sync (full)", r)
sync_data = r.json()
print(f"       Deltas: {len(sync_data.get('deltas', []))}, Versions: {sync_data.get('current_versions', {})}")

# Sync with current versions (should return 0 deltas)
r = client.post("/api/v1/master-data/sync", json={"versions": sync_data.get("current_versions", {})})
test("POST sync (no changes)", r)
sync_data2 = r.json()
print(f"       Deltas: {len(sync_data2.get('deltas', []))} (expected 0)")

# Summary
print(f"\n{'=' * 60}")
passed = sum(results)
total = len(results)
print(f"RESULT: {passed}/{total} tests passed")
if passed == total:
    print("🟢 All API endpoints working correctly!")
else:
    print("🔴 Some tests failed — check above")
print(f"{'=' * 60}")
