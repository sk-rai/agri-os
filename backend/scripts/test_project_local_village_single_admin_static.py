#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
API=(ROOT/"backend/app/modules/master_data/api/project_local_villages.py").read_text()
ROUTERS=(ROOT/"backend/app/modules/master_data/api/__init__.py").read_text()
BEHAVIOR=(ROOT/"backend/scripts/test_project_local_village_single_admin.py").read_text()
DOC=(ROOT/"docs/project-local-village-single-admin-authorization-2026-10-04.md").read_text()
UI=(ROOT/"web/src/components/admin/ProjectLocalVillageAuthorization.tsx").read_text()
PANEL=(ROOT/"web/src/components/admin/ProjectVillageResolutionPanel.tsx").read_text()
checks=[
("Authorization schema is pinned","project_local_village_authorization.v1",API),
("Retirement schema is pinned","project_local_village_retirement.v1",API),
("Generic local-addition endpoint exists",'"/projects/{project_id}/local-additions"',API),
("Project edit permission is required","AdminPermission.PROJECT_EDIT",API),
("Tenant project is resolved","project(db, project_id, x_tenant_id)",API),
("Single admin model is explicit","SINGLE_PROJECT_ADMIN",API),
("Exact authorization phrase is required","AUTHORIZE PROJECT LOCAL VILLAGE",API),
("Exact retirement phrase is required","RETIRE PROJECT LOCAL VILLAGE",API),
("At least one parent must match","any(parent_matches.values())",API),
("State match is evaluated",'"state": bool',API),
("District match is evaluated",'"district": bool',API),
("Tehsil or block match is evaluated",'"tehsil_or_block": bool',API),
("Only unmapped NWDP sources qualify","proposed_village_id is not null",API),
("Active runtime sources are excluded","runtime.is_active",API),
("Duplicate overlay is blocked","ACTIVE_PROJECT_LOCAL_VILLAGE_EXISTS",API),
("Project-local mode is used","PROJECT_LOCAL_ADDITION",API),
("Applied audit event is written","'APPLIED'",API),
("Rollback event is written","'ROLLED_BACK'",API),
("Global geography remains unchanged",'"global_geography_changed": False',API),
("Android exposure is not claimed",'"android_visible": False',API),
("Project visibility is explicit",'"project_visible": True',API),
("Project catalog route exists",'"/projects/{project_id}/available-villages"',API),
("Project catalog schema is pinned","project_available_villages.v1",API),
("Project catalog is tenant/project scoped","TENANT_PROJECT_ONLY",API),
("Canonical identities remain explicit","CANONICAL_LGD",API),
("Project-local identities remain explicit","PROJECT_LOCAL",API),
("Retired overlays are excluded","resolution.resolution_status='ACTIVE'",API),
("Manual-name submission is explicit","village_name_manual",API),
("Router is registered","project_local_villages_router",ROUTERS),
("Behavior verifies one admin",'event["approver_id"] is None',BEHAVIOR),
("Behavior verifies parent evidence",'any(result["parent_matches"].values())',BEHAVIOR),
("Behavior verifies cleanup","database_restored",BEHAVIOR),
("Behavior verifies catalog visibility","catalog_visible_before_retirement",BEHAVIOR),
("Behavior verifies retirement removal","catalog_hidden_after_retirement",BEHAVIOR),
("Single-admin panel is mounted","ProjectLocalVillageAuthorization",PANEL),
("Only eligible candidates show authorization","eligible_for_project_local_addition",UI),
("UI requires exact phrase","AUTHORIZE PROJECT LOCAL VILLAGE",UI),
("UI states project-only scope","Authorize for this project only",UI),
("UI preserves Android boundary","Android exposure is not enabled",UI),
("Policy is documented","one authenticated project administrator",DOC),
("Clock-drift rationale is documented","administrative drift",DOC),
("Global two-session boundary remains","global canonical",DOC),
("Android reader contract is documented","project_available_villages.v1",DOC),
("Android repository boundary is explicit","Android source code is not present",DOC),
]
for label,needle,source in checks:
 if needle not in source:raise AssertionError(f"{label}: missing {needle!r}")
 print(f"PASS {label}")
for forbidden in ("update geography_villages","insert into geography_villages","update geography_village_pin_links","insert into geography_village_pin_links"):
 if forbidden in API.lower():raise AssertionError(f"Global geography mutation found: {forbidden}")
print("PASS API contains no global geography mutation")
print("PROJECT LOCAL VILLAGE SINGLE-ADMIN STATIC CONTRACT PASSED")
