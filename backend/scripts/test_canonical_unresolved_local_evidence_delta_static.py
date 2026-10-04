#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SCRIPT=ROOT/"backend/scripts/report_canonical_unresolved_local_evidence_delta.py";DOC=ROOT/"docs/canonical-unresolved-local-evidence-delta-2026-10-04.md"
def main():
 source=SCRIPT.read_text(encoding="utf-8");document=DOC.read_text(encoding="utf-8")
 checks=(("Schema is pinned",'SCHEMA_VERSION="canonical_unresolved_local_evidence_delta.v1"',source),("Canonical baseline is pinned",'"canonical_unresolved":7493',source),("Unmapped baseline is pinned",'"unmapped_sources":162229',source),("Candidate pairs are pinned",'"candidate_pairs":290',source),("Deterministic queue is pinned",'"deterministic":70',source),("High confidence queue is pinned",'"high_confidence":70',source),("Ambiguous queue is pinned",'"ambiguous":47',source),("Blocked queue is pinned",'"blocked":7306',source),("Canonical classification is reused","CLASSIFIED_SQL",source),("State-name fallback is retained","code_name.get((sn,vc),[])",source),("Unmapped query is reused","NWDP_UNMAPPED_SQL",source),("Normalization is deterministic","def norm(",source),("Fuzzy matching is prohibited",'"fuzzy_matching_used":False',source),("Automatic resolution is prohibited",'"automatic_resolution_authorized":False',source),("Database immutability is required",'"database_counts_unchanged":before==after',source),("Prior evidence is required",'"prior_evidence_present"',source),("Populations are distinguished","different populations",document),("Exact queues are documented","7,306",document),("Review is required","REVIEW_REQUIRED",document),("No-write boundary is documented","does not authorize",document))
 for label,needle,haystack in checks:
  if needle not in haystack:raise AssertionError(f"{label}: missing {needle!r}")
  print(f"PASS {label}")
 for needle in ("insert into geography_","update geography_","delete from geography_"):
  if needle in source.lower():raise AssertionError(f"Read-only script contains {needle!r}")
 print("PASS Report contains no geography mutations");print("CANONICAL UNRESOLVED LOCAL EVIDENCE DELTA STATIC CONTRACT PASSED");return 0
if __name__=="__main__":raise SystemExit(main())
