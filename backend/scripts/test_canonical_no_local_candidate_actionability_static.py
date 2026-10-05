#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "backend/scripts/report_canonical_no_local_candidate_actionability.py").read_text()
checks = [
    ("Schema is pinned", "canonical_no_local_candidate_actionability.v1"),
    ("Blocked baseline is pinned", "EXPECTED_BLOCKED = 7306"),
    ("State-source absence is pinned", '"NO_NWDP_STATE_SOURCE": 421'),
    ("District alignment is pinned", '"DISTRICT_IDENTITY_ALIGNMENT_REQUIRED": 824'),
    ("Block alignment is pinned", '"BLOCK_TEHSIL_ALIGNMENT_REQUIRED": 2122'),
    ("Same-parent research is pinned", '"SAME_PARENT_NAME_RESEARCH_REQUIRED": 3939'),
    ("Existing classification is reused", "canonical_unresolved_villages.csv"),
    ("Unmapped NWDP query is reused", "NWDP_UNMAPPED_SQL"),
    ("State-source absence is classified", "NO_NWDP_STATE_SOURCE"),
    ("District drift is classified", "DISTRICT_IDENTITY_ALIGNMENT_REQUIRED"),
    ("Block drift is classified", "BLOCK_TEHSIL_ALIGNMENT_REQUIRED"),
    ("Same-parent research is classified", "SAME_PARENT_NAME_RESEARCH_REQUIRED"),
    ("Fuzzy matching is prohibited", '"fuzzy_matching_used": False'),
    ("Automatic resolution is prohibited", '"automatic_resolution_authorized": False'),
    ("Database immutability is checked", '"database_counts_unchanged": before == after'),
    ("Exact actionability counts are checked", '"actionability_counts_exact"'),
    ("Android remains unchanged", '"android_changes_authorized": False'),
]
for label, needle in checks:
    if needle not in SOURCE:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
for forbidden in ("update geography_", "insert into geography_", "delete from geography_"):
    if forbidden in SOURCE.lower():
        raise AssertionError(f"Report contains prohibited mutation: {forbidden}")
print("PASS Report contains no geography mutation")
print("CANONICAL NO-LOCAL-CANDIDATE ACTIONABILITY STATIC CONTRACT PASSED")
