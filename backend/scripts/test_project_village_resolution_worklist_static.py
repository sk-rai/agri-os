#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];S=(ROOT/'backend/scripts/report_project_village_resolution_worklist.py').read_text()
checks=[('project_village_resolution_worklist.v1','Schema is pinned'),('build_scope_village_sql','Existing project scope resolver is reused'),('P0_PROJECT_','Project gaps are prioritized'),('global_geography_change_authorized','Global mutation remains unauthorized'),('PROJECT_LOCAL_VILLAGE','Project-local identity is proposed'),('existing_core_override_sufficient','Existing override limitation is explicit'),('nwdp_boundary_actual_pin_absent','Missing NWDP PIN evidence is enforced'),('NO_NWDP_PIN_EVIDENCE_AVAILABLE_FOR_DIRECT_ANDROID_EXPOSURE','Android claim boundary is explicit'),('database_counts_unchanged','Database immutability is checked')]
for needle,label in checks:
 if needle not in S:raise AssertionError(label+': missing '+repr(needle))
 print('PASS '+label)
for term in ('insert into geography_','update geography_','delete from geography_'):
 if term in S.lower():raise AssertionError('Mutation found: '+term)
print('PASS No geography mutations');print('PROJECT VILLAGE RESOLUTION WORKLIST STATIC CONTRACT PASSED')
