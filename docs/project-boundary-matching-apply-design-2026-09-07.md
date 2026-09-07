# Project boundary matching apply design

Status date: 2026-09-07  
Status: design baseline only; real apply remains disabled.

## Purpose

This document defines the future real-apply contract for NWDP boundary project matching.

The apply workflow will create reviewed project-to-boundary match records for a scoped project, based on the existing dry-run selector. It must not promote NWDP boundary candidates into runtime boundary tables, enable runtime spatial lookup, overwrite LGD geography, call external APIs, or change Android behavior.

## Current committed prerequisite surfaces

| Surface | Path | Status |
| --- | --- | --- |
| Project boundary readiness report | `backend/scripts/report_project_boundary_readiness.py` | Implemented. |
| Project geography scope resolver | `backend/scripts/report_project_boundary_readiness.py` | Implemented. |
| Project boundary dry-run plan | `backend/scripts/plan_nwdp_boundary_project_matching_apply_dry_run.py` | Implemented. |
| Project boundary disabled apply guard | `backend/scripts/apply_nwdp_boundary_project_matching_disabled.py` | Implemented. |
| Endpoint/web rollup | `GET /api/v1/master-data/geography/layer-readiness` and `/geography-layer-readiness` | Implemented. |

Current posture from readiness work:

- active projects: 57
- projects with non-empty geography scope: 10
- projects with resolved LGD scope: 6
- projects ready for project-boundary dry-run: 5
- resolved project-scope villages: 123,505
- villages with eligible boundary candidates: 119,886
- villages without eligible boundary candidates: 3,619
- active project boundary matches: 0

## Non-goals

This apply must not:

- write `geography_boundary_runtime_sets`
- write `geography_boundary_runtime_features`
- write `geography_boundary_runtime_crosswalks`
- write runtime promotion events
- change `geography_boundary_crosswalk_candidates.promotion_status`
- activate NWDP boundary candidates
- mark source geometries as runtime eligible
- repair geometries
- enable lookup APIs
- change Android payloads or behavior
- overwrite LGD names/codes/geography
- call external APIs

## Target table

Primary target table:

- `geography_boundary_project_matches`

Future real apply may write rows to this table only.

Expected logical columns, inferred from existing scripts:

- `project_id`
- `village_id`
- candidate/source reference, preferably `boundary_candidate_id` if available in schema
- source metadata/provenance
- `is_active`
- audit timestamps / actor fields if available
- supersession or replaced-by fields if available

Before implementation, inspect the actual schema and write only existing columns unless a reviewed migration adds missing audit/provenance fields.

## Candidate selection contract

A future project-boundary apply may only consume candidates returned by:

- `backend/scripts/plan_nwdp_boundary_project_matching_apply_dry_run.py`

The dry-run selection policy is the source of truth:

- `source_system = NWDP_GSI_VILLAGE_BOUNDARY`
- `candidate_bucket = DIRECT_VLCODE_MATCH`
- `review_status = AUTO_CANDIDATE`
- `promotion_status = NOT_PROMOTED`
- `is_active = false`
- `proposed_village_id is not null`
- candidate village must be inside resolved project geography scope
- manual-review candidates excluded
- blocked candidates excluded
- non-direct candidates excluded

The apply must reject execution if the dry-run result is unhealthy, missing, stale, unscoped, or inconsistent with current DB state.

## Project scope contract

Project villages may resolve from:

- direct farmer enrollment villages
- farmer `project_id` + `village_id`
- parcel `project_id` + `village_id`
- enrollment project + farmer parcel village
- `projects.geography_scope`

Supported `projects.geography_scope` keys:

- `village_lgd_codes`
- `village_names`
- `pin_codes`
- `district_lgd_codes`
- `districts`
- `state_lgd_codes`
- `state_ids`
- `state`

Important precedence rule:

- broad state scope may be used only when narrower district/PIN/village scope is absent.

The apply must store enough audit context to reproduce which scope source selected each village.

## Dry-run to apply handshake

Real apply must require all of the following:

1. explicit `--apply`
2. explicit future policy flag, e.g. `--enable-project-boundary-apply`
3. exact `--project-id`
4. fresh dry-run artifact path or dry-run hash
5. dry-run confirmation flag
6. admin confirmation flag
7. rollback/supersession token
8. max-row limit
9. actor/admin identity if run through API/admin workflow
10. output directory for JSON/CSV audit

A dry-run artifact should be considered stale if:

- generated for a different project
- generated with different candidate policy
- generated before relevant candidate/project/geography updates
- selected candidates no longer match current DB state
- selected project scope no longer resolves to the same village set
- selected row count exceeds the approved limit

## Idempotency and uniqueness

The apply must be idempotent.

Recommended unique logical key:

- `project_id`
- `village_id`
- boundary candidate/source feature reference

If the actual table cannot enforce this directly, add a reviewed migration before real apply.

Behavior:

- first apply inserts active match rows for selected candidate/village pairs
- second apply with the same token and same dry-run should insert zero new rows
- if an active match already exists for the same project/village/candidate, skip it and report as already matched
- if an active match exists for the same project/village but different candidate, do not overwrite automatically; report conflict/manual review
- if the project scope changed after dry-run, abort

## Audit output

Every invocation must emit durable audit files:

- JSON audit
- selected candidate CSV
- skipped/already-existing CSV
- conflict CSV
- optional summary CSV

Minimum JSON fields:

- schema version
- generated timestamp
- mode
- project id
- tenant id
- actor/admin identity if available
- dry-run artifact/hash
- rollback/supersession token
- input flags
- candidate selection policy
- before counts
- planned counts
- inserted counts
- skipped counts
- conflict counts
- after counts
- guardrails
- output file paths

## Guardrails for future real apply

Project-boundary apply may set only:

- `project_boundary_matches_written=true` if rows are actually inserted

It must keep these false:

- `runtime_boundary_features_written=false`
- `runtime_boundary_crosswalks_written=false`
- `runtime_tables_written=false`
- `boundary_candidates_promoted=false`
- `boundary_candidates_activated=false`
- `runtime_spatial_matching_changed=false`
- `lookup_api_enabled=false`
- `android_behavior_changed=false`
- `lgd_geography_overwritten=false`
- `external_api_called=false`

## Rollback and supersession

Rollback must be possible without deleting historical audit.

Recommended strategy:

- insert rows with `is_active=true`
- rollback/supersession sets matching rows inactive or superseded
- keep original rows for audit
- record rollback token/reason
- record actor/admin identity if available
- emit rollback JSON/CSV audit

Do not use hard deletes for normal rollback.

## Conflict handling

The apply must not auto-resolve:

- multiple eligible boundary candidates for one project village
- existing active match for a different candidate
- non-direct crosswalk buckets
- manual-review candidates
- blocked candidates
- missing proposed village
- invalid/runtime-ineligible boundary source geometry

These should be emitted as conflict/manual-review rows.

## Relationship to selected boundary runtime promotion

Project-boundary matching is not runtime boundary promotion.

After project-boundary apply succeeds:

- boundary runtime lookup remains disabled
- selected boundary runtime promotion remains separately gated
- geometry validation/repair remains separately gated
- Android remains unchanged

A project-boundary match may later become an input to selected runtime promotion review, but it cannot itself create runtime boundary tables.

## API/admin workflow design

Future admin API should be added only after script apply design is regression-tested.

Suggested future endpoints:

- `POST /api/v1/master-data/geography/project-boundary-matching/dry-run`
- `POST /api/v1/master-data/geography/project-boundary-matching/apply`
- `POST /api/v1/master-data/geography/project-boundary-matching/rollback`

Access should require admin mutation permission, not viewer permission.

Admin UI should show:

- selected project
- resolved scope sources
- resolved village count
- eligible candidate count
- conflicts
- dry-run artifact hash
- explicit confirmation checklist
- rollback/supersession token

## Required regression ladder before real apply

Before enabling any real apply:

1. disabled guard regression remains passing
2. dry-run regression remains passing
3. schema inspection regression verifies target columns
4. tiny-fixture apply regression inserts two match rows
5. tiny-fixture apply regression is idempotent on second run
6. rollback/supersession regression deactivates only fixture rows
7. broad real apply remains disabled unless policy flag and admin approval are explicit
8. Android non-regression guard remains passing

## Current conclusion

Project boundary matching is ready for apply implementation design review, not ready for broad real apply.

The next safe implementation step is a tiny-fixture project-boundary apply script that writes only `geography_boundary_project_matches`, proves idempotency, proves rollback/supersession, and keeps runtime lookup and Android unchanged.
