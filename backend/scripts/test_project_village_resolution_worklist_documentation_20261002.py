#!/usr/bin/env python3
from pathlib import Path
D=(Path(__file__).resolve().parents[2]/'docs/project-scoped-village-resolution-worklist-2026-10-02.md').read_text()
checks=[('project_village_resolution_worklist.v1','Schema is recorded'),('20,185 project-priority','Project total is recorded'),('145,651 total global','Global worklist is recorded'),('geography_core_layer_project_overrides','Existing override limitation is named'),('PROJECT_LOCAL_ADDITION','Project-local addition is designed'),('CANONICAL_ENRICHMENT','Canonical enrichment is designed'),('162,229 NWDP','Unmapped NWDP total is recorded'),('320 reuse a village LGD code','Code-reuse cohort is recorded'),('269 of those','Code-with-PIN cohort is recorded'),('zero NWDP boundary source rows contain an actual PIN','Absent PIN evidence is explicit'),('zero loaded NWDP demographic rows','Demographic PIN absence is explicit'),('identity_scope = PROJECT_LOCAL_VILLAGE','Android identity scope is explicit'),('must never appear in the unscoped global','Global isolation is required'),('Current Android exposure remains unauthorized','Android remains gated'),('Generated worklists are review evidence and are not committed','Generated outputs remain uncommitted')]
for needle,label in checks:
 if needle not in D:raise AssertionError(label+': missing '+repr(needle))
 print('PASS '+label)
print('PROJECT VILLAGE RESOLUTION DOCUMENTATION CONTRACT PASSED')
