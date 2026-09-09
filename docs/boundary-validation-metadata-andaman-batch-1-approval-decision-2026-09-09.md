# Andaman batch 1 boundary validation metadata approval decision

Status date: 2026-09-09
Approval status: `CONDITIONALLY_APPROVED_FOR_EXACT_BATCH`
Write authorization: `GRANTED_AFTER_ENABLED_IMPLEMENTATION_REVIEW`

## Purpose

This artifact records administrative authorization for the exact checksum-pinned Andaman and Nicobar Islands validation-metadata batch.

Authorization becomes executable only after the enabled implementation and its regression pass, and after the database baseline is recaptured immediately before apply.

## Governing design

The production apply contract is defined in:

`docs/boundary-validation-metadata-production-apply-design-2026-09-09.md`

Relevant implementation evidence includes:

- bounded state rollout design: `93bd4a6`
- bounded state planner: `edfca74`
- validation metadata event schema: `8496c39`
- disabled bounded apply guard: `95b578b`
- multi-row transaction lifecycle proof: `2e8a111`
- production-shaped apply design: `f63e024`

## State and source identity

| Field | Value |
| --- | --- |
| State slug | `andaman_and_nicobar_islands` |
| State or UT | `Andaman and Nicobar Islands` |
| Import batch ID | `0a93be10-e508-50b9-97ba-b43659899e9b` |
| Source system | `NWDP_GSI_VILLAGE_BOUNDARY` |
| Source CRS | `EPSG:7755` |
| Target CRS | `EPSG:4326` |
| Source feature count | 669 |
| Source SHA-256 | `46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591` |
| Geometry hash algorithm | `NWDP_GEOJSON_GEOMETRY_CANONICAL_V1` |

## Reviewed plan identity

| Field | Value |
| --- | --- |
| Plan schema | `boundary_geometry_validation_metadata_bounded_state_plan.v1` |
| Batch ID | `cf20a985-31c8-550d-8898-51475b568fda` |
| Plan checksum | `822ed7575c67de714e1599de243d7ecbd77828471de308c1a087ff38de12ef4d` |
| Cursor after index | `-1` |
| First selected source-feature index | 0 |
| Last selected source-feature index | 506 |
| Next cursor after index | 506 |
| Selected row count | 500 |
| Remaining safe rows | 160 |
| Has more | true |

The plan was regenerated and checked on 2026-09-09.

Preflight confirmed:

- `healthy=true`
- selected row count is exactly 500
- canonical plan checksum matches
- source checksum matches
- every selected row is `VALIDATED_NO_REPAIR`
- every selected row plans `VALIDATED`
- no selected row plans a runtime eligibility change

## State classification

| Classification | Count |
| --- | ---: |
| Valid without repair | 660 |
| Repair required | 9 |
| Validation review | 0 |

All 9 `REPAIR_REQUIRED` rows are excluded from this batch.

No repaired geometry may be persisted through this workflow.

## Proposed field changes

Only these fields may change:

- `source_geometry_hash`
- `source_bbox`
- `transformed_bbox`
- `transformed_centroid`
- `geometry_validation_status`
- `metadata`

For every selected row:

- current status must be `NOT_VALIDATED`
- planned status must be `VALIDATED`
- runtime eligibility must remain false
- the canonical geometry hash must be present
- transformed bounding-box metadata must be present
- transformed centroid metadata must be present

## Prohibited changes

This candidate does not authorize:

- geometry repair persistence
- runtime eligibility changes
- candidate promotion
- candidate activation
- runtime-set writes
- runtime-feature writes
- runtime-crosswalk writes
- runtime lookup enablement
- LGD geography changes
- Android behavior changes
- a second Andaman batch
- another state batch
- broad state apply
- national apply

## Expected database accounting

The database baseline must be recaptured immediately before any future apply.

The last known baseline was:

| Measure | Before | Expected after apply |
| --- | ---: | ---: |
| Source feature rows | 654,285 | 654,285 |
| `NOT_VALIDATED` rows | 654,275 | 653,775 |
| `VALIDATED` rows | 10 | 510 |
| Runtime-eligible source rows | 0 | 0 |
| Boundary candidate rows | 654,285 | 654,285 |
| Active boundary candidates | 0 | 0 |
| Promoted boundary candidates | 0 | 0 |
| Runtime sets | 1 | 1 |
| Runtime features | 10 | 10 |
| Runtime crosswalks | 10 | 10 |
| Validation event rows | 0 | 500 |
| Active validation events | 0 | 500 |

If the recaptured baseline differs, these expected values must be regenerated
and reviewed before approval.

Exactly 500 source rows and 500 validation event rows must change.

## Transaction requirements

A future enabled apply must:

1. Revalidate the plan and source checksums.
2. Lock all 500 source rows.
3. Recheck source identity, import batch, current status, and runtime
   ineligibility.
4. Insert 500 inactive `PLANNED` events.
5. Update only the approved source metadata fields.
6. Record complete `before_values`, `planned_values`, and `after_values`.
7. Activate all 500 events only after their source updates succeed.
8. verify exact row and count accounting.
9. Commit the full batch once.
10. Roll back the entire transaction after any failure.

Partial success is prohibited.

## Idempotency requirements

Repeating the same apply with the same source checksum, plan checksum, and
rollback token must:

- return `IDEMPOTENT_NO_OP`
- change zero source rows
- change zero event rows
- preserve all counts

A partial or conflicting event set must be rejected.

## Proposed rollback identity

Proposed rollback token:

`andaman-boundary-validation-metadata-batch-1-20260909`

The final token must be confirmed in the administrative approval.

Rollback must:

- require the exact source checksum
- require the exact plan checksum
- require the exact rollback token
- restore all 500 source rows from event `before_values`
- mark all corresponding events `ROLLED_BACK`
- make all corresponding events inactive
- preserve the event rows as lifecycle evidence
- execute as one transaction
- be idempotent when repeated

## Required pre-apply evidence

Before approval, reviewers must receive:

- the complete planner JSON
- the planner CSV containing all 500 selected rows
- the source-file checksum verification
- the canonical plan-content checksum verification
- the selected-ID uniqueness check
- the source-index uniqueness and ordering check
- database identity alignment results
- current-status verification
- runtime-ineligibility verification
- expected database count delta
- disabled-guard regression output
- multi-row transaction regression output
- rollback procedure
- named operator
- named approver

## Pending administrative fields

| Field | Status |
| --- | --- |
| Operator | `admin-regression` |
| Approver | `admin-regression` |
| Approval timestamp | `2026-09-09` |
| Approval reference | `user-authorization-2026-09-09` |
| Final rollback token confirmation | `andaman-boundary-validation-metadata-batch-1-20260909` |
| Pre-apply database baseline recapture | `REQUIRED_IMMEDIATELY_BEFORE_APPLY` |
| Complete 500-row plan review | `TECHNICAL_EVIDENCE_PASSED_24_OF_24` |
| Enabled implementation review | `REQUIRED_BEFORE_APPLY` |

## Decision

Current decision:

`CONDITIONALLY_APPROVED_FOR_EXACT_BATCH`

Current readiness:

- ready for administrative evidence review: yes
- ready for enabled bounded apply implementation: yes
- ready for real 500-row apply: only after implementation regression and immediate baseline recapture
- ready for broad validation metadata apply: no
- ready for runtime eligibility changes: no
- ready for runtime lookup enablement: no
- ready for Android behavior changes: no

This decision authorizes implementation and, after its regression passes, one exact 500-row apply using the recorded checksums and rollback token. It does not authorize another batch, runtime eligibility, candidate promotion, runtime lookup, or Android behavior changes.
