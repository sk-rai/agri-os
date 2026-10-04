#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_canonical_unresolved_single_candidate_review_packet.py"
DOC = ROOT / "docs/canonical-unresolved-single-candidate-review-packet-2026-10-04.md"


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    document = DOC.read_text(encoding="utf-8")
    checks = (
        ("Packet schema is pinned", 'SCHEMA_VERSION = "canonical_unresolved_single_candidate_review_packet.v1"', source),
        ("Source schema is pinned", 'SOURCE_SCHEMA = "canonical_unresolved_local_evidence_delta.v1"', source),
        ("Review total is pinned", '"review_rows": 140', source),
        ("Deterministic total is pinned", '"deterministic": 70', source),
        ("High-confidence total is pinned", '"high_confidence": 70', source),
        ("Rank-one total is pinned", '"rank_1": 51', source),
        ("Rank-three total is pinned", '"rank_3": 19', source),
        ("Rank-four total is pinned", '"rank_4": 70', source),
        ("Unique source total is pinned", "\"unique_sources\": 131", source),
        ("Collision groups are pinned", "\"collision_sources\": 6", source),
        ("Collision rows are pinned", "\"collision_rows\": 15", source),
        ("Collision eligibility is explicit", "CONFLICT_REVIEW_REQUIRED", source),
        ("Collision acceptance is prohibited", "\"collision_rows_can_be_accepted\": False", source),
        ("Two review sessions are explicit", '"second_review_required_for_acceptance": True', source),
        ("Automatic application is prohibited", '"automatic_application_authorized": False', source),
        ("Database access is absent", '"database_accessed": False', source),
        ("Review decisions remain blank", '"review_fields_blank"', source),
        ("Source hashes are recorded", '"candidate_pairs_sha256"', source),
        ("Primary decisions are bounded", '"ACCEPT_FOR_SECOND_REVIEW"', source),
        ("Review remains required", "No row is approved", document),
        ("Strength tiers remain distinct", "three evidence-strength tiers", document),
        ("Android remains unauthorized", "Android exposure", document),
        ("Generated packet is excluded", "must not be committed", document),
        ("Collision boundary is documented", "15 collision rows cannot be accepted", document),
    )
    for label, needle, haystack in checks:
        if needle not in haystack:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")
    lowered = source.lower()
    for needle in ("from sqlalchemy", "insert into geography_", "update geography_", "delete from geography_"):
        if needle in lowered:
            raise AssertionError(f"Read-only packet contains {needle!r}")
    print("PASS Packet contains no database or geography mutation")
    print("CANONICAL UNRESOLVED SINGLE-CANDIDATE REVIEW PACKET STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
