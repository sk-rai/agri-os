"""Regression test for modular crop taxonomy / propagation catalog."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


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


def codes(items):
    return {item["code"] for item in items}


print("=" * 72)
print("CROP CATALOG TAXONOMY / PROPAGATION REGRESSION")
print("=" * 72)

print("\n[1] Taxonomy catalog")
r = client.get("/api/v1/crop-catalog/taxonomy")
test("Taxonomy endpoint returns 200", r.status_code == 200, f"Status: {r.status_code}")
body = r.json()
test("Taxonomy schema version present", body["schema_version"] == "crop_taxonomy.v1")
node_codes = codes(body["nodes"])
for expected in ["AGRICULTURE", "FIELD_CROP", "CEREAL", "PULSE", "OILSEED", "SUGAR_CROP", "VEGETABLE", "FRUIT"]:
    test(f"Taxonomy includes {expected}", expected in node_codes)
edge_pairs = {(edge["parent_code"], edge["child_code"]) for edge in body["edges"]}
test("FIELD_CROP -> CEREAL edge exists", ("FIELD_CROP", "CEREAL") in edge_pairs)
test("HORTICULTURE -> VEGETABLE edge exists", ("HORTICULTURE", "VEGETABLE") in edge_pairs)

print("\n[2] Propagation types")
r = client.get("/api/v1/crop-catalog/propagation-types")
test("Propagation endpoint returns 200", r.status_code == 200, f"Status: {r.status_code}")
propagation_codes = codes(r.json())
for expected in [
    "DIRECT_SEEDED",
    "NURSERY_TRANSPLANT",
    "VEGETATIVE_SETT",
    "TUBER",
    "CUTTING",
    "SAPLING",
    "GRAFTED_PLANT",
    "BULB",
    "RHIZOME",
]:
    test(f"Propagation includes {expected}", expected in propagation_codes)

print("\n[3] Crop catalog items")
r = client.get("/api/v1/crop-catalog/crops/RICE")
test("Rice catalog returns 200", r.status_code == 200, f"Status: {r.status_code}")
rice = r.json()
rice_taxonomy = codes(rice["taxonomy"])
rice_propagation = codes(rice["propagation_options"])
test("Rice includes CEREAL taxonomy", "CEREAL" in rice_taxonomy)
test("Rice includes FIELD_CROP taxonomy", "FIELD_CROP" in rice_taxonomy)
test("Rice supports nursery transplant", "NURSERY_TRANSPLANT" in rice_propagation)
test("Rice supports direct seeded", "DIRECT_SEEDED" in rice_propagation)

r = client.get("/api/v1/crop-catalog/crops/SUGARCANE")
test("Sugarcane catalog returns 200", r.status_code == 200, f"Status: {r.status_code}")
sugarcane = r.json()
sugarcane_taxonomy = codes(sugarcane["taxonomy"])
sugarcane_propagation = codes(sugarcane["propagation_options"])
test("Sugarcane includes SUGAR_CROP taxonomy", "SUGAR_CROP" in sugarcane_taxonomy)
test("Sugarcane includes VEGETATIVE_PROPAGATED taxonomy", "VEGETATIVE_PROPAGATED" in sugarcane_taxonomy)
test("Sugarcane uses vegetative sett propagation", "VEGETATIVE_SETT" in sugarcane_propagation)

print("\n[4] Catalog filters")
r = client.get("/api/v1/crop-catalog/crops?taxonomy_code=CEREAL")
test("Taxonomy filter returns 200", r.status_code == 200, f"Status: {r.status_code}")
catalog = r.json()
catalog_codes = codes(catalog["crops"])
test("CEREAL filter includes Rice", "RICE" in catalog_codes)
test("CEREAL filter excludes Sugarcane", "SUGARCANE" not in catalog_codes)

r = client.get("/api/v1/crop-catalog/crops?propagation_type=VEGETATIVE_SETT")
test("Propagation filter returns 200", r.status_code == 200, f"Status: {r.status_code}")
catalog_codes = codes(r.json()["crops"])
test("VEGETATIVE_SETT filter includes Sugarcane", "SUGARCANE" in catalog_codes)

print(f"\n{'=' * 72}")
print("🟢 Crop catalog taxonomy/propagation validated")
print(f"{'=' * 72}")
