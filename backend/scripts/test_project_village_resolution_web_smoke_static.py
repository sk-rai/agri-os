#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "web/smoke/project_village_resolution_smoke.mjs").read_text()
CHECKS = {
    "Smoke schema is versioned": 'project_village_resolution_web_smoke.v1',
    "Deterministic project is pinned": '0f7e0a6b-8472-5d6d-8a14-a9d000000001',
    "Temporary editor-capable admin is used": "role='ENTERPRISE_ADMIN'",
    "Live worklist endpoint is exercised": 'liveWorklistResponse=await context.request.get',
    "Project dropdown is exercised": 'getByLabel("Resolution project")',
    "Rendered rows are reconciled": 'Rendered row count mismatch',
    "Candidate search is exercised through UI": 'getByRole("button",{name:"Search NWDP"})',
    "Candidate result is selected": 'getByLabel("NWDP candidate",{exact:true}).selectOption',
    "Candidate endpoint schema is required": 'project_village_resolution_nwdp_candidates.v1',
    "Dry run is exercised through UI": 'getByRole("button",{name:"Validate dry run"})',
    "Dry run cannot write": 'dryRun.preview.would_write!==false',
    "Dry run cannot expose Android": 'dryRun.preview.would_be_android_visible!==false',
    "Apply boundary is probed": 'dry_run:false,confirm_apply:true',
    "Apply remains disabled": 'PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED',
    "Apply returns 503": 'applyResponse.status()!==503',
    "Database before and after is compared": 'JSON.stringify(before)!==JSON.stringify(after)',
    "Project resolution table is protected": 'geography_project_village_resolutions',
    "Global geography is protected": 'geography_villages',
    "Candidate and runtime state are protected": 'geography_boundary_crosswalk_candidates',
    "Project matches are protected": 'geography_boundary_project_matches',
    "Temporary admin is deleted": 'delete_test_admin',
}
for label, needle in CHECKS.items():
    if needle not in SOURCE:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")
print("PROJECT VILLAGE RESOLUTION WEB SMOKE STATIC CONTRACT PASSED")