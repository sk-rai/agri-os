#!/usr/bin/env python3
"""Static contract for the Playwright evidence-review rehearsal."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = (ROOT / "web/smoke/village_resolution_evidence_review_pilot.mjs").read_text()
checks = [
    ("Pilot schema is pinned", "village_resolution_evidence_review_pilot_playwright.v1"),
    ("Pilot manifest is reused", "village_resolution_evidence_review_pilot.json"),
    ("Pilot size is ten", "rows.length !== 10"),
    ("Rank one is required", "row.best_match_rank !== 1"),
    ("Eligibility is required", 'row.review_eligibility !== "TWO_SESSION_REVIEW_ELIGIBLE"'),
    ("Collisions are excluded", "row.source_collision !== false"),
    ("Two temporary admins are created", "create_test_admin"),
    ("Distinct browser identities are used", "identities_are_distinct: true"),
    ("Primary review uses Playwright", "primaryApi.post"),
    ("Second review uses Playwright", "secondApi.post"),
    ("Application remains unauthorized", "result.application_authorized !== false"),
    ("Progress delta is exact", "delta.approved !== 10"),
    ("Four screenshots are captured", "04-approved-page.png"),
    ("Review rows are cleaned", "delete from geography_village_resolution_evidence_reviews"),
    ("Temporary admins are removed", "delete_test_admin"),
    ("Protected geography is compared", "cleanup.runtime !== setup.before.runtime"),
]
for label, needle in checks:
    if needle not in SMOKE:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
if "persistent_audit_records: true" in SMOKE:
    raise AssertionError("Rehearsal must not claim persistent audit records")
print("PASS Rehearsal restores review and identity state")
print("VILLAGE RESOLUTION EVIDENCE REVIEW PLAYWRIGHT REHEARSAL STATIC CONTRACT PASSED")
