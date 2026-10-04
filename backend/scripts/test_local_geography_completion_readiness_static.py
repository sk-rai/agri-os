#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
AUDIT = (ROOT / "backend/scripts/audit_local_geography_completion_readiness.py").read_text()
DOC = (ROOT / "docs/local-geography-completion-readiness-2026-10-03.md").read_text()
checks = [
 (AUDIT,"local_geography_completion_readiness.v1","Audit schema is pinned"),
 (AUDIT,'"villages": 600647',"Canonical baseline is pinned"),
 (AUDIT,'"pin_linked_villages": 560151',"PIN baseline is pinned"),
 (AUDIT,'"effective_nwdp_villages": 487999',"Effective NWDP baseline is pinned"),
 (AUDIT,'"active_runtime_villages": 467397',"Runtime baseline is pinned"),
 (AUDIT,'"fully_resolved": 454996',"Resolved partition is pinned"),
 (AUDIT,'"pin_only": 105155',"PIN-only partition is pinned"),
 (AUDIT,'"nwdp_only": 33003',"NWDP-only partition is pinned"),
 (AUDIT,'"unresolved": 7493',"Unresolved partition is pinned"),
 (AUDIT,'"read_only": True',"Audit is read only"),
 (AUDIT,'ops["migration_head"] == "065"',"Migration 065 is required"),
 (AUDIT,"project_resolution_tests_cleaned","Test cleanup is required"),
 (AUDIT,"git_posture()","Git posture is captured"),
 (AUDIT,"redis_posture()","Redis posture is captured"),
 (AUDIT,"DATA_RECONCILIATION","Data reconciliation is classified"),
 (AUDIT,"DEFERRED_CLOUD","Cloud work is classified"),
 (AUDIT,"UNIMPLEMENTED_PRODUCT","Product work is classified"),
 (AUDIT,"ROADMAP_ONLY","Roadmap-only work is classified"),
 (AUDIT,"PROJECT_LOCAL_VILLAGE_ANDROID","Project-local Android work is retained"),
 (AUDIT,"HARVEST_SALE_NET_REALIZATION","Harvest economics is retained"),
 (AUDIT,"DECISION_NODES_PERENNIAL_ONBOARDING","Workflow hardening is retained"),
 (AUDIT,"INSURANCE_RISK_REVIEW","Risk boundary is retained"),
 (DOC,"# Local geography completion and engineering readiness — 2026-10-03","Checkpoint is documented"),
 (DOC,"## Future engineering work reconciled from repository roadmaps","Future work is reconciled"),
 (DOC,"not local-completion blockers","Deferred work is separated"),
]
for source,needle,label in checks:
 if needle not in source: raise AssertionError(f"{label}: missing {needle!r}")
 print("PASS "+label)
for needle,label in [("insert into ","No inserts"),("update geography_","No geography updates"),("delete from ","No deletes")]:
 if needle in AUDIT.lower(): raise AssertionError(label)
 print("PASS "+label)
print("LOCAL GEOGRAPHY COMPLETION READINESS STATIC CONTRACT PASSED")
