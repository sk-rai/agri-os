#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = (ROOT / "backend/scripts/report_village_resolution_evidence_review_pilot.py").read_text()
DOC = (ROOT / "docs/village-resolution-evidence-review-pilot-2026-10-04.md").read_text()

checks = [
    ("Schema is pinned", "village_resolution_evidence_review_pilot.v1", REPORT),
    ("Pilot size is ten", "PILOT_SIZE = 10", REPORT),
    ("Only rank one is selected", "item.best_match_rank=1", REPORT),
    ("Only eligible rows are selected", "TWO_SESSION_REVIEW_ELIGIBLE", REPORT),
    ("Collisions are excluded", "item.source_collision=false", REPORT),
    ("Prior evidence is retained", '"prior_evidence_recorded"', REPORT),
    ("Existing reviews are excluded", "not exists", REPORT),
    ("Selection order is deterministic", "state.lgd_code::integer", REPORT),
    ("Snapshot hashes are recorded", "source_candidate_pairs_sha256", REPORT),
    ("Review fields remain blank", "review_fields_blank", REPORT),
    ("Database immutability is checked", "database_counts_unchanged", REPORT),
    ("No decisions are created", '"review_decisions_created": False', REPORT),
    ("Automatic apply is prohibited", '"automatic_application_authorized": False', REPORT),
    ("Pilot scope is documented", "ten-row pilot", DOC),
    ("Human review remains required", "human review", DOC),
    ("Generated artifacts are excluded", "must not be committed", DOC),
]
for label, needle, source in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in (
    "insert into geography_", "update geography_", "delete from geography_",
):
    if forbidden in REPORT.lower():
        raise AssertionError(f"Report contains prohibited mutation: {forbidden}")
print("PASS Pilot builder contains no geography mutation")
print("VILLAGE RESOLUTION EVIDENCE REVIEW PILOT STATIC CONTRACT PASSED")
