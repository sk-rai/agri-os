#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
page = (ROOT / "web/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
api = (ROOT / "web/src/lib/api.ts").read_text(encoding="utf-8")

picker = Path("web/src/components/geography-village-picker.tsx").read_text()
summary = Path("web/src/components/project-geography-summary.tsx").read_text()
boundary_page = Path("web/src/app/(admin)/nwdp-boundary-review/page.tsx").read_text()
csv_tools = Path("web/src/components/project-geography-scope-csv.tsx").read_text()
scope_history = Path(
    "web/src/components/project-geography-scope-audit.tsx"
).read_text()
activation_preflight = Path(
    "web/src/components/project-geography-activation-preflight.tsx"
).read_text()

checks = [
    ("API client exposes geography scope update", "updateGeographyScope" in api),
    ("API uses PATCH", 'method: "PATCH"' in api),
    ("API sends canonical village codes", "village_lgd_codes" in api),
    ("API sends an audit reason", "reason" in api),
    ("Projects page exposes scope editing", "Geography scope" in page),
    ("Projects page exposes save action", "Save geography scope" in page),
    ("Projects page exposes cancel action", "Cancel" in page),
    ("Projects page uses canonical village picker", "GeographyVillagePicker" in page),
    ("Project creation offers optional canonical geography", "Initial geography scope (optional)" in page and "createVillageCodes" in page),
    ("Project creation submits canonical village codes", "geography_scope: createVillageCodes.length" in page and "village_lgd_codes: createVillageCodes" in page),
    ("Project creation requires a geography audit reason", "Initial geography scope reason" in page and "createGeographyReason.trim().length < 3" in page),
    ("Project creation keeps empty geography supported", "createVillageCodes.length" in page and ": {}" in page),
    ("Project creation remains atomic", "complete form is submitted atomically" in page and "projectsApi.create" in page),
    ("Project creation API has a dedicated request type", "ProjectCreateRequest" in api and "geography_scope_reason?: string" in api),
    ("Picker hydrates saved LGD codes", ".resolveVillagesByLgdCodes(" in picker),
    ("Picker renders saved canonical village names", "village?.name" in picker),
    ("Picker renders saved hierarchy labels", "village.stateName" in picker and "village.districtName" in picker and "village.blockName" in picker),
    ("Picker loads canonical states", "geographyApi" in picker and ".listStates(" in picker),
    ("Picker loads state districts", "geographyApi" in picker and ".listDistricts(" in picker),
    ("Picker loads district blocks", ".listBlocks(" in picker and "Block / Sub-district" in picker),
    ("API exposes hierarchy bulk preview", "previewVillageBulkSelection" in api and "bulk-selection-preview" in api),
    ("Picker previews district villages", "Preview district villages" in picker and 'loadBulkPreview("DISTRICT")' in picker),
    ("Picker previews block villages", "Preview block villages" in picker and 'loadBulkPreview("BLOCK")' in picker),
    ("Bulk preview shows readiness totals", "eligible_village_count" in picker and "missing_village_count" in picker and "blocked_village_count" in picker),
    ("Bulk preview reports already selected villages", "alreadySelected" in picker and "Already selected" in picker),
    ("Bulk preview reports resulting scope size", "resultingCount" in picker and "project scope" in picker),
    ("Bulk preview requires explicit confirmation", "Confirm add" in picker and "applyBulkPreview" in picker),
    ("Bulk preview prevents partial oversized selection", "no partial selection will be applied" in picker and "can_select_entire_scope" in picker),
    ("Bulk preview respects remaining project capacity", "availableCapacity" in picker and "project slots remain" in picker),
    ("Bulk preview preserves audited save boundary", "Preview and selection do not write the database" in picker and "Save geography scope action remains required" in picker),
    ("Bulk preview supports cancellation", "Cancel bulk preview" in picker and "setBulkPreview(null)" in picker),
    ("Picker offers nationwide village-name search", "Search across India" in picker),
    ("Picker keeps hierarchy search as default", '"district" | "india"' in picker and '>("district")' in picker),
    ("Nationwide results show full hierarchy", "village.state_name" in picker and "village.district_name" in picker and "village.block_name" in picker),
    ("Picker performs district-scoped village search", "geographyApi" in picker and ".searchVillages(" in picker),
    ("Picker cancels stale searches", "AbortController" in picker and "controller.abort()" in picker),
    ("Picker supports keyboard result navigation", '"ArrowDown"' in picker and '"ArrowUp"' in picker and '"Enter"' in picker),
    ("Picker exposes combobox semantics", 'role="combobox"' in picker and 'role="listbox"' in picker and 'role="option"' in picker),
    ("Picker displays backend match type", "match_type.replaceAll" in picker),
    ("Picker exposes the 500-village limit", "MAX_SELECTED_VILLAGES = 500" in picker),
    ("Picker selects all displayed results", "selectAllDisplayed" in picker and "Select all displayed" in picker),
    ("Picker toggles selected search results", "toggleVillage" in picker),
    ("Picker supports keyboard bulk selection", "event.ctrlKey" in picker and "selectAllDisplayed();" in picker),
    ("Picker filters selected villages", "Filter selected villages" in picker and "filteredSelectedCodes" in picker),
    ("Picker guards remove all", "Confirm remove all" in picker and "confirmRemoveAll" in picker),
    ("Projects page exposes geography scope history", "ProjectGeographyScopeAudit" in page and "Scope history" in page),
    ("Scope history loads lazily per project", "scopeHistoryProjectId" in page and "geographyScopeAudit(projectId)" in scope_history),
    ("API exposes geography scope audit", "geographyScopeAudit" in api and "geography-scope/audit" in api),
    ("Scope history shows actor labels", "event.actor.display_name" in scope_history and "event.actor.role" in scope_history),
    ("Scope history shows event timestamps", "event.created_at" in scope_history and "toLocaleString" in scope_history),
    ("Scope history shows audited reasons", "event.reason" in scope_history),
    ("Scope history reports before and after counts", "before_village_count" in scope_history and "after_village_count" in scope_history),
    ("Scope history resolves canonical hierarchy", "change.state_name" in scope_history and "change.district_name" in scope_history and "change.block_name" in scope_history),
    ("Scope history filters change types", "Village change filter" in scope_history and "ADDED" in scope_history and "REMOVED" in scope_history and "UNCHANGED" in scope_history),
    ("Scope history filters boundary readiness", "Boundary readiness filter" in scope_history and "ELIGIBLE" in scope_history and "MISSING" in scope_history and "BLOCKED" in scope_history),
    ("Scope history is available for locked projects", 'disabled={!canCreateProjects || p.status !== "PLANNED"}' in page and "Scope history" in page),
    ("Scope history preserves runtime guardrails", "does not activate or promote boundary candidates" in scope_history and "change Android behavior" in scope_history),
    ("Projects page exposes geography CSV tools", "ProjectGeographyScopeCsv" in page),
    ("API exposes geography import preview", "previewGeographyScopeImport" in api and "import-preview" in api),
    ("API exposes geography scope export", "downloadGeographyScopeCsv" in api and "export.csv" in api),
    ("CSV import requires an LGD-code header", "village_lgd_code" in csv_tools and "lgd_code" in csv_tools),
    ("CSV import limits upload size", "MAX_CSV_BYTES" in csv_tools),
    ("CSV import shows accepted and rejected counts", "Accepted" in csv_tools and "Rejected" in csv_tools),
    ("CSV import reports duplicate codes", "Duplicate codes ignored" in csv_tools),
    ("CSV import reports malformed codes", "Malformed codes" in csv_tools),
    ("CSV import reports unknown villages", "Unknown canonical villages" in csv_tools),
    ("CSV preview loads accepted codes into picker", "onUseAcceptedCodes" in csv_tools and "normalized_village_lgd_codes" in csv_tools),
    ("CSV preview preserves audited save boundary", "performed no database write" in csv_tools and "Save geography scope" in page),
    ("Picker supports multiple selected villages", "Selected villages" in picker),
    ("Picker supports village removal", "removeVillage" in picker),
    ("Picker prevents duplicate village selection", "selectedCodes.has" in picker),
    ("Project cards expose activation preflight", "Activation preflight" in page and "ProjectGeographyActivationPreflightPanel" in page),
    ("Activation preflight loads lazily per project", "preflightProjectId" in page and "getProjectGeographyActivationPreflight(projectId)" in activation_preflight),
    ("API exposes project activation preflight", "getProjectGeographyActivationPreflight" in api and "activation-preflight" in api),
    ("Activation preflight shows ready and blocked decisions", "Ready for project activation" in activation_preflight and "Activation blocked by" in activation_preflight),
    ("Activation preflight shows geography counts", "configured_village_code_count" in activation_preflight and "villages_with_eligible_boundary" in activation_preflight and "villages_without_eligible_boundary" in activation_preflight),
    ("Activation preflight renders blocker details", "decision.blockers.map" in activation_preflight and "blocker.message" in activation_preflight),
    ("Activation preflight links boundary review", "Review project boundaries" in activation_preflight and "preflight.links.boundary_review" in activation_preflight),
    ("Activation preflight is advisory until confirmation", "preflight is advisory until explicit confirmation" in activation_preflight and "does not change project status" in activation_preflight),
    ("Activation preflight preserves runtime guardrails", "activate or promote boundary" in activation_preflight and "write runtime tables" in activation_preflight and "enable lookup" in activation_preflight and "change Android" in activation_preflight),
    ("Ready preflight exposes guarded activation", "Review project activation" in activation_preflight and "Confirm project activation" in activation_preflight),
    ("Project activation requires a reason", "Project activation reason" in activation_preflight and "activationReason.trim().length < 3" in activation_preflight),
    ("Project activation requires explicit confirmation", "confirmActivation" in activation_preflight and "Confirm PLANNED → ACTIVE" in activation_preflight),
    ("Project activation submits the preflight fingerprint", "preflight.decision.preflight_fingerprint" in activation_preflight and "preflight_fingerprint" in api),
    ("Project activation invokes guarded API", "projectsApi.activate" in activation_preflight and 'method: "POST"' in api),
    ("Project activation refreshes project cards", "onActivated" in activation_preflight and "void loadProjects()" in page),
    ("Blocked preflight exposes no activation action", "ready ? (" in activation_preflight),
    ("Activation confirmation warns geography locking", "Geography will become locked" in activation_preflight),
    ("Activation handles stale server rejection", "server" in activation_preflight.lower() and "stale decision" in activation_preflight),
    ("Project cards expose geography summary", "ProjectGeographySummary" in page),
    ("Projects page loads one batched readiness response", ".listProjectGeographyReadiness(" in page),
    ("Summary component makes no API requests", "useEffect" not in summary and "api<" not in summary),
    ("Summary resolves state and district labels", "state_name" in summary and "district_name" in summary),
    ("Summary shows eligible and missing boundaries", "villages_with_eligible_boundary" in summary and "villages_without_eligible_boundary" in summary),
    ("Summary exposes project-filtered boundary review", "Review boundaries" in summary and "project_id=" in summary),
    ("Boundary review accepts project deep links", 'get("project_id")' in boundary_page),
    ("Projects page requires a reason", "Change reason" in page),
    ("Projects page invokes guarded API", "projectsApi.updateGeographyScope" in page),
    ("Existing scope is loaded into editor", "village_lgd_codes" in page),
    ("PLANNED status governs editing", 'p.status !== "PLANNED"' in page),
    ("Locked-project guidance is rendered", "locked" in page.lower()),
]

print("=" * 72)
print("PROJECT GEOGRAPHY SCOPE EDITOR UI REGRESSION")
print("=" * 72)

failed = []
for label, passed in checks:
    print(("PASS" if passed else "FAIL"), label)
    if not passed:
        failed.append(label)

if failed:
    print("\nFailures:")
    for label in failed:
        print("-", label)
    raise SystemExit(1)

print("=" * 72)
print("PROJECT GEOGRAPHY SCOPE EDITOR UI REGRESSION PASSED")
print("=" * 72)
