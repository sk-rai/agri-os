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
No API currently inserts, updates, activates, retires, or rolls back a project
resolution row.

## Read-only NWDP candidate search

The project-resolution panel now searches NWDP source features by village name or source code within the selected canonical village hierarchy. Results expose source identity, match basis, existing canonical/runtime linkage, and eligibility for a future project-local addition. Selecting a candidate only feeds the existing validation dry run.

The search requires an active tenant project, an authenticated admin with project-scoped view permission, and a canonical village already within that project's effective scope. It remains read-only: apply is disabled, Android visibility is false, and canonical geography, PIN links, NWDP candidates, runtime boundaries, project matches, and project-resolution rows are unchanged.
