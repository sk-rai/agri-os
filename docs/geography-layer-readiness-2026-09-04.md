# Geography layer readiness and enablement roadmap

Status date: 2026-09-08
Baseline purpose: committed readiness baseline after the geography matrix, admin endpoint, web page, project-boundary readiness, national boundary geometry validation, validation-metadata lifecycle proof, selected boundary runtime readiness, climate runtime dry-run, and external API readiness work.

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
| Project boundary matches | 0 active project boundary matches | Not ready | Readiness/dry-run visible | Keep apply disabled until policy, rollback, and exact project scope are approved. |
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

Project boundary matching now has read-only readiness, scope resolution, dry-run planning, disabled broad-apply guard coverage, and a green tiny-fixture apply path.

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

The dry-run can select eligible direct-VLCode auto-candidates for scoped projects, but real apply remains disabled. No project boundary match rows, runtime tables, lookup API enablement, candidate activation, candidate promotion, or Android behavior changes are allowed yet.

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

The page remains read-only.

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
7. Continue project-boundary, climate, SOI/BharatAtlas, and external-provider
   gap closure behind their existing dry-run and disabled-apply gates.
8. Keep Android behavior unchanged until a separate Android-intended runtime
   enablement is explicitly approved.

## Current conclusion

The application is ready to use LGD and village PIN-code geography for Android/runtime workflows.

NWDP demographic profiles are ready for admin/web preview only.

NWDP boundary, project boundary matching, selected boundary runtime promotion, climate/ecology/biosphere runtime enablement, SOI/BharatAtlas reconciliation, and external API activation now have committed visibility and guard rails, but should remain blocked from runtime application behavior until their dry-run, policy, rollback, and promotion workflows are separately approved.
