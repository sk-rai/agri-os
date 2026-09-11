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

checks = [
    ("API client exposes geography scope update", "updateGeographyScope" in api),
    ("API uses PATCH", 'method: "PATCH"' in api),
    ("API sends canonical village codes", "village_lgd_codes" in api),
    ("API sends an audit reason", "reason" in api),
    ("Projects page exposes scope editing", "Geography scope" in page),
    ("Projects page exposes save action", "Save geography scope" in page),
    ("Projects page exposes cancel action", "Cancel" in page),
    ("Projects page uses canonical village picker", "GeographyVillagePicker" in page),
    ("Picker hydrates saved LGD codes", ".resolveVillagesByLgdCodes(" in picker),
    ("Picker renders saved canonical village names", "village?.name" in picker),
    ("Picker renders saved hierarchy labels", "village.stateName" in picker and "village.districtName" in picker and "village.blockName" in picker),
    ("Picker loads canonical states", "geographyApi" in picker and ".listStates(" in picker),
    ("Picker loads state districts", "geographyApi" in picker and ".listDistricts(" in picker),
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
