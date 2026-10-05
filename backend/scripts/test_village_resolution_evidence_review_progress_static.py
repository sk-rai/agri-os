#!/usr/bin/env python3
"""Static contract for full-queue village evidence review progress."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/modules/master_data/api/village_resolution_evidence_reviews.py").read_text()
TEST = (ROOT / "backend/scripts/test_village_resolution_evidence_review_workflow.py").read_text()
DOC = (ROOT / "docs/village-resolution-evidence-review-workflow-2026-10-04.md").read_text()

checks = [
    ("Existing queue endpoint is reused", "village_resolution_evidence_review_queue.v1", API),
    ("Eligible evidence is counted", "eligible_total", API),
    ("Unreviewed evidence is counted", "unreviewed", API),
    ("Pending second review is counted", "pending_second_review", API),
    ("Terminal states are counted", 'progress["completed_total"]', API),
    ("Progress never authorizes application", 'progress["application_authorized"] = False', API),
    ("Exact 125-row baseline is tested", 'pending_progress["eligible_total"] == 125', TEST),
    ("Pending transition is tested", 'pending_progress["pending_second_review"] == 1', TEST),
    ("Approval transition is tested", 'approved_progress["approved"] == 1', TEST),
    ("Full queue is documented", "125 collision-free, two-session-eligible", DOC),
    ("No cohort endpoint is introduced", "without introducing a cohort-specific endpoint", DOC),
]
for label, needle, source in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in (
    "update geography_villages",
    "insert into geography_village_pin_links",
    "insert into geography_boundary_runtime_crosswalks",
):
    if forbidden in API.lower():
        raise AssertionError(f"Progress API contains prohibited mutation: {forbidden}")
print("PASS Progress query contains no geography application")
print("VILLAGE RESOLUTION EVIDENCE REVIEW PROGRESS STATIC CONTRACT PASSED")
