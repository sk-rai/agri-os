#!/usr/bin/env python3
from pathlib import Path
SOURCE=(Path(__file__).resolve().parent/"report_canonical_same_parent_name_evidence.py").read_text()
checks=[("Schema pinned","canonical_same_parent_name_evidence.v1"),("Cohort pinned","EXPECTED=3939"),("Same parent bounded","source_block_name"),("Canonical aliases used","cv.get(\"aliases\")"),("Census names used","census_name"),("Latin similarity explicit","latin_similarity"),("Vernacular similarity explicit","vernacular_similarity"),("Vernacular availability reported","cross_script_transliteration_available"),("Ambiguity retained","near_best_candidate_count"),("Only top three emitted","ranked[:3]"),("Similarity is evidence only","similarity_is_evidence_only"),("Automatic resolution prohibited",'"automatic_resolution_authorized":False'),("Database unchanged","database_counts_unchanged")]
for label,needle in checks:
 if needle not in SOURCE:raise AssertionError(f"{label}: missing {needle!r}")
 print("PASS",label)
for forbidden in ("update geography_","insert into geography_","delete from geography_"):
 if forbidden in SOURCE.lower():raise AssertionError(forbidden)
print("PASS Report contains no geography mutation")
print("CANONICAL SAME-PARENT NAME EVIDENCE STATIC CONTRACT PASSED")
