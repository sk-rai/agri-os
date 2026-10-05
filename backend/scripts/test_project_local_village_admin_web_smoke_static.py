#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SMOKE=(ROOT/"web/smoke/project_local_village_admin_smoke.mjs").read_text()
CATALOG=(ROOT/"web/src/components/admin/ProjectLocalVillageCatalog.tsx").read_text()
PANEL=(ROOT/"web/src/components/admin/ProjectVillageResolutionPanel.tsx").read_text()
DOC=(ROOT/"docs/project-local-village-single-admin-authorization-2026-10-04.md").read_text()
ALLOWLIST=(ROOT/"docs/android-endpoint-allowlist.md").read_text()
checks=[
("Smoke schema is pinned","project_local_village_admin_web_smoke.v1",SMOKE),
("One admin context is used","create_test_admin(db,role='ENTERPRISE_ADMIN'",SMOKE),
("Authorization is performed through UI","Authorize for this project only",SMOKE),
("Catalog visibility is required","catalog_visible_before_retirement:true",SMOKE),
("Retirement is performed through UI","Retire from this project",SMOKE),
("Catalog removal is required","catalog_hidden_after_retirement:true",SMOKE),
("Cross-tenant isolation is required","cross_tenant_hidden:true",SMOKE),
("Audit sequence is exact","APPLIED,ROLLED_BACK",SMOKE),
("Protected geography is compared","protectedCode",SMOKE),
("Temporary admin is removed","delete_test_admin",SMOKE),
("Resolution rows are cleaned","delete from geography_project_village_resolutions",SMOKE),
("Android remains hidden","android_visible:false",SMOKE),
("Catalog is mounted","ProjectLocalVillageCatalog",PANEL),
("Project-local candidates are selectable","eligible_for_project_local_addition",PANEL),
("Catalog is web-admin only","Web-admin project scope only",CATALOG),
("Rollback token is explicit","Rollback token for",CATALOG),
("Retirement confirmation is exact","RETIRE PROJECT LOCAL VILLAGE",CATALOG),
("Documentation says no Android change","No Android client or Maestro change is required",DOC),
("Playwright gate is documented","## Web-admin Playwright lifecycle",DOC),
]
for label,needle,source in checks:
 if needle not in source:raise AssertionError(f"{label}: missing {needle!r}")
 print(f"PASS {label}")
for forbidden,label in [
 ("update geography_villages","Smoke contains no canonical village mutation"),
 ("update geography_village_pin_links","Smoke contains no global PIN mutation"),
]:
 if forbidden in SMOKE.lower():raise AssertionError(label)
 print(f"PASS {label}")
if "project-village-resolutions/projects/{project_id}/available-villages" in ALLOWLIST:
 raise AssertionError("Admin village catalog must remain outside Android allowlist")
print("PASS Admin village catalog remains outside Android allowlist")
print("PROJECT LOCAL VILLAGE WEB-ADMIN SMOKE STATIC CONTRACT PASSED")
