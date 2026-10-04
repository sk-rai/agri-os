#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend/alembic/versions/067_add_village_resolution_evidence_reviews.py").read_text()
API = (ROOT / "backend/app/modules/master_data/api/village_resolution_evidence_reviews.py").read_text()
TEST = (ROOT / "backend/scripts/test_village_resolution_evidence_review_workflow.py").read_text()

checks = [
    ("Migration revision is pinned", 'revision = "067"', MIGRATION),
    ("Migration follows snapshot foundation", 'down_revision = "066"', MIGRATION),
    ("Review table exists", "geography_village_resolution_evidence_reviews", MIGRATION),
    ("Immutable event table exists", "geography_village_resolution_evidence_review_events", MIGRATION),
    ("One review per snapshot item", "uq_village_evidence_review_item", MIGRATION),
    ("Distinct reviewers are constrained", "ck_village_evidence_distinct_reviewers", MIGRATION),
    ("Primary decisions are bounded", "ACCEPT_FOR_SECOND_REVIEW", API),
    ("Second decisions are bounded", "SECOND_DECISIONS", API),
    ("Only active snapshot evidence is reviewed", "snapshot.is_active=true", API),
    ("Collision rows are rejected", "EVIDENCE_ITEM_NOT_TWO_SESSION_ELIGIBLE", API),
    ("Enterprise second reviewer is required", "ENTERPRISE_ADMIN_SECOND_REVIEW_REQUIRED", API),
    ("Second reviewer differs", "SECOND_REVIEWER_MUST_DIFFER_FROM_PRIMARY", API),
    ("Confirmation phrase is exact", "COMPLETE SECOND VILLAGE EVIDENCE REVIEW", API),
    ("Queue is reusable", "village_resolution_evidence_review_queue.v1", API),
    ("Application remains unauthorized", '"application_authorized": False', API),
    ("Canonical geography remains unchanged", '"canonical_geography_changed": False', API),
    ("PIN links remain unchanged", '"pin_links_changed": False', API),
    ("Runtime remains unchanged", '"runtime_changed": False', API),
    ("Android remains unchanged", '"android_changed": False', API),
    ("Behavior verifies self-review rejection", "self_review.status_code == 409", TEST),
    ("Behavior restores database", "assert after == before", TEST),
]
for label, needle, source in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in (
    "update geography_villages", "insert into geography_village_pin_links",
    "insert into geography_boundary_runtime_crosswalks",
):
    if forbidden in API.lower():
        raise AssertionError(f"Workflow contains prohibited mutation: {forbidden}")
print("PASS Workflow contains no geography application")
print("VILLAGE RESOLUTION EVIDENCE REVIEW WORKFLOW STATIC CONTRACT PASSED")
