#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "web/src/app/(admin)/geography-layer-readiness/page.tsx").read_text()
PANEL = (ROOT / "web/src/components/admin/VillageResolutionEvidenceReviewPanel.tsx").read_text()
API = (ROOT / "backend/app/modules/master_data/api/geography.py").read_text()
SMOKE = (ROOT / "web/smoke/village_resolution_evidence_review_smoke.mjs").read_text()

checks = [
    ("Evidence item identity is returned", '"evidence_item_id"', API),
    ("Review button exists", "Review evidence", PAGE),
    ("Only eligible rows can be selected", 'row.review_eligibility !== "TWO_SESSION_REVIEW_ELIGIBLE"', PAGE),
    ("Collisions disable review", "row.source_collision === true", PAGE),
    ("Review panel is mounted", "VillageResolutionEvidenceReviewPanel", PAGE),
    ("Snapshot identity is returned", '"evidence_snapshot_id"', API),
    ("NWDP source hierarchy is returned", '"source_village_name"', API),
    ("Canonical and NWDP evidence are compared", "village-evidence-comparison", PANEL),
    ("Match rank is visible", "Match rank / basis", PANEL),
    ("Prior evidence is visible", "Prior candidate evidence", PANEL),
    ("Source reuse is visible", "Source reuse count", PANEL),
    ("Primary decision control exists", "Primary evidence decision", PANEL),
    ("Primary notes are required", "Primary review notes", PANEL),
    ("Second decision control exists", "Second evidence decision", PANEL),
    ("Second confirmation is explicit", "Second review confirmation", PANEL),
    ("Exact confirmation phrase is visible", "COMPLETE SECOND VILLAGE EVIDENCE REVIEW", PANEL),
    ("Same actor cannot use second control", "item.primary_reviewer_id === currentActorId", PANEL),
    ("No apply control exists", "REVIEW_ONLY_NO_APPLY", PANEL),
    ("UI states safety boundary", "never apply canonical geography", PANEL),
    ("Smoke uses two browser contexts", "proposerContext", SMOKE),
    ("Smoke proves self review rejection", "selfReview.status() !== 409", SMOKE),
    ("Smoke completes independent review", "Complete independent review", SMOKE),
    ("Smoke cleans review rows", "delete from geography_village_resolution_evidence_reviews", SMOKE),
    ("Smoke cleans temporary admins", "delete_test_admin", SMOKE),
]
for label, needle, source in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in ("Apply mapping", "Apply canonical", "Android visible"):
    if forbidden in PANEL:
        raise AssertionError(f"UI must not expose application: {forbidden}")
print("PASS UI exposes no geography application")
print("VILLAGE RESOLUTION EVIDENCE REVIEW UI STATIC CONTRACT PASSED")
