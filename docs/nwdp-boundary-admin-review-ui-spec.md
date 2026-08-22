# NWDP Boundary Admin Review UI Spec

Status date: 2026-08-21

This spec defines the admin review UI for NWDP/GSI village-boundary crosswalk candidates.

It mirrors the CoRE/LGD manual-review pattern:

- candidate rows are staged first;
- candidates are inactive by default;
- unresolved or ambiguous records require human review;
- promotion is separate from import;
- runtime point-in-polygon stays disabled until explicit promotion.

## Purpose

Give an admin reviewer a safe way to inspect NWDP village-boundary candidates and decide whether each candidate should remain pending, be promoted later, be marked reference-only, or be rejected.

This UI must not directly mutate canonical LGD geography.

## Route proposal

Suggested admin routes:

- `/admin/geography/boundaries`
- `/admin/geography/boundaries/batches`
- `/admin/geography/boundaries/batches/:batchId`
- `/admin/geography/boundaries/candidates/:candidateId`

If the existing admin route grouping prefers a different structure, keep the concept but fit it under the current geography/admin navigation.

## Main navigation label

Suggested label:

    Geography boundaries

Sub-label:

    Review staged village-boundary crosswalks before promotion.

## Batch list screen

Purpose: show source batches and their safety state.

Columns:

- batch id;
- source system;
- source dataset;
- state/UT;
- source format;
- source CRS;
- target CRS;
- status;
- review status;
- source file checksum;
- feature count;
- candidate count;
- auto-candidate count;
- manual-review count;
- blocked/reference-only count;
- created at;
- reviewed at.

Primary actions:

- view batch;
- download dry-run summary;
- download candidate CSV;
- mark batch reviewed;
- block batch;
- open source/audit docs.

Hard guard:

No batch action should make rows active for runtime lookup.

## Candidate list screen

Purpose: let reviewer triage candidates by bucket, geography, and risk.

Required filters:

- candidate bucket;
- review status;
- promotion status;
- proposed scope;
- state/UT;
- district;
- subdistrict/block;
- source `vlcode`;
- backend village LGD code;
- special/reference feature flag;
- parent mismatch only;
- unresolved only.

Default filter:

    review_status in MANUAL_REVIEW, BLOCKED

Sortable columns:

- source feature index;
- candidate bucket;
- review status;
- proposed scope;
- district;
- subdistrict;
- block;
- source village name;
- source `vlcode`;
- backend village name;
- backend village LGD code;
- reason;
- updated at.

Visual bucket treatment:

| Bucket | UI tone | Default reviewer posture |
| --- | --- | --- |
| `DIRECT_VLCODE_MATCH` | green/neutral | batch review before promotion |
| `DIRECT_VLCODE_PARENT_MISMATCH` | amber | manual review |
| `PARENT_SCOPED_NAME_MATCH` | amber | manual review |
| `PARENT_SCOPED_NAME_AMBIGUOUS` | amber/red | manual review |
| `PARENT_MATCH_VILLAGE_UNRESOLVED` | amber | district/subdistrict-scoped review |
| `DISTRICT_SCOPED_AMBIGUOUS` | red | district-level ambiguity review |
| `SPECIAL_REFERENCE_FEATURE` | gray/red | reference-only or reject |
| `BLOCKED_SOURCE_CAVEAT` | red | block until source caveat resolved |

Bulk actions:

- export selected candidates;
- mark selected as needs source review;
- assign reviewer;
- add batch note.

No bulk promotion in first version.

## Candidate detail screen

Show four panels.

### 1. Source feature panel

Fields:

- source feature index;
- source `stcode`;
- source `dtcode`;
- source `sdcode`;
- source `bkcode`;
- source `vlcode`;
- source state/district/subdistrict/block/village names;
- source agency;
- feature category;
- source properties JSON;
- geometry checksum;
- source bbox;
- transformed bbox;
- transformed centroid;
- geometry validation status.

### 2. Proposed LGD match panel

Fields:

- proposed scope;
- proposed state;
- proposed district;
- proposed block/subdistrict;
- proposed village;
- proposed LGD codes;
- backend IDs;
- match evidence;
- candidate bucket;
- confidence;
- reason.

### 3. Audit evidence panel

Show:

- manifest audit summary;
- CRS audit summary;
- geometry/topology audit summary;
- crosswalk candidate-plan summary;
- dry-run import verifier summary;
- source file checksum;
- source URL/download URL;
- “not cadastral truth” warning.

### 4. Reviewer decision panel

Allowed decisions:

| Decision | Meaning |
| --- | --- |
| `KEEP_PENDING` | Needs more review; no promotion. |
| `ACCEPT_DIRECT_CODE_MATCH` | Reviewer accepts direct `vlcode` candidate for later promotion. |
| `ACCEPT_REVIEWED_NAME_MATCH` | Reviewer accepts scoped name/candidate evidence. |
| `MARK_REFERENCE_ONLY` | Keep as district/subdistrict reference geometry, not village assignment. |
| `REJECT_SOURCE_MISMATCH` | Source feature does not match backend geography. |
| `REJECT_SPECIAL_FEATURE` | River/reservoir/beat/etc. not eligible as village mapping. |
| `BLOCK_PENDING_SOURCE_REVIEW` | Source caveat or evidence gap blocks decision. |

Every non-pending decision requires:

- reviewer id;
- timestamp;
- reviewer note;
- evidence summary.

## Promotion gate

Promotion must be a separate screen or action, not part of import.

Promotion prerequisites:

- candidate exists;
- candidate is inactive;
- source batch is reviewed;
- geometry audit is green;
- CRS transform is verified;
- candidate review decision is accepted;
- reviewer note exists;
- no unresolved source caveat;
- runtime boundary lookup feature flag remains off unless separately enabled.

Promotion output should create or update only a promoted mapping table in a future migration. It should not mutate LGD canonical state/district/block/village rows.

## Map preview

The first version can be attribute-only.

Future version may show:

- transformed centroid;
- source boundary outline;
- proposed district/block/village context;
- parcel overlay only after runtime policy exists.

Map preview warnings:

- boundary is reference geography;
- not cadastral parcel truth;
- not ownership evidence;
- not automated claim/subsidy/insurance decisioning.

## Safety copy

Display on batch and candidate detail pages:

    NWDP/GSI village boundaries are reference administrative geometry. LGD remains canonical identity. Unreviewed candidates are inactive and cannot affect Android, parcel assignment, claims, subsidy, insurance, or runtime point-in-polygon decisions.

## API shape proposal

Read endpoints:

- `GET /api/v1/admin/geography/boundary-batches`
- `GET /api/v1/admin/geography/boundary-batches/{batch_id}`
- `GET /api/v1/admin/geography/boundary-batches/{batch_id}/candidates`
- `GET /api/v1/admin/geography/boundary-candidates/{candidate_id}`

Review endpoints:

- `POST /api/v1/admin/geography/boundary-candidates/{candidate_id}/review`
- `POST /api/v1/admin/geography/boundary-batches/{batch_id}/review`

Future promotion endpoints:

- `POST /api/v1/admin/geography/boundary-candidates/{candidate_id}/promote`
- `POST /api/v1/admin/geography/boundary-batches/{batch_id}/promote-reviewed-direct-matches`

Promotion endpoints should remain unimplemented until the staging import and reviewer workflow are proven.

## Acceptance criteria

- UI exposes batch-level and candidate-level review.
- UI separates auto candidates, manual review, blocked/reference-only, and unresolved rows.
- UI never marks candidates active during import review.
- UI requires reviewer note for non-pending decisions.
- UI shows CRS/geometry/crosswalk evidence.
- UI clearly states that boundary data is not cadastral truth or ownership proof.
- UI has no Android-facing impact.
- UI has no runtime point-in-polygon effect before explicit promotion.

## Current decision

Build this as an admin review workflow after staging-table migration is reviewed. Do not implement promotion or runtime spatial matching in the first UI pass.

## Related backend contract

Backend endpoint and response contracts are specified in `docs/nwdp-boundary-admin-api-contract.md`.
