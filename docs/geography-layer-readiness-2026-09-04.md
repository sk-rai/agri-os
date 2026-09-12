# Geography layer readiness and enablement roadmap

Status date: 2026-09-12
Baseline purpose: committed readiness baseline after the geography matrix, admin endpoint, web page, project-boundary readiness, national boundary geometry validation, validation-metadata lifecycle proof, selected boundary runtime readiness, climate runtime dry-run, external API readiness, project geography-scope administration, audit-history visibility, hierarchy bulk selection, atomic project-creation geography, and the read-only project geography activation preflight completed on 2026-09-12.

## Executive decision

Use backend LGD and LGD village-to-pin-code mapping as the canonical runtime geography layer for Android, farmer onboarding, land profiles, and village/pin-code lookup.

Keep NWDP demographic profiles, NWDP boundary candidates, project boundary matching, selected boundary runtime promotion, climate runtime enablement, SOI/BharatAtlas reconciliation, and external provider activation behind admin/web visibility plus explicit dry-run/apply gates.

No Android behavior should change as a side effect of any geography enrichment unless a separate Android-intended change is explicitly approved.

## Current committed proof points

Recent committed baseline:

- bfe17fb test: update nwdp demographic regressions for full admin rollout
- 4805b16 docs: add geography layer readiness roadmap
- aa5907c feat: add geography layer readiness matrix report
- 178493a feat: report geography layer matrix gap accounting
- 8a0ea30 feat: expose geography layer readiness endpoint
- a19261c feat: add geography layer readiness admin page
- d57c358 test: authenticate geography layer readiness smoke
- 0e39a98 feat: add climate agro-ecology readiness report
- 3356b9b feat: show climate readiness on geography matrix page
- 840546a feat: resolve project geography scope in boundary readiness
- dd320d5 feat: show project boundary readiness in geography matrix
- f5b135f feat: resolve project geography scope in boundary dry-run
- 156b97d feat: add disabled project boundary apply guard
- 37c49d4 feat: add selected boundary runtime promotion readiness report
- c6e0ad8 feat: surface selected boundary runtime promotion readiness
- a29652d feat: add disabled selected boundary runtime promotion guard
- 4b39fa8 feat: add external API readiness report
- fd7d7e7 feat: surface external API readiness in geography matrix
- c929c1e feat: add climate runtime enablement dry-run plan
- e14d46b feat: add disabled climate runtime enablement guard
- aef1ae5 test: cover project scope to boundary assignment workflow
- 007175a feat: add searchable project village picker
- 94a9068 feat: hydrate project village selections
- 2235a0b feat: show project geography readiness
- 8a43f29 perf: batch project geography readiness
- 1d94115 feat: add nationwide village name search
- 6a41327 feat: improve village search quality
- 248e74f feat: add bulk project village selection
- 52c4d09 feat: add project geography scope CSV tools
- 89c9db6 docs: record project geography administration milestone
- e0bb396 feat: expose project geography scope history
- c8653b2 feat: add hierarchy project village selection
- a13d3e6 feat: configure geography during project creation

Known passing validations include:

- NWDP boundary regression runner passed.
- Geography layer readiness matrix regression passed.
- Geography layer readiness endpoint regression passed.
- Geography layer readiness web smoke passed.
- Climate/agro-ecology readiness report regression passed.
- Project boundary readiness report regression passed.
- Project boundary matching dry-run regression passed.
- Disabled project boundary apply guard regression passed.
- Selected boundary runtime promotion readiness regression passed.
- Disabled selected boundary runtime promotion guard regression passed.
- External API readiness report regression passed.
- Climate runtime enablement dry-run regression passed.
- Disabled climate runtime enablement apply guard regression passed.
- Geography village LGD bulk-lookup API regression passed.
- Geography village nationwide name/LGD search API regression passed.
- Project geography readiness batch API regression passed.
- Project geography-scope editor UI contract regression passed.
- Project geography-scope CSV import/export API regression passed.
- Project geography-scope audit API regression passed, including tenant isolation, actor resolution, canonical hierarchy, change classification, boundary-readiness classification, and read-only database proof.
- District/block village bulk-selection preview API regression passed with real selectable block, selectable district, and oversized district fixtures.
- Hierarchy bulk-selection UI contract regression passed.
- Authenticated Playwright smoke previewed and selected all 112 canonical Nancowry block villages client-side, proved zero writes before Save, then completed the existing audited scope, assignment, and rollback workflow.
- Project geography-scope history UI contract regression passed.
- Authenticated Playwright smoke proved lazy audit loading, actor/reason/time visibility, added/removed/unchanged filtering, eligible/missing/blocked filtering, and unchanged runtime/Android guardrails.
- Next.js optimized production build passed after the complete project-scope UI changes.
- Authenticated Playwright project-scope-to-boundary-assignment smoke passed.
- Project geography activation-preflight API regression passed for ready, missing, empty, unresolved, non-PLANNED, blocked/manual-review, unknown-project, and cross-tenant cases.
- Activation-preflight zero-write regression proved project status, boundary candidates, runtime tables, lookup, and Android behavior remained unchanged.
- Activation-preflight UI contract and optimized Next.js production build passed.
- Authenticated Playwright proved lazy activation-preflight loading with exactly one request and a ready decision for a canonically scoped project.
- The smoke proved village search, exact LGD ranking, hierarchy labels, stale-request cancellation, keyboard selection, bulk selection, selected-scope filtering, guarded remove-all, CSV invalid/valid preview, audited scope save, persistence, readiness summary, deep linking, CSV export, project-boundary assignment, rollback, and fixture cleanup.
- Smoke guardrails proved no candidate activation, candidate promotion, runtime eligibility, runtime lookup, or Android behavior change.

## Implemented committed surfaces

| Surface | Path | Mode | Current posture |
| --- | --- | --- | --- |
| State/district geography layer matrix report | `backend/scripts/report_geography_layer_readiness_matrix.py` | Read-only JSON/CSV | Implemented and regression-tested. |
| Matrix regression | `backend/scripts/test_geography_layer_readiness_matrix.py` | Read-only test | Validates summary, gaps, guardrails, required fields. |
| Admin readiness endpoint | `GET /api/v1/master-data/geography/layer-readiness` | Read-only API | Implemented behind admin auth. |
| Endpoint regression | `backend/scripts/test_geography_layer_readiness_endpoint.py` | Read-only test | Validates auth, scoped filters, rollups, guardrails. |
| Web admin page | `web/src/app/(admin)/geography-layer-readiness/page.tsx` | Read-only admin UI | Shows cross-layer state/district matrix and rollups. |
| Web smoke | `web/smoke/geography_layer_readiness_smoke.mjs` | Authenticated smoke | Validates page load and readiness payload. |
| Climate/agro-ecology readiness report | `backend/scripts/report_climate_agro_ecology_readiness.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| Climate runtime dry-run plan | `backend/scripts/plan_climate_agro_ecology_runtime_enablement_dry_run.py` | Dry-run only | Implemented; writes audit, no runtime enablement. |
| Climate disabled apply guard | `backend/scripts/apply_climate_agro_ecology_runtime_enablement_disabled.py` | Disabled apply guard | Implemented; rejects real apply and preserves guardrails. |
| Project boundary readiness report | `backend/scripts/report_project_boundary_readiness.py` | Read-only JSON/CSV | Implemented with geography_scope resolution. |
| Project boundary matching dry-run | `backend/scripts/plan_nwdp_boundary_project_matching_apply_dry_run.py` | Dry-run only | Implemented; resolves project geography scope. |
| Project boundary disabled apply guard | `backend/scripts/apply_nwdp_boundary_project_matching_disabled.py` | Disabled apply guard | Implemented; rejects broad real apply and writes audit. |
| Tiny-fixture project boundary apply | `backend/scripts/apply_nwdp_boundary_project_matching_tiny_fixture.py` | Fixture-only apply | Implemented; writes only `geography_boundary_project_matches`, proves idempotency and rollback, then returns DB counts to baseline. |
| Project geography-scope editor | `web/src/app/(admin)/projects/page.tsx` | Guarded admin UI | PLANNED projects can configure canonical LGD village scope through the existing audited PATCH. |
| Canonical village picker | `web/src/components/geography-village-picker.tsx` | Admin UI | Supports state/district search, nationwide name or exact-LGD search, hierarchy labels, saved-code hydration, stale-request cancellation, keyboard navigation, bulk selection, filtering, guarded removal, and a 500-village limit. |
| Village LGD bulk lookup | `backend/app/modules/master_data/api/geography.py` | Read-only API | Hydrates persisted LGD codes with canonical village, block, district, and state labels. |
| Nationwide village search | `backend/app/modules/master_data/api/geography.py` | Read-only API | Uses indexed exact-LGD, exact/prefix/substring name, and `pg_trgm` fuzzy matching with deterministic ranking and match-type evidence. |
| Batched project geography readiness | `backend/app/modules/master_data/api/geography.py` | Read-only API | Returns tenant-scoped project readiness in one request and avoids per-card boundary-preview requests. |
| Project geography summary | `web/src/components/project-geography-summary.tsx` | Read-only admin UI | Shows states, districts, eligible boundaries, missing boundaries, and a project-filtered boundary-review deep link. |
| Geography-scope CSV preview/export | `backend/app/modules/farmer/api.py`, `web/src/components/project-geography-scope-csv.tsx` | Read-only preview/export plus guarded apply handoff | Reports duplicate, malformed, unknown, and over-limit rows; exports canonical hierarchy; accepted codes still require the existing audited save. |
| Geography-scope CSV API regression | `backend/scripts/test_project_geography_scope_import_export_api.py` | Authenticated regression | Proves tenant scope, read-only preview, lock policy, canonical export, and exactly one audit event on guarded PATCH apply. |
| Geography-scope audit read model | `GET /api/v1/projects/{project_id}/geography-scope/audit` | Read-only tenant/project-scoped API | Returns only geography-scope events with actor labels, reasons, timestamps, before/after counts, canonical village hierarchy, change types, and current boundary readiness. |
| Geography-scope history panel | `web/src/components/project-geography-scope-audit.tsx` | Read-only admin UI | Loads lazily per project and filters changes by added, removed, unchanged, eligible, missing, or blocked status; it remains available for locked projects. |
| Geography-scope audit regression | `backend/scripts/test_project_geography_scope_audit_api.py` | Authenticated regression | Proves event isolation, actor resolution, ordered differences, canonical hierarchy, readiness classification, tenant isolation, and zero writes during reads. |
| District/block village bulk preview | `GET /api/v1/master-data/geography/villages/bulk-selection-preview` | Read-only admin API | Resolves all active canonical villages for one district or block, reports eligible/missing/blocked totals, and explicitly rejects silent selection of scopes over 500 villages. |
| Hierarchy bulk-selection controls | `web/src/components/geography-village-picker.tsx` | Preview-only admin selection UI | Loads blocks, previews district or block impact, reports duplicates and resulting size, requires confirmation, and refuses partial or over-capacity application. |
| Hierarchy bulk-preview regression | `backend/scripts/test_geography_village_bulk_selection_preview_api.py` | Authenticated regression | Proves hierarchy isolation, canonical labels, readiness accounting, invalid-scope rejection, explicit truncation disclosure, and zero protected-table writes. |
| Project scope-to-boundary Playwright smoke | `web/smoke/project_geography_scope_boundary_assignment_smoke.mjs` | Authenticated end-to-end smoke | Proves scope configuration through assignment and rollback while preserving runtime and Android guardrails. |
| Boundary geometry validation readiness | `backend/scripts/report_boundary_geometry_validation_readiness.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| National boundary geometry validation evidence | `docs/boundary-geometry-national-validation-evidence-2026-09-07.md` | Evidence baseline | Records 654,285 source features: 654,093 valid and 192 repairable invalid, with zero manual or CRS blockers. |
| Boundary validation metadata apply design | `docs/boundary-geometry-validation-metadata-apply-design-2026-09-07.md` | Design baseline | Defines scoped validation-status metadata writes, idempotency, audit/rollback, and strict runtime/Android separation. |
| Boundary validation metadata dry-run | `backend/scripts/plan_boundary_geometry_validation_metadata_dry_run.py` | Read-only JSON/CSV | Implemented; computes canonical geometry metadata and planned validation status without database writes. |
| Boundary validation metadata disabled guard | `backend/scripts/apply_boundary_geometry_validation_metadata_disabled.py` | Disabled apply guard | Implemented; validates scope, checksum, review, rollback, and admin gates while refusing every real write. |
| Tiny-fixture boundary validation metadata apply | `backend/scripts/apply_boundary_geometry_validation_metadata_tiny_fixture.py` | Fixture-only apply | Implemented; updates one controlled source-feature row, proves idempotency and exact rollback, and restores database counts to baseline. |
| Bounded state validation metadata rollout design | `docs/boundary-validation-metadata-bounded-state-rollout-design-2026-09-08.md` | Design baseline | Defines checksum-pinned state batches of at most 500 valid-without-repair rows, immutable audit evidence, atomic apply, and exact rollback while broad apply remains disabled. |
| Production-shaped bounded validation metadata apply | `docs/boundary-validation-metadata-production-apply-design-2026-09-09.md` | Design and disabled control | Records the production transaction, preflight, idempotency, rollback, and batch-approval contract. The existing bounded apply remains disabled. |
| Andaman bounded validation metadata batch 1 approval candidate | `docs/boundary-validation-metadata-andaman-batch-1-approval-candidate-2026-09-09.md` | Pending administrative review | Records the checksum-pinned 500-row candidate, expected accounting, rollback contract, prohibited mutations, and unresolved approval fields. It grants no write authorization. |
| Andaman bounded validation metadata batch 1 approval decision | `docs/boundary-validation-metadata-andaman-batch-1-approval-decision-2026-09-09.md` | Exact batch applied | The approved 500-row apply completed from commit `4165140`; 500 immutable active events record the change and the one-time authorization is consumed. Runtime eligibility, promotion, lookup, and Android changes remain prohibited. |
| Andaman bounded validation metadata batch 1 apply evidence | `docs/evidence/andaman-boundary-validation-metadata-batch-1-apply-2026-09-09.json` | Production evidence | Records the exact checksums, authorization identity, before/after counts, 500 source-row changes, 500 event writes, and unchanged downstream guardrails. |
| Bounded state validation metadata planner | `backend/scripts/plan_boundary_geometry_validation_metadata_bounded_state.py` | Read-only JSON/CSV | Implemented; deterministically selects checksum-pinned batches of at most 500 valid-without-repair rows with cursor continuation. |
| Validation metadata event schema | `backend/alembic/versions/058_add_boundary_validation_metadata_events.py` | Immutable audit schema | Implemented with apply-identity uniqueness, one-active-event-per-source enforcement, before/planned/after snapshots, and rollback evidence. |
| Bounded state validation metadata disabled guard | `backend/scripts/apply_boundary_geometry_validation_metadata_bounded_state_disabled.py` | Disabled apply guard | Implemented; verifies plan content checksum, source checksum, scope, approvals, event schema, and row policy while refusing every mutation. |
| Boundary geometry repair classification | `backend/scripts/report_boundary_geometry_repair_classification.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| Boundary geometry repair disabled guard | `backend/scripts/apply_boundary_geometry_repair_disabled.py` | Disabled apply guard | Implemented; rejects real repair/status/eligibility writes and writes audit. |
| Boundary geometry repair apply design | `docs/boundary-geometry-repair-apply-design-2026-09-07.md` | Design baseline | Added; defines repair taxonomy, mutation boundaries, audit/rollback policy, and runtime/Android guardrails. |
| Tiny-fixture boundary geometry repair apply | `backend/scripts/apply_boundary_geometry_repair_tiny_fixture.py` | Fixture-only apply | Implemented; writes only repair-event metadata, proves idempotency and rollback, and returns fixture rows to baseline. |
| Selected boundary runtime readiness | `backend/scripts/report_selected_boundary_runtime_promotion_readiness.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| Selected boundary runtime disabled guard | `backend/scripts/apply_selected_boundary_runtime_promotion_disabled.py` | Disabled apply guard | Implemented; rejects real apply and writes audit. |
| External API readiness report | `backend/scripts/report_external_api_readiness.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |

## Readiness matrix

| Layer | Current state | Runtime / Android | Admin / web | Next action |
| --- | --- | --- | --- | --- |
| LGD spine | 35 states/UTs, 778 districts, 7,061 blocks, 576,083 villages | Ready | Ready | Keep as canonical geography identity. |
| Village pin codes | 560,316 active matched links; 560,151 linked villages | Ready | Ready | Add periodic freshness/audit reporting. |
| NWDP demographics | 453,036 rows; 450,026 approved/active/promoted; 1,570 blocked; 0 remaining eligible | Keep disabled for Android | Ready | Admin/web preview only; expose duplicate-blocked diagnostics. |
| NWDP/GSI boundary staging | 654,285 raw candidates; 580,629 district-placeable matrix candidates | Not broadly ready | Ready for review | Continue review, geometry validation, and controlled promotion planning. |
| Boundary runtime | Existing tiny inactive pilot footprint: 1 set, 10 features, 10 crosswalks; active runtime counts remain 0 | Disabled | Pilot verification only | Validate geometries and source eligibility before any runtime promotion. |
| Project boundary matches | 0 active matches after regression rollback/cleanup | Broad/runtime apply disabled | Readiness plus guarded project-scoped assignment/rollback available | Allow only permission-checked assignment of VALIDATED direct-code candidates within exact project scope; keep broad batch apply and runtime lookup disabled. |
| Climate/agro-ecology | 50 active regions, 231 active mappings, 45 active crop-climate rules | Broad runtime disabled | Readiness/dry-run visible | Fill district/rule gaps before runtime activation. |
| SOI ABDB | Official reference, but staged extract has unsafe LGD/name mismatch posture | Not safe for direct runtime joins | Reference/review only | Build reviewed SOI-to-backend-LGD crosswalk. |
| BharatAtlas | Operational LGD-like boundary review source | Not authoritative by itself | Review/overlay source | Use with provenance caveats and review gates. |
| External APIs/providers | Provider surfaces inventoried; live execution not enabled by readiness work | Disabled unless already separately active | Readiness visible | Add per-provider policy/credential/rate-limit/failure-audit gates before activation. |

## State/district matrix baseline

The state/district geography layer matrix exposes 778 rows and summarizes cross-layer coverage. Current key totals:

- LGD village count: 576,083
- PIN link count: 560,316
- PIN linked village count: 560,151
- Demographic profile rows: 453,036
- Demographic active/promoted rows: 450,026
- Demographic remaining eligible rows: 0
- Boundary raw candidate count: 654,285
- Boundary district-placeable matrix candidate count: 580,629
- Boundary outside state/district matrix gap: 73,656
- Project boundary match count: 0
- Climate mapping count in matrix summary: 412
- Climate region count in matrix summary: 246
- Crop-climate rule count in matrix summary: 1,674

The matrix is read-only and records guardrails:

- `db_writes_attempted=false`
- `runtime_lookup_enabled=false`
- `android_behavior_changed=false`
- `lgd_geography_overwritten=false`
- `official_census_claimed_imported=false`

## LGD and pincode layer

LGD remains the spine of the application. It should drive:

- farmer profile geography
- agent/farmer village selection
- land profile village and pin-code mapping
- backend joins across administrative layers
- Android-facing lookup responses

The village PIN-code layer is runtime-ready for Android and farmer workflows. This is the only geography enrichment layer currently considered safe for Android/runtime use with LGD.

## NWDP demographic profile layer

The demographic rollout is complete for admin/web purposes.

Final accepted baseline:

- profile rows: 453,036
- active/promoted rows: 450,026
- approved rows: 450,026
- blocked duplicate-safe exclusions: 1,570
- remaining eligible rows: 0

Earlier intermediate reports may show different South Andamans counts or remaining eligible rows. Those states were superseded by the full admin rollout and duplicate-blocked cleanup. The accepted baseline is: all safe demographic profiles are approved/promoted/active for admin/web verification, and 0 remain promotion-eligible.

This layer must remain disabled for Android runtime lookup until a separate Android-intended change is approved.

## NWDP boundary layer

The boundary layer is staged and reviewable, but not broadly runtime-promoted.

Current raw candidate posture:

- raw candidate count: 654,285
- raw direct VLCode match count: 453,046
- raw auto-candidate count: 453,036
- raw manual-review count: 98,705
- raw blocked count: 102,534
- promoted candidate count: 0

Current matrix-placeable posture:

- matrix candidate count: 580,629
- matrix direct VLCode match count: 402,135
- matrix auto-candidate count: 402,125
- matrix manual-review count: 84,203
- matrix blocked count: 94,291
- outside matrix gap: 73,656

The selected boundary runtime promotion readiness report currently shows that selected runtime promotion is not ready because selected promotable count is 0, invalid geometry count is positive, and non-runtime-eligible source count is positive.

## Boundary geometry validation posture

Boundary geometry validation readiness is now implemented as both a standalone read-only report and a rollup in the admin matrix/page.

Current evidence posture:

- 654,275 database rows are `NOT_VALIDATED`, not confirmed invalid
- 10 database rows are `VALIDATED`
- national source-file validation covered all 654,285 features
- 654,093 source geometries are valid without repair
- 192 source geometries are repairable with in-memory `make_valid()`
- no feature requires manual repair, reimport, or CRS review
- runtime promotion, runtime lookup, and Android changes remain disabled

### Boundary validation metadata lifecycle proof

The validation-metadata workflow is now implemented through three separately
guarded stages:

- read-only dry-run committed in `faaa666`
- disabled broad-apply guard committed in `fa396ea`
- tiny-fixture apply committed in `110ce32`
- fixture source feature: `9a18114f-5350-5173-97df-f24e1e64c30b`
- source checksum:
  `46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591`
- first apply changed exactly one row from `NOT_VALIDATED` to `VALIDATED`
- canonical geometry hash, source bounding box, transformed bounding box, and
  transformed centroid were written
- repeated apply produced `IDEMPOTENT_NO_OP` and changed zero rows
- wrong-token rollback was rejected
- confirmed rollback restored the exact original row and national counts
- national counts returned to 654,275 `NOT_VALIDATED` and 10 `VALIDATED`
- source GeoJSON checksum remained unchanged
- runtime eligibility remained false
- candidates, runtime tables, runtime lookup, LGD geography, and Android
  behavior remained unchanged

Broad validation-metadata apply remains disabled. The fixture proof authorizes
neither national metadata application nor runtime boundary promotion.

### Bounded state validation metadata control proof

The bounded state control layer is now implemented without enabling real apply:

- rollout design committed in `93bd4a6`
- bounded read-only planner committed in `edfca74`
- planner formatting cleanup committed in `cf97886`
- immutable validation metadata event schema committed in `8496c39`
- checksum-hardened disabled bounded apply guard committed in `95b578b`
- Andaman batch 1 deterministically selects 500 rows
- batch 1 plan checksum:
  `822ed7575c67de714e1599de243d7ecbd77828471de308c1a087ff38de12ef4d`
- batch 1 advances the cursor to source feature index 506
- batch 2 deterministically selects the remaining 160 safe rows
- the combined batches contain 660 unique valid-without-repair rows
- all 9 repair-required rows are excluded
- repeated planning produces the same rows, batch identity, and checksum
- edited plan content is rejected with `PLAN_CONTENT_CHECKSUM_MISMATCH`
- validation event rows remain 0
- source-feature, candidate, runtime, LGD, lookup, and Android state remain
  unchanged
- fully confirmed bounded apply still exits non-zero by policy

The event schema is available for future controlled transaction evidence, but
its existence does not authorize metadata application. Broad and 500-row apply
remain disabled.

This report separates geometry repair planning from runtime promotion. Geometry validation/repair must be solved before selected boundary runtime promotion can move beyond disabled guards.

Boundary geometry repair classification is also now implemented and surfaced in the admin matrix/page.

Boundary geometry repair apply design: `docs/boundary-geometry-repair-apply-design-2026-09-07.md`

The classification report splits the boundary backlog into validation, repair/re-import, runtime eligibility review, missing village/crosswalk review, manual review, and policy exclusion buckets.

A disabled boundary geometry repair guard is committed. It requires explicit apply intent, state/district scope, geometry-repair policy flag, runtime-eligibility policy flag, rollback/supersession token, classification review, and admin confirmation, but still refuses real mutation by policy.

Tiny-fixture repair apply proof:

- committed in `361bf09`
- regression passed
- dedicated repair-event metadata is the only apply target
- idempotency and rollback are proved
- source geometry, validation status, and runtime eligibility are unchanged
- boundary candidates are neither promoted nor activated
- runtime tables and lookup remain unchanged
- LGD geography and Android behavior remain unchanged
- fixture repair-event rows return to baseline after cleanup

The guardrails remain:

- geometry repair attempted: false
- geometry validation status changed: false
- source runtime eligibility changed: false
- source features changed: false
- boundary candidates promoted: false
- boundary candidates activated: false
- runtime tables written: false
- runtime lookup enabled: false
- Android behavior changed: false
- LGD geography overwritten: false

## Selected boundary runtime promotion posture

Selected boundary runtime promotion is guarded and disabled.

Expected current posture:

- `selected_runtime_promotable_count=0`
- `invalid_geometry_count>0`
- `not_runtime_eligible_source_count>0`
- `ready_for_selected_runtime_promotion_dry_run=false`
- `ready_for_selected_runtime_promotion_apply=false`
- Android unchanged

The disabled apply guard enforces:

- no-apply invocation exits non-zero and writes audit
- missing state/district scope exits non-zero
- missing rollback/supersession plan exits non-zero
- even with apply/confirmation flags, real apply remains disabled
- JSON and CSV audit output
- DB runtime row counts unchanged

Guardrails remain:

- `db_writes_attempted=false`
- `runtime_tables_written=false`
- `runtime_lookup_enabled=false`
- `boundary_candidates_promoted=false`
- `boundary_candidates_activated=false`
- `android_behavior_changed=false`
- `lgd_geography_overwritten=false`

## Project boundary matching posture

- Project boundary apply design: `docs/project-boundary-matching-apply-design-2026-09-07.md`

Project boundary matching now has read-only readiness, scope resolution, dry-run planning, disabled broad-apply guard coverage, a green tiny-fixture apply path, and a guarded project-scoped assignment/rollback path for VALIDATED direct-code candidates.

Tiny-fixture apply proof:

- committed in `173d19b` and repaired in `b0b2ce8`
- regression: `NWDP BOUNDARY PROJECT MATCHING TINY FIXTURE APPLY REGRESSION PASSED`
- target table only: `geography_boundary_project_matches`
- idempotency proved by deterministic match IDs
- rollback/supersession proved by rollback token
- boundary candidates were not promoted or activated
- runtime boundary tables were not written
- lookup/runtime spatial matching stayed disabled
- Android behavior stayed unchanged
- regression cleanup returned DB counts to baseline

Current project-boundary readiness:

- active projects: 57
- non-empty geography-scope projects: 10
- projects with resolved LGD scope: 6
- projects ready for project-boundary dry-run: 5
- resolved project-scope villages: 123,505
- scope villages with eligible boundary candidates: 119,886
- scope villages without eligible boundary candidates: 3,619
- active project boundary matches: 0

Important scope rule:

- Broad state scope is used only when no narrower district/PIN/village scope is present.

The dry-run can select eligible direct-VLCode auto-candidates for scoped projects. A permission-checked admin/API path may now write and roll back project-scoped match history for an exact scoped village and a VALIDATED direct-code candidate. Broad or batch project-boundary apply remains disabled. Runtime tables, lookup enablement, candidate activation, candidate promotion, and Android behavior changes remain prohibited.

### Project geography-scope administration milestone — 2026-09-10

Nine commits completed the admin workflow from canonical village discovery through guarded project-boundary assignment:

1. `aef1ae5` added an authenticated Playwright workflow covering project geography-scope persistence, boundary assignment, rollback, immutable history, and unchanged runtime/Android guardrails.
2. `007175a` replaced manual scope entry with a reusable canonical village picker.
3. `94a9068` added LGD-code hydration so persisted selections render canonical village and hierarchy labels.
4. `2235a0b` added per-project geography and boundary-readiness summaries plus project-filtered boundary-review deep links.
5. `8a43f29` replaced per-card preview calls with one tenant-scoped batched readiness request and added tenant-isolation regression coverage.
6. `1d94115` added nationwide village-name search while retaining state/district search as the default workflow.
7. `6a41327` added exact-LGD search, deterministic ranking, backend match-type evidence, indexed query coverage, stale-request cancellation, keyboard navigation, and improved combobox semantics.
8. `248e74f` added checkbox-style result toggling, select-all-displayed, selected-scope filtering, guarded remove-all, keyboard bulk selection, and the explicit 500-village limit.
9. `52c4d09` added read-only CSV import preview and canonical CSV export. Preview reports duplicates, malformed codes, unknown villages, and limit violations. Accepted rows load into the picker but do not write the database; the existing permission-checked PATCH and audit reason remain mandatory.

Operational behavior now proved:

- canonical village names are searchable globally and within a district
- exact LGD codes rank first and expose match evidence
- saved project scopes hydrate to canonical hierarchy labels
- multiple villages can be selected and managed up to the 500-village API limit
- project cards use one batched readiness request
- readiness identifies eligible and missing boundary coverage
- boundary review accepts an exact project deep link
- CSV preview is read-only and CSV export includes canonical hierarchy
- project geography scope remains editable only under the existing edit policy
- applying scope creates exactly one immutable project configuration audit event
- validated direct-code project-boundary assignment and rollback work end to end
- fixture cleanup restores project, assignment-history, and audit counts to zero

Explicit non-effects retained throughout:

- no geography master overwrite
- no boundary candidate activation
- no boundary candidate promotion
- no boundary runtime-table write
- no runtime spatial lookup enablement
- no Android behavior change

This milestone makes project geography administration operationally usable without changing the broader boundary-runtime posture. Broad project-boundary apply remains independently gated.


### Project geography-scope audit-history milestone — 2026-09-11

The project administration workflow now exposes its existing immutable geography-scope audit records as an operational read model rather than raw configuration JSON.

Implemented behavior:

- a tenant- and project-scoped endpoint returns only `UPDATE_PROJECT_GEOGRAPHY_SCOPE` events
- actor UUIDs resolve to display names and roles without weakening tenant isolation
- events show timestamps, audited reasons, and before/after village counts
- village differences are classified as added, removed, or unchanged
- every resolvable LGD code includes canonical village, block, district, and state labels
- current boundary posture is classified with the same direct-code, validated-geometry eligibility policy used by project readiness
- villages can be filtered by change type and eligible, missing, or blocked boundary posture
- history loads only when an administrator opens the project card panel
- history remains visible when project editing is locked
- the generic runtime app-config audit endpoint remains unchanged

Regression evidence:

- authenticated API regression passed
- geography-scope editor UI contract regression passed
- optimized Next.js production build passed
- authenticated Playwright scope-to-assignment smoke passed
- the smoke verified lazy history loading and both filter dimensions
- fixture cleanup returned project, assignment-history, and audit counts to zero

The current database has blocked candidates in aggregate but no blocked candidate linked to a canonical village that satisfies the regression fixture query. The regression records this as an explicit skip while retaining executable blocked-classification logic and UI filter coverage.

Explicit non-effects:

- no geography-scope write occurs while reading history
- no boundary candidate is activated or promoted
- no boundary runtime table is written
- no runtime spatial lookup is enabled
- no Android behavior changes



### District/block project-village bulk-selection milestone — 2026-09-11

Project administrators can now preview and select complete canonical village sets under a district or block without weakening the existing project-scope write boundary.

Implemented behavior:

- the existing state and district hierarchy now continues into canonical blocks/sub-districts in the picker
- a read-only endpoint accepts exactly one district or block scope
- previews return canonical village, block, district, and state labels
- previews classify every returned village as eligible, missing, or blocked using the established project-boundary readiness policy
- preview summaries report total, returned, eligible, missing, and blocked village counts
- the picker reports villages already selected, new additions, remaining capacity, and resulting project-scope size
- explicit confirmation is required before adding a complete hierarchy scope
- scopes over 500 villages are reported as oversized and cannot be partially or silently selected
- otherwise-valid scopes that exceed remaining project capacity are also rejected without partial selection
- preview and client-side selection do not write the project
- the existing permission-checked and reason-audited `Save geography scope` action remains the only persistence boundary

Regression evidence:

- a selectable block returned all canonical villages
- a selectable district returned all canonical villages
- an oversized district returned 500 preview rows while preserving its larger total and declaring truncation
- invalid empty, dual-scope, and unknown-scope requests were rejected
- protected-table counts were unchanged after all preview requests
- the optimized Next.js production build passed
- the UI contract covered block loading, both preview modes, readiness totals, duplicate impact, confirmation, cancellation, and capacity fences
- authenticated Playwright smoke previewed and selected 112 Nancowry block villages, verified zero persisted scope rows before Save, cleared the client-side selection, and completed the existing audited one-village assignment/rollback workflow
- fixture cleanup returned project, assignment-history, and audit counts to zero

Explicit non-effects:

- no partial oversized district or block selection
- no project write during preview or client-side selection
- no boundary candidate activation or promotion
- no boundary runtime-table write
- no runtime spatial lookup enablement
- no Android behavior change

### Project-creation geography milestone — 2026-09-11

Canonical geography configuration is now integrated into project creation.

Implemented behavior:

- project creation continues to support an empty geography scope
- the create form reuses the canonical LGD village picker
- individual, search-result bulk, district, and block selection retain the existing 500-village limit
- non-empty geography requires a 3–500 character audit reason
- submitted LGD codes are deduplicated, sorted, and resolved to active canonical village, block, district, and state records
- malformed, unknown, inactive, and over-limit geography is rejected before project insertion
- valid project creation and its initial geography audit event are committed atomically
- the normalized scope records `admin_project_creation` as its source
- initial villages appear as `ADDED` in the existing geography-scope history
- actor identity, reason, canonical hierarchy, and boundary readiness remain visible in history

Verification evidence:

- the project-creation geography API regression passed all validation, normalization, atomicity, audit, history, tenant, and cleanup checks
- the project geography UI contract passed
- the optimized Next.js production build passed
- authenticated Playwright created a project with LGD village `645063`, verified the persisted canonical scope, verified the creation audit through the API and UI, and proved that creation occurred only on complete form submission
- fixture cleanup restored project and audit counts to zero

Explicit non-effects:

- village preview and client-side selection do not create a project
- invalid geography does not create either a project or audit event
- no boundary candidate activation or promotion
- no boundary runtime-table write
- no runtime spatial lookup enablement
- no Android behavior change


## Climate, ecology, and biosphere layers

The climate/agro-ecology layer is seeded and visible but not broadly runtime-enabled.

Current readiness report posture:

- active climate regions: 50
- active region systems: 4
- active climate mappings: 231
- state-scope mappings: 5
- district-scope mappings: 226
- village-scope mappings: 0
- active crop-climate rules: 45
- active crops: 30
- crops with climate rules: 26
- crops without climate rules: 4
- districts with climate mapping/rules: 186 of 778
- districts without climate mapping: 592
- region records without active crop-climate rules: 45

Climate is ready for admin review and dry-run planning, but not ready for broad runtime enablement. The disabled apply guard keeps runtime and Android unchanged.

Before climate drives recommendations or advisories, the admin UI should show:

- mapped vs unmapped states/districts/blocks/villages/pin codes
- mapping scope level
- confidence and source references
- crop-season-region rule coverage
- missing rules by crop, season, and geography
- overrides and review status

## SOI and BharatAtlas posture

Existing policy docs remain valid:

- `docs/core-lgd-boundary-source-policy.md`
- `docs/bharatlas-boundary-source-review.md`
- `docs/survey-of-india-boundary-source-review.md`

Operational posture:

1. Backend LGD remains canonical for names/codes.
2. BharatAtlas is the current operational geometry source for development and overlay review.
3. SOI is official and should remain a reference/review source.
4. The current SOI extract is not safe for automatic direct LGD joins.
5. No source should become runtime-active without reviewed promotion, provenance, and rollback.

## External APIs and provider readiness

External API readiness is now inventoried without making network calls or enabling providers.

The current report covers provider-backed application surfaces such as:

- weather provider configuration
- weather snapshots
- soil enrichment snapshots and audit
- field-event external source usage

Readiness posture:

- read-only inventory is implemented
- live provider calls are not made by the report
- provider worker execution is not enabled
- activation remains blocked until credentials, policy, rate limits, cost controls, scheduler controls, failure audit, and rollback/supersession posture are explicit

The admin should be able to answer: for this tenant/project/state/district, which provider-backed functions are configured, observed, missing, blocked, or safe to activate?

## Admin UI enablement status

Implemented admin UI:

- route: `/geography-layer-readiness`
- endpoint used: `/api/v1/master-data/geography/layer-readiness`
- sidebar entry: Layer Readiness
- filters: state/UT, district, limit
- visible rollups:
  - runtime posture
  - LGD/PIN geography
  - NWDP demographic
  - NWDP boundary
  - climate/agro-ecology
  - project boundary readiness
  - boundary geometry validation readiness
  - selected boundary runtime promotion readiness
  - external API readiness
  - gap accounting
  - recommended next steps
  - state/district rows

The geography-layer-readiness page remains read-only.

The `/projects` admin page now additionally provides:

- canonical state/district village search
- nationwide village-name and exact-LGD search
- persisted selection hydration
- keyboard and bulk village selection
- selected-scope filtering and guarded removal
- per-project geography/boundary readiness summaries
- project-filtered boundary-review links
- read-only CSV import preview
- canonical CSV export
- optional canonical geography during atomic project creation
- lazy read-only project geography activation preflight
- explicit ready/blocker decisions and project-filtered boundary-review links
- an audited save action governed by project edit policy

The project editor changes only project configuration. Boundary promotion, runtime lookup, and Android behavior remain outside this surface.

## Recommended next implementation sequence

1. Keep this roadmap, national source validation, bounded planner outputs, and
   production-shaped apply design as the committed readiness baseline.
2. The multi-row validation-metadata transaction fixture is complete:
   - commit `2e8a111`
   - three source rows and three immutable events were written atomically
   - forced mid-batch failure restored the complete baseline
   - apply and rollback idempotency passed
   - wrong-token rollback was rejected without writes
   - regression cleanup restored exact database counts
3. Andaman batch 1 completed the exact pinned production apply:
   - operator and approver: `admin-regression`
   - approval reference: `user-authorization-2026-09-09`
   - final rollback token:
     `andaman-boundary-validation-metadata-batch-1-20260909`
   - source and plan checksums remain pinned
   - all 9 repair-required rows remain excluded
   - enabled implementation and regression passed in commit `4165140`
   - the immediate pre-apply baseline passed all 24 technical checks
   - exactly 500 source rows became `VALIDATED`
   - exactly 500 immutable active validation events were created
   - `NOT_VALIDATED` changed from 654,275 to 653,775
   - `VALIDATED` changed from 10 to 510
   - the one-time exact-batch authorization is consumed
   - runtime eligibility and downstream behavior remain unchanged
4. Keep further bounded batches and broad state apply disabled pending a new,
   separately reviewed plan and authorization. Andaman has 160 additional safe
   rows outside the completed batch.
5. Keep repair-required geometry separate:
   - do not include the 192 repairable-invalid rows in metadata apply
   - do not persist `make_valid()` output through validation metadata
   - retain separate geometry-repair review and apply controls
6. Resolve runtime eligibility only in a later independent workflow:
   - geometry validity must not grant runtime eligibility
   - candidate promotion and activation remain disabled
   - runtime tables and lookup remain unchanged
7. Treat the 2026-09-10 project geography-scope administration milestone as complete:
   - canonical search, hydration, bulk management, readiness, CSV preview/export, audited save, assignment, rollback, and cleanup are proved
   - keep broad project-boundary runtime enablement separate
8. Treat the 2026-09-11 project geography-scope audit-history milestone as complete: actor, reason, timestamp, canonical before/after changes, readiness classification, filtering, tenant isolation, and read-only guardrails are proved.
9. Treat district/block bulk selection as complete with read-only preview, readiness totals, duplicate/capacity impact, explicit confirmation, and no-partial-selection enforcement.
10. Treat project-creation geography configuration as complete:
    - empty geography remains supported
    - canonical selection retains the 500-village limit
    - non-empty geography requires an audit reason
    - validation happens before insertion
    - project and initial geography audit are committed atomically
    - authenticated browser proof confirms persistence and history
11. Treat the 2026-09-12 project geography activation-preflight milestone as complete:
    - ready, empty, missing, unresolved, blocked/manual-review, and non-PLANNED outcomes are explicit
    - tenant isolation and unknown-project handling are proved
    - the UI loads the preflight lazily and links to project-filtered boundary review
    - the decision is advisory and does not change project status
    - zero-write and runtime/Android guardrails are proved
12. Continue climate, SOI/BharatAtlas, and external-provider gap closure behind their existing dry-run and disabled-apply gates.
13. Keep Android behavior unchanged until a separate Android-intended runtime enablement is explicitly approved.

## Current conclusion

The application is ready to use LGD and village PIN-code geography for Android/runtime workflows.

NWDP demographic profiles are ready for admin/web preview only.

Project geography-scope administration is now operational for guarded PLANNED-project configuration: canonical search and hydration, readiness summaries, bulk management, CSV preview/export, audited persistence, project-boundary assignment, rollback, and cleanup all have committed regression evidence.

Project geography-scope audit history is now operationally visible with actor, reason, timestamp, canonical village differences, boundary readiness, and filters, while remaining read-only and available for locked projects.

District/block bulk selection is now operational through a read-only preview and explicit client-side confirmation workflow. Oversized and over-capacity scopes are never partially applied, and persistence still requires the existing audited project-scope save.

Canonical geography can now be configured during project creation. Empty geography remains optional; non-empty geography is validated and normalized before insertion, requires an audit reason, and is committed atomically with its initial history event. Browser proof confirms that preview and selection alone do not create a project.

Project cards now expose a lazy, read-only geography activation preflight. It reports canonical resolution, eligible and missing boundaries, blocked/manual-review candidates, explicit blockers, and an advisory ready decision without changing project status or runtime state.

NWDP boundary broad apply, selected boundary runtime promotion, climate/ecology/biosphere runtime enablement, SOI/BharatAtlas reconciliation, and external API activation still require their separately approved dry-run, policy, rollback, and promotion workflows. The 2026-09-10 milestone does not activate runtime spatial lookup or alter Android behavior.
