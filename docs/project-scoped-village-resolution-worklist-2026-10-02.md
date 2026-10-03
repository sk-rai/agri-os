# Project-scoped village resolution worklist — 2026-10-02

## Outcome

The read-only project_village_resolution_worklist.v1 audit passed against the current database. It reused the established project geography_scope resolver, made no database changes, and wrote review artifacts only under /tmp.

Current canonical resolution totals remain:

- 454,996 FULLY_RESOLVED villages;
- 105,155 PIN_ONLY villages;
- 33,003 NWDP_ONLY villages;
- 7,493 UNRESOLVED villages;
- 145,651 total global worklist rows.

There are 58 active projects. Six projects currently have canonical villages in their resolved project scope that need work, producing 20,185 project-priority rows. A village may occur in multiple project worklists because resolution is intentionally project scoped.

## Priority policy

Project rows precede equivalent global work: P0_PROJECT_P0 covers neither PIN nor NWDP, P0_PROJECT_P1 covers NWDP without PIN, and P0_PROJECT_P2 covers PIN without NWDP. Global P0, P1, and P2 retain the same order. No row authorizes canonical LGD, PIN-link, candidate, runtime, project-match, or Android writes.

## Existing override limitation

geography_core_layer_project_overrides is not a village identity override. It requires an existing canonical village_id and only changes effective Core climate-region resolution. It cannot represent an NWDP village absent from canonical LGD or add a project-local PIN/village option.

A future project-local entity must be separate from canonical geography and the climate override table. It needs tenant/project identity, optional canonical village and NWDP source-feature identities, a stable project-local village identity, local hierarchy labels, verified PIN evidence, immutable review history and rollback. Its modes are CANONICAL_ENRICHMENT and PROJECT_LOCAL_ADDITION. Neither mode changes geography_villages or global mappings.

## NWDP villages, PIN evidence, and canonical LGD

There are 162,229 NWDP boundary source features without effective LGD mapping:

- 320 reuse a village LGD code present in active canonical geography;
- 269 of those canonical villages already have active PIN links;
- zero NWDP boundary source rows contain an actual PIN property;
- zero loaded NWDP demographic rows have a non-empty village_pin_code_status.

The 320 code-reuse rows are reconciliation candidates, not new villages. The other 161,909 rows mix source-code drift, hierarchy/name mismatch, duplicates, and potentially additional settlements. Current data cannot call them PIN-backed NWDP villages.

## Android delivery boundary

Project-local villages can eventually reach Android without changing global geography, but only through a project-scoped API requiring project_id. Each option must state identity_scope = PROJECT_LOCAL_VILLAGE or CANONICAL_LGD, its project resolution ID, optional canonical identity, verified PIN evidence, NWDP evidence and project/tenant scope.

A project-local option must never appear in the unscoped global village or PIN lookup. Android caches must key it by project and must not write it back as canonical LGD.

Current Android exposure remains unauthorized because the loaded NWDP source has no actual PIN values for this cohort. A verified India Post/OGD link, existing canonical PIN link, or reviewed admin evidence is required before project-local activation.

## Reproduction

    venv/bin/python backend/scripts/report_project_village_resolution_worklist.py --output-dir /tmp/project-village-resolution-worklist-v1

Outputs include global/project CSV worklists, project summaries, an NWDP-without-effective-LGD research CSV and JSON audit. Generated worklists are review evidence and are not committed.

## Disabled-apply implementation foundation

Migration 062 adds geography_project_village_resolutions as a dedicated,
project-scoped identity and evidence table. The migration completed locally
with zero resolution rows and zero active rows.

The foundation exposes:

- a project-scoped, paginated, read-only worklist endpoint;
- a PROJECT_EDIT-protected validation endpoint;
- CANONICAL_ENRICHMENT and PROJECT_LOCAL_ADDITION validation modes;
- canonical project-membership checks;
- NWDP source eligibility checks;
- PIN syntax and active postal-reference evidence checks;
- an admin worklist and dry-run panel on Geography Layer Readiness.

Only dry_run=true and confirm_apply=false are accepted. Any apply request fails
closed with PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED and HTTP 503. A successful
preview always reports would_write=false and would_be_android_visible=false.
At that foundation milestone, no API inserted, updated, activated, retired, or
rolled back a project resolution row. The later guarded and two-session sections
below supersede that implementation status.

## Read-only NWDP candidate search

The project-resolution panel now searches NWDP source features by village name or source code within the selected canonical village hierarchy. Results expose source identity, match basis, existing canonical/runtime linkage, and eligibility for a future project-local addition. Selecting a candidate only feeds the existing validation dry run.

The search requires an active tenant project, an authenticated admin with project-scoped view permission, and a canonical village already within that project's effective scope. It remains read-only: apply is disabled, Android visibility is false, and canonical geography, PIN links, NWDP candidates, runtime boundaries, project matches, and project-resolution rows are unchanged.

## Guarded canonical-enrichment apply gate — 2026-10-03

Migration 063 adds append-only APPLIED and ROLLED_BACK audit events plus a partial unique index that prevents concurrent active canonical resolutions for the same tenant, project, and village. The server flag PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED defaults false.

When separately enabled, apply accepts only CANONICAL_ENRICHMENT. It requires project-edit permission, an exact confirmation phrase, a valid token belonging to a different active enterprise administrator in the same tenant, verified project membership and evidence, and no conflicting NWDP-to-canonical mapping. PROJECT_LOCAL_ADDITION remains disabled.

A successful apply writes only the project resolution and its immutable audit event. It does not change canonical LGD, global PIN links, NWDP candidates, runtime boundaries, project matches, or Android visibility. Rollback requires the stored rollback token, retires the project resolution, and appends a ROLLED_BACK event without deleting history or deactivating runtime geography.

The feature flag remains false after validation. No admin apply control or Android read path has been enabled.


## Two-session proposal and approval workflow — 2026-10-03

Migration 064 extends the immutable review history with PROPOSED and APPROVED
events and prevents more than one non-retired DRAFT, APPROVED, or ACTIVE canonical resolution for
the same tenant, project, and village.

The admin workflow is deliberately split across authenticated sessions:

1. a project editor validates the existing dry run and creates a DRAFT
   CANONICAL_ENRICHMENT proposal;
2. the proposing identity cannot approve that proposal;
3. a different authenticated ENTERPRISE_ADMIN reviews the evidence and appends
   the APPROVED event;
4. the read-only review queue exposes the full proposal and event history;
5. activation is offered only when the server reports
   PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED=true.

Proposal and approval do not require the activation flag because neither makes
a resolution active or visible to Android. Repository defaults keep the flag
false, so an approved proposal remains inert. When separately authorized,
activation requires its own exact confirmation phrase and writes only the
project-scoped resolution plus its APPLIED audit event. Immediate rollback
remains available through the stored rollback token and appends ROLLED_BACK.

PROJECT_LOCAL_ADDITION remains disabled. The workflow does not change canonical
LGD villages, global PIN links, NWDP candidate mappings, runtime boundaries,
project matches, or the unscoped Android geography API. The admin screen does
not accept a pasted approver token: independent approval uses the identity of
the separately authenticated browser session.


## Two-session browser smoke gate — 2026-10-03

The browser gate uses two independent Playwright browser contexts backed by two
temporary ENTERPRISE_ADMIN identities in the same tenant. The proposer validates
a canonical-enrichment dry run and creates a DRAFT through the admin screen.
The backend must reject that identity's self-approval attempt with HTTP 409.
The second authenticated browser loads the review queue and approves the same
proposal through the admin screen.

The expected event sequence is exactly PROPOSED then APPROVED. Because
PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED defaults false, the review
queue must report activation_enabled=false and the activation control must not
be rendered. The smoke compares protected global geography counts, confirms
Android visibility remains false, captures review evidence, and removes only
its temporary proposal, events, and admin identities.
