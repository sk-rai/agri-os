# Geography layer readiness and enablement roadmap

Status date: 2026-09-06  
Baseline purpose: committed readiness baseline after the geography matrix, admin endpoint, web page, project-boundary readiness, selected boundary runtime readiness, climate runtime dry-run, and external API readiness work.

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
| Project boundary disabled apply guard | `backend/scripts/apply_nwdp_boundary_project_matching_disabled.py` | Disabled apply guard | Implemented; rejects real apply and writes audit. |
| Boundary geometry validation readiness | `backend/scripts/report_boundary_geometry_validation_readiness.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| Boundary geometry repair classification | `backend/scripts/report_boundary_geometry_repair_classification.py` | Read-only JSON/CSV | Implemented and surfaced in matrix/page. |
| Boundary geometry repair disabled guard | `backend/scripts/apply_boundary_geometry_repair_disabled.py` | Disabled apply guard | Implemented; rejects real repair/status/eligibility writes and writes audit. |
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

Current blocker posture:

- invalid geometry blockers are visible
- runtime-ineligible source blockers are visible
- selected runtime promotable rows remain 0
- geometry repair is not attempted by the report
- runtime promotion remains disabled
- runtime lookup remains disabled
- Android remains unchanged

This report separates geometry repair planning from runtime promotion. Geometry validation/repair must be solved before selected boundary runtime promotion can move beyond disabled guards.

Boundary geometry repair classification is also now implemented and surfaced in the admin matrix/page. It splits the boundary backlog into validation, repair/re-import, runtime eligibility review, missing village/crosswalk review, manual review, and policy exclusion buckets.

A disabled boundary geometry repair guard is committed. It requires explicit apply intent, state/district scope, geometry-repair policy flag, runtime-eligibility policy flag, rollback/supersession token, classification review, and admin confirmation, but still refuses real mutation by policy.

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

Project boundary matching now has read-only readiness, scope resolution, dry-run planning, and disabled apply guard coverage.

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

1. Keep this document as the committed readiness baseline.
2. Add project boundary matching real-apply design document:
   - exact target table
   - uniqueness/idempotency policy
   - rollback/supersession plan
   - audit event model
   - admin confirmation requirements
3. Add boundary geometry repair real-apply design document:
   - exact fields allowed to change
   - geometry validation/re-import/repair policy
   - runtime eligibility status policy
   - rollback/supersession plan
   - proof that selected runtime promotion remains separately gated
4. Only after design review, implement tiny-fixture repair apply regression before any broad repair.
5. Continue climate gap closure:
   - exact target table
   - uniqueness/idempotency policy
   - rollback/supersession plan
   - audit event model
   - admin confirmation requirements
5. Only after the design is reviewed, implement tiny-fixture apply regressions before any broad project-boundary apply.
6. Continue climate gap closure:
   - fill missing district mappings
   - fill crop/rule gaps
   - then run dry-run again
   - keep disabled apply guard until coverage is acceptable.
7. Keep Android unchanged until a separate Android runtime enablement story is explicitly approved.

## Current conclusion

The application is ready to use LGD and village PIN-code geography for Android/runtime workflows.

NWDP demographic profiles are ready for admin/web preview only.

NWDP boundary, project boundary matching, selected boundary runtime promotion, climate/ecology/biosphere runtime enablement, SOI/BharatAtlas reconciliation, and external API activation now have committed visibility and guard rails, but should remain blocked from runtime application behavior until their dry-run, policy, rollback, and promotion workflows are separately approved.
