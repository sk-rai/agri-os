# Boundary geometry repair apply design

Status date: 2026-09-07
Scope: design baseline only. No repair/apply implementation is enabled by this document.

## Executive decision

Boundary geometry repair must remain separated from selected boundary runtime promotion.

The repair apply path may only prepare invalid NWDP boundary source features or candidates for a later runtime promotion review. It must not promote candidates, write runtime boundary tables, enable runtime lookup, overwrite LGD geography, or change Android behavior.

## Current blocker posture

The committed readiness and classification reports show that selected boundary runtime promotion is blocked because:

- selected runtime promotable count is zero
- invalid geometry count is positive
- runtime-ineligible source count is positive
- source features need classification into repairable, re-import-required, manual-review, policy-excluded, and unresolved buckets
- runtime lookup is disabled
- Android behavior is unchanged

Relevant committed scripts:

- `backend/scripts/report_boundary_geometry_validation_readiness.py`
- `backend/scripts/report_boundary_geometry_repair_classification.py`
- `backend/scripts/apply_boundary_geometry_repair_disabled.py`
- `backend/scripts/report_selected_boundary_runtime_promotion_readiness.py`
- `backend/scripts/apply_selected_boundary_runtime_promotion_disabled.py`

## Target of future repair apply

The only allowed future repair-apply target is boundary geometry preparation metadata and source-feature geometry validity posture.

Allowed future changes, only after explicit policy enablement:

- mark selected source features as reviewed for geometry repair
- store repair classification outcome
- store repair audit metadata
- optionally store a repaired geometry or repaired geometry reference if the schema explicitly supports it
- optionally mark a source feature as runtime-eligible only when geometry validation and source policy both pass

Forbidden changes in geometry repair apply:

- no writes to geography_boundary_runtime_features
- no writes to geography_boundary_runtime_crosswalks
- no candidate promotion
- no candidate activation
- no project boundary match writes
- no LGD state/district/village overwrite
- no Android payload or runtime lookup behavior change
- no external API activation

## Repair strategy taxonomy

Each invalid or blocked boundary geometry should be classified into exactly one primary action bucket.

### 1. Auto-repair candidate

Use only when geometry can be repaired deterministically without changing intended administrative identity.

Examples:

- self-intersection that ST_MakeValid can repair into a valid polygon/multipolygon
- ring orientation or minor topology issue
- geometry collection can be safely normalized to polygonal geometry

Required checks:

- source feature has stable source identity
- proposed LGD village remains unchanged
- repaired geometry is valid
- repaired geometry is non-empty
- repaired geometry type is polygonal
- area is positive
- repaired geometry does not create obvious cross-district/state mismatch

### 2. Re-import required

Use when repair cannot safely preserve the source geometry semantics.

Examples:

- null geometry
- empty geometry
- non-polygonal feature
- geometry with extreme distortion after repair
- geometry crosses incompatible administrative boundary
- source feature lacks enough identity to verify repaired output

### 3. Manual review required

Use when automated repair is technically possible but policy confidence is not enough.

Examples:

- multiple polygons with uncertain village identity
- mismatched source district/subdistrict names
- conflicting LGD code/name evidence
- duplicate candidate competition for the same village
- severe area change after repair

### 4. Runtime eligibility review

Use when geometry is valid or repairable but the source itself is not approved for runtime use.

Examples:

- source feature is valid but eligible_for_runtime_after_promotion=false
- source system policy has not been approved
- licensing/provenance review is incomplete

### 5. Permanent exclusion

Use only when the feature should not be repaired or promoted.

Examples:

- corrupt/unusable feature
- confirmed wrong village
- confirmed duplicate superseded by better source
- source is not allowed for runtime use

## Required dry-run behavior

Before any real repair apply exists, a dry-run must emit JSON and CSV audit files.

Dry-run must report:

- input state/district scope
- candidate feature count
- invalid geometry count
- null/empty geometry count
- auto-repair candidate count
- re-import required count
- manual review required count
- runtime eligibility review count
- permanent exclusion count
- sample source feature IDs
- proposed action per sample
- before DB counts
- after DB counts
- guardrails proving no mutation

Dry-run must not write DB rows.

## Required real-apply gates

A future real repair apply must require all of the following:

- --apply
- state and district scope
- explicit geometry repair policy flag
- explicit runtime eligibility policy flag if eligibility fields may change
- rollback or supersession token
- classification review confirmation
- admin confirmation
- max-row cap
- JSON audit path
- CSV audit path

The apply must exit non-zero if any gate is missing.

## Required real-apply constraints

A future real apply must be idempotent.

Idempotency policy:

- same source feature plus same repair classification plus same rollback token must not duplicate audit records
- repeated apply must report already-applied rows
- supersession must create a clear new token or version
- rollback must never delete source features

Allowed mutation scope must be narrow and explicit. If the current schema does not have a safe place for repair metadata, add a dedicated audit/status table before implementing apply.

Recommended future table if needed: geography_boundary_geometry_repair_events

Suggested fields:

- id
- source_feature_id
- import_batch_id
- source_system
- state_or_ut
- district
- repair_action
- repair_status
- before_geometry_validation_status
- after_geometry_validation_status
- before_runtime_eligibility
- after_runtime_eligibility
- repair_method
- rollback_token
- dry_run_report
- apply_report
- rollback_report
- applied_by
- applied_at
- rolled_back_by
- rolled_back_at
- created_at
- updated_at
- is_active
- version

## Rollback and supersession

Rollback must be metadata-safe.

Rollback may:

- deactivate repair event rows
- restore previous validation/eligibility status only if the previous value was captured in the apply audit
- mark repaired output as superseded

Rollback must not:

- delete source features
- delete candidates
- delete runtime tables
- promote candidates
- enable lookup
- touch Android behavior

Supersession is preferred when repaired geometry outputs are versioned. A newer repair token can supersede an older repair event while keeping full audit history.

## Guardrails

Every dry-run, disabled guard, and future apply audit must include these guardrails:

- db_writes_attempted=false
- geometry_repair_attempted=false
- geometry_validation_status_changed=false
- source_runtime_eligibility_changed=false
- source_features_changed=false
- boundary_candidates_promoted=false
- boundary_candidates_activated=false
- runtime_boundary_features_written=false
- runtime_boundary_crosswalks_written=false
- runtime_tables_written=false
- runtime_lookup_enabled=false
- android_behavior_changed=false
- lgd_geography_overwritten=false

For a future enabled tiny fixture repair apply, db_writes_attempted and the narrow repair metadata guardrail may become true, but runtime, lookup, LGD, candidate promotion, and Android guardrails must remain false.

## Regression requirements

Minimum regressions before any real apply:

1. no-apply invocation exits non-zero and writes audit
2. missing state/district scope exits non-zero
3. missing rollback/supersession token exits non-zero
4. missing classification confirmation exits non-zero
5. disabled apply remains blocked even with confirmations
6. dry-run writes JSON and CSV
7. dry-run leaves DB counts unchanged
8. tiny fixture apply, if implemented, mutates only the approved repair metadata target
9. rollback returns fixture DB counts to baseline
10. selected boundary runtime promotion remains blocked until repaired/eligible features exist
11. Android behavior remains unchanged

## Relationship to selected runtime promotion

Geometry repair is a prerequisite, not a promotion.

The sequence must remain:

1. classify boundary geometry repair backlog
2. design repair apply
3. implement disabled guard
4. implement tiny fixture repair apply, if schema supports it
5. re-run selected boundary runtime promotion readiness
6. only then consider selected runtime promotion dry-run/apply

## Current conclusion

Boundary geometry repair is ready for design review and disabled-guard enforcement.

It is not ready for broad real apply, runtime boundary promotion, runtime lookup enablement, or Android behavior change.
