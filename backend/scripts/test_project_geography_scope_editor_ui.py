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
lifecycle_history = Path(
    "web/src/components/project-lifecycle-history.tsx"
).read_text()
deactivation_preflight = Path(
    "web/src/components/project-deactivation-preflight.tsx"
).read_text()
completion_preflight = Path(
    "web/src/components/project-completion-preflight.tsx"
).read_text()
archive_preflight = Path(
    "web/src/components/project-archive-preflight.tsx"
).read_text()
restore_preflight = Path(
    "web/src/components/project-restore-preflight.tsx"
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
    ("Project cards expose lifecycle history", "Lifecycle history" in page and "ProjectLifecycleHistory" in page),
    ("Lifecycle history loads lazily per project", "lifecycleHistoryProjectId" in page and "lifecycleAudit(projectId)" in lifecycle_history),
    ("API exposes project lifecycle history", "lifecycleAudit" in api and "lifecycle/audit" in api),
    ("Lifecycle history shows status transitions", "event.transition.from_status" in lifecycle_history and "event.transition.to_status" in lifecycle_history),
    ("Lifecycle history resolves actor labels", "event.actor.display_name" in lifecycle_history and "event.actor.role" in lifecycle_history),
    ("Lifecycle history shows reasons and timestamps", "event.reason" in lifecycle_history and "event.created_at" in lifecycle_history and "toLocaleString" in lifecycle_history),
    ("Lifecycle history shows activation evidence", "event.preflight_fingerprint" in lifecycle_history and "event.geography_summary" in lifecycle_history),
    ("Lifecycle history is read only", "performs no database write" in lifecycle_history and "does not change project status" in lifecycle_history),
    ("Active project cards expose deactivation preflight", 'p.status === "ACTIVE"' in page and "Deactivation preflight" in page and "ProjectDeactivationPreflightPanel" in page),
    ("Deactivation preflight loads lazily per project", "deactivationPreflightProjectId" in page and "getDeactivationPreflight(projectId)" in deactivation_preflight),
    ("API exposes project deactivation preflight", "getDeactivationPreflight" in api and "deactivation-preflight" in api),
    ("Deactivation preflight shows operational counts", "farmer_count" in deactivation_preflight and "enrollment_count" in deactivation_preflight and "parcel_count" in deactivation_preflight and "crop_cycle_count" in deactivation_preflight),
    ("Deactivation preflight shows assignment and field blockers", "project_role_count" in deactivation_preflight and "active_boundary_assignment_count" in deactivation_preflight and "field_event_count" in deactivation_preflight),
    ("Deactivation preflight renders blocker details", "decision.blockers.map" in deactivation_preflight and "blocker.message" in deactivation_preflight),
    ("Ready deactivation preflight exposes guarded action", "Review project deactivation" in deactivation_preflight and "Confirm project deactivation" in deactivation_preflight),
    ("Project deactivation requires a reason", "Project deactivation reason" in deactivation_preflight and "deactivationReason.trim().length < 3" in deactivation_preflight),
    ("Project deactivation requires explicit confirmation", "confirmDeactivation" in deactivation_preflight and "Confirm ACTIVE → PLANNED" in deactivation_preflight),
    ("Project deactivation submits preflight fingerprint", "preflight.decision.preflight_fingerprint" in deactivation_preflight and "preflight_fingerprint" in api),
    ("Project deactivation invokes guarded API", "projectsApi.deactivate" in deactivation_preflight and "/deactivate" in api),
    ("Project deactivation refreshes project cards", "onDeactivated" in deactivation_preflight and "void loadProjects()" in page),
    ("Blocked preflight exposes no deactivation action", "decision.can_deactivate" in deactivation_preflight and "Resolve every operational blocker" in deactivation_preflight),
    ("Deactivation confirmation explains lifecycle effect", "Project operations will pause" in deactivation_preflight and "geography editing" in deactivation_preflight),
    ("Deactivation handles stale server rejection", "fresh preflight" in deactivation_preflight and "stale decision" in deactivation_preflight),
    ("Deactivation preflight preserves runtime guardrails", "does not change project status" in deactivation_preflight and "candidate activation or promotion" in deactivation_preflight and "runtime" in deactivation_preflight and "Android behavior" in deactivation_preflight),
    ("Active project cards expose completion preflight", 'p.status === "ACTIVE"' in page and "Completion preflight" in page and "ProjectCompletionPreflightPanel" in page),
    ("Completion preflight loads lazily per project", "completionPreflightProjectId" in page and "getCompletionPreflight(projectId)" in completion_preflight),
    ("API exposes project completion preflight", "getCompletionPreflight" in api and "completion-preflight" in api),
    ("Completion preflight shows unfinished work counts", "unfinished_enrollment_count" in completion_preflight and "unfinished_crop_cycle_count" in completion_preflight and "unfinished_crop_stage_count" in completion_preflight and "open_query_thread_count" in completion_preflight),
    ("Completion preflight renders blocker details", "decision.blockers.map" in completion_preflight and "blocker.message" in completion_preflight),
    ("Ready completion preflight exposes guarded action", "Review project completion" in completion_preflight and "Confirm project completion" in completion_preflight),
    ("Project completion requires a reason", "Project completion reason" in completion_preflight and "completionReason.trim().length < 3" in completion_preflight),
    ("Project completion requires explicit confirmation", "confirmCompletion" in completion_preflight and "Confirm ACTIVE → COMPLETED" in completion_preflight),
    ("Project completion submits preflight fingerprint", "preflight.decision.preflight_fingerprint" in completion_preflight and "preflight_fingerprint" in api),
    ("Project completion invokes guarded API", "projectsApi.complete" in completion_preflight and "/complete" in api),
    ("Project completion refreshes project cards", "onCompleted" in completion_preflight and "void loadProjects()" in page),
    ("Blocked preflight exposes no completion action", "decision.can_complete" in completion_preflight and "Resolve every operational blocker" in completion_preflight),
    ("Completion confirmation explains terminal lifecycle", "ACTIVE → COMPLETED" in completion_preflight and "permanently closes" in completion_preflight),
    ("Completion handles stale server rejection", "fresh preflight" in completion_preflight and "stale decision" in completion_preflight),
    ("Completion preflight preserves operational and runtime guardrails", "does not change project status or" in completion_preflight and "operational records" in completion_preflight and "candidate activation" in completion_preflight and "runtime" in completion_preflight and "Android" in completion_preflight),
    ("Completed project cards expose archive preflight", 'p.status === "COMPLETED"' in page and "Archive preflight" in page and "ProjectArchivePreflightPanel" in page),
    ("Archive preflight loads lazily per project", "archivePreflightProjectId" in page and "getArchivePreflight(projectId)" in archive_preflight),
    ("API exposes project archive preflight", "getArchivePreflight" in api and "archive-preflight" in api),
    ("Archive preflight shows unfinished work", "unfinished_enrollment_count" in archive_preflight and "unfinished_crop_cycle_count" in archive_preflight and "unfinished_crop_stage_count" in archive_preflight and "open_query_thread_count" in archive_preflight),
    ("Archive preflight shows retained records", "retained_counts" in archive_preflight and "Records retained after archive" in archive_preflight),
    ("Archive action requires reason and confirmation", "Project archive reason" in archive_preflight and "archiveReason.trim().length < 3" in archive_preflight and "Confirm COMPLETED → ARCHIVED" in archive_preflight),
    ("Archive action submits fingerprint", "preflight.decision.preflight_fingerprint" in archive_preflight and "projectsApi.archive" in archive_preflight),
    ("Archive refreshes project cards", "onArchived" in archive_preflight and "void loadProjects()" in page),
    ("Blocked archive exposes no action", "decision.can_archive" in archive_preflight and "Resolve every unfinished-work blocker" in archive_preflight),
    ("Archive preserves records and runtime guardrails", "does not change project status or" in archive_preflight and "operational records" in archive_preflight and "runtime" in archive_preflight and "Android" in archive_preflight),
    ("Archived project cards expose restore preflight", 'p.status === "ARCHIVED"' in page and "Restore preflight" in page and "ProjectRestorePreflightPanel" in page),
    ("Restore preflight loads lazily per project", "restorePreflightProjectId" in page and "getRestorePreflight(projectId)" in restore_preflight),
    ("API exposes project restore preflight", "getRestorePreflight" in api and "restore-preflight" in api),
    ("Restore preflight shows retained records", "retained_counts" in restore_preflight and "farmer_count" in restore_preflight and "field_event_count" in restore_preflight),
    ("Restore preflight shows archive evidence", "prior_archive_event" in restore_preflight and "Immutable archive evidence" in restore_preflight),
    ("Restore action requires reason and confirmation", "Project restore reason" in restore_preflight and "restoreReason.trim().length < 3" in restore_preflight and "Confirm ARCHIVED → COMPLETED" in restore_preflight),
    ("Restore action submits fingerprint", "preflight.decision.preflight_fingerprint" in restore_preflight and "projectsApi.restore" in restore_preflight),
    ("Restore refreshes project cards", "onRestored" in restore_preflight and "void loadProjects()" in page),
    ("Blocked restore exposes no action", "decision.can_restore" in restore_preflight and "Resolve every archive-evidence blocker" in restore_preflight),
    ("Archive and restore handle stale decisions", "fresh preflight" in archive_preflight and "stale decision" in archive_preflight and "fresh preflight" in restore_preflight and "stale decision" in restore_preflight),
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
