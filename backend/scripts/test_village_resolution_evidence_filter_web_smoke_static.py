#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = (ROOT / "web/smoke/village_resolution_evidence_filter_smoke.mjs").read_text()
PAGE = (ROOT / "web/src/app/(admin)/geography-layer-readiness/page.tsx").read_text()

checks = [
    ("Smoke schema is pinned", "village_resolution_evidence_filter_web_smoke.v1", SMOKE),
    ("Rajasthan eligible total is pinned", "!== 98", SMOKE),
    ("Rajasthan collision total is pinned", "!== 15", SMOKE),
    ("Eligible rows exclude collisions", "item.source_collision !== false", SMOKE),
    ("Review tables are compared", "Read-only filter smoke changed review tables", SMOKE),
    ("Temporary admin is removed", "delete_test_admin", SMOKE),
    ("Evidence status control exists", "Village local evidence status", PAGE),
    ("Eligibility control exists", "Village review eligibility", PAGE),
    ("Collision control exists", "Village source collision", PAGE),
    ("Existing endpoint is observed", "/geography/village-resolution?", SMOKE),
]
for label, needle, source in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in ("page.request.post(", "page.request.put(", "page.request.delete("):
    if forbidden in SMOKE:
        raise AssertionError(f"Smoke must remain read only: {forbidden}")
print("PASS Browser smoke contains no mutation request")
print("VILLAGE RESOLUTION EVIDENCE FILTER WEB SMOKE STATIC CONTRACT PASSED")
