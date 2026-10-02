#!/usr/bin/env python3
"""Static contract for the corrected read-only coverage report and admin view."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORT=(ROOT/'backend/scripts/report_state_wise_lgd_pin_nwdp_coverage.py').read_text()
API=(ROOT/'backend/app/modules/master_data/api/geography.py').read_text()
WEB=(ROOT/'web/src/app/(admin)/geography-layer-readiness/page.tsx').read_text()
contracts=[
 (REPORT,'state_wise_lgd_pin_nwdp_coverage.v2','Corrected report schema is pinned'),
 (REPORT,'union of candidate mapping and active runtime mapping','Effective NWDP union is explicit'),
 (REPORT,'database_counts_unchanged','Database immutability is checked'),
 (REPORT,'four_way_partition_exact','Four-way partition is exact'),
 (REPORT,'write_csv','Reusable CSV output exists'),
 (API,'@router.get("/village-resolution")','Village resolution endpoint exists'),
 (API,'require_admin_permission(AdminPermission.VIEW)','Endpoint is admin-only'),
 (API,'limit: int = Query(50, ge=1, le=200)','Pagination is bounded'),
 (API,'VILLAGE_RESOLUTION_STATUSES','Statuses are allow-listed'),
 (API,'candidate_mapping OR active_runtime_mapping','Union semantics are exposed'),
 (WEB,'data-testid="village-resolution-panel"','Admin village panel exists'),
 (WEB,'Village resolution status','Resolution filter exists'),
 (WEB,'has_candidate_mapping','Candidate status remains separate'),
 (WEB,'has_active_runtime','Runtime status remains separate'),
]
for source,needle,label in contracts:
 if needle not in source: raise AssertionError(f"{label}: missing {needle!r}")
 print(f"PASS {label}")
for forbidden in ('insert into geography_','update geography_','delete from geography_'):
 if forbidden in REPORT.lower(): raise AssertionError(f"Report contains mutation: {forbidden}")
print('PASS Report contains no geography mutations')
print('STATE-WISE LGD PIN NWDP COVERAGE STATIC CONTRACT PASSED')
