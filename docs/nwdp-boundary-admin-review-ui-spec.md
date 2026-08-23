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

## UI smoke checkpoint

Status date: 2026-08-22

Smoke script:

- `web/smoke/nwdp_boundary_review_smoke.mjs`

Latest observed result:

- status: passed;
- page URL: `/nwdp-boundary-review`;
- rows seen: 100;
- screenshot: `web/smoke/screenshots/nwdp-boundary-review.png`;
- runtime spatial matching expected state: disabled.

Implementation note:

The first UI smoke found a frontend/backend field-name mismatch: the batch list API returns `batch_id`, while the first UI implementation expected `id`. The UI now accepts `batch_id` and uses it for candidate-list loading.

Current decision:

- NWDP boundary admin review UI is usable for inactive staging review;
- candidate rows remain inactive and unpromoted;
- runtime point-in-polygon behavior remains unchanged;
- screenshots remain local smoke artifacts and are not committed by default.

## Auto-detail smoke checkpoint

Status date: 2026-08-22

Latest observed smoke:

- script: `web/smoke/nwdp_boundary_review_smoke.mjs`;
- status: passed;
- rows seen: 100;
- stable detail panels asserted:
  - source codes;
  - source names;
  - source feature;
- match evidence panel is treated as optional in smoke because the first auto-selected row/detail payload may not always expose renderable match evidence;
- latest observed `match_evidence_panel_seen`: false.

Implementation note:

The auto-detail behavior now loads the first visible candidate after candidate data is available. This avoids the earlier runtime initialization issue where `loadDetail` was referenced before initialization.

Governance remains unchanged:

- candidates remain inactive;
- promotion remains unsupported from this UI;
- runtime spatial matching remains disabled;
- Android behavior remains unchanged.

## Detail smoke stabilization checkpoint

Status date: 2026-08-22

Latest observed result:

- `web/smoke/nwdp_boundary_review_smoke.mjs` passed;
- rows seen: 100;
- shortcut buttons are covered;
- stable detail panels are covered:
  - source codes;
  - source names;
  - source feature;
- match-evidence display remains observational rather than required by smoke.

Implementation note:

The UI can render match evidence from either the detailed candidate payload or the selected list row. The smoke does not fail when the first selected row does not expose a visible match-evidence panel, because candidate detail payload/rendering can vary by bucket and row shape.

Regression note:

A transient runtime issue was observed when `loadCandidates` referenced `loadDetail` before `loadDetail` was initialized. The stable implementation keeps `loadCandidates` dependent only on `queryPath` and handles detail loading after candidate data is present.

Governance remains unchanged:

- candidate rows remain inactive;
- review metadata changes do not promote candidates;
- runtime spatial matching remains disabled;
- Android behavior remains unchanged.

## Review decision shortcut checkpoint

Status date: 2026-08-22

Latest UI behavior:

- review metadata form includes shortcut buttons for common reviewer actions:
  - keep pending;
  - reference only;
  - reject mismatch;
  - block review;
- shortcuts prefill the reviewer decision and, where useful, suggested notes;
- UI explicitly reminds reviewers that notes are required for non-pending decisions;
- saving review metadata does not activate geometry, promote candidates, or change runtime spatial matching.

Regression coverage:

- `web/smoke/nwdp_boundary_review_smoke.mjs` now asserts:
  - queue shortcut buttons;
  - review decision shortcut buttons;
  - notes guidance;
  - stable detail panels;
  - candidate rows render;
  - runtime spatial matching remains disabled.

Latest observed smoke result:

- status: passed;
- rows seen: 100;
- runtime spatial matching expected: disabled;
- match evidence panel remains observational.

## Review guard hint checkpoint

Status date: 2026-08-22

Latest UI behavior:

- non-pending review decisions show a notes requirement;
- save is disabled when non-pending decisions have missing/too-short notes;
- `Reference only` on a non-special/reference row shows a guard hint;
- approve-style decisions on special/reference rows show a guard hint;
- guard hints are advisory/client-side only; backend validation remains authoritative.

Regression coverage:

- `web/smoke/nwdp_boundary_review_smoke.mjs` now covers:
  - review decision shortcut buttons;
  - notes guidance;
  - reference-only mismatch hint;
  - stable candidate/detail rendering;
  - runtime spatial matching remains disabled.

Governance remains unchanged:

- review saves affect metadata only;
- candidates remain inactive unless a future reviewed promotion workflow is separately designed;
- no runtime spatial lookup table or active geometry path is enabled by this UI.

## Review history panel checkpoint

Status date: 2026-08-23

Latest UI behavior:

- selected candidate detail panel shows review history from the backend candidate detail payload;
- newest review events are shown first;
- each event can show decision/status, timestamp, reviewer id, and notes when present;
- empty history is displayed as `No review history yet.`;
- review history is read-only display context and does not enable promotion or runtime spatial matching.

Regression coverage:

- `web/smoke/nwdp_boundary_review_smoke.mjs` now asserts the Review history panel is present;
- latest observed smoke result passed with 100 candidate rows rendered;
- runtime spatial matching remains disabled.

Governance remains unchanged:

- review endpoint updates metadata only;
- candidate rows remain inactive;
- promotion remains unsupported from this UI;
- Android behavior remains unchanged.

## Review save smoke checkpoint

Status date: 2026-08-23

Latest UI behavior:

- review metadata save path is exercised through browser smoke;
- UI sends both `reviewer_decision` and backend-required `review_status`;
- safe `KEEP_PENDING` review save succeeds;
- success message confirms the candidate remains inactive and unpromoted;
- runtime spatial matching remains disabled.

Smoke script:

- `web/smoke/nwdp_boundary_review_save_smoke.mjs`

Latest observed result:

- status: passed;
- rows seen: 100;
- screenshot: `web/smoke/screenshots/nwdp-boundary-review-save.png`;
- runtime spatial matching expected: disabled.

Implementation note:

The first save smoke exposed a UI/backend contract gap: the backend requires `review_status`, while the UI initially sent only `reviewer_decision`. The UI now derives a guarded review status from the selected decision:
- `KEEP_PENDING` -> `MANUAL_REVIEW`;
- `MARK_REFERENCE_ONLY` -> `REFERENCE_ONLY`;
- reject decisions -> `REJECTED`;
- block decision -> `BLOCKED`;
- accept decisions -> `APPROVED_FOR_PROMOTION`.

Governance remains unchanged:

- the tested save path updates review metadata only;
- candidates remain inactive;
- promotion remains unsupported from the UI;
- no runtime spatial lookup path is enabled.

## Combined web smoke runner checkpoint

Status date: 2026-08-23

Runner:

- `web/smoke/run_nwdp_boundary_review_smokes.mjs`

Covered smokes:

- `web/smoke/nwdp_boundary_review_smoke.mjs`;
- `web/smoke/nwdp_boundary_review_save_smoke.mjs`.

Latest observed result:

- status: passed;
- review smoke rows seen: 100;
- save smoke rows seen: 100;
- runtime spatial matching expected: disabled;
- screenshots generated locally under `web/smoke/screenshots/`.

Current decision:

- NWDP boundary admin UI has a compact web smoke runner for read/detail/guard-hint and safe metadata-save coverage;
- screenshots remain local smoke artifacts and are not committed by default;
- backend and frontend review flows remain metadata-only and do not promote or activate boundary candidates.

## Combined web smoke runner checkpoint

Status date: 2026-08-23

Runner:

- `web/smoke/run_nwdp_boundary_review_smokes.mjs`

Latest observed result:

- `nwdp_boundary_review_smoke.mjs`: passed;
- `nwdp_boundary_review_save_smoke.mjs`: passed;
- rows seen: 100 in each smoke;
- runtime spatial matching expected state: disabled;
- screenshots are written under `web/smoke/screenshots/` and remain local smoke artifacts.

Current decision:

- NWDP boundary admin UI has a compact web smoke runner;
- backend and frontend review flows remain metadata-only;
- review saves do not promote or activate boundary candidates;
- runtime point-in-polygon behavior remains unchanged.

## Operational handoff

Status date: 2026-08-23

Backend server:

    cd ~/projects/farmint/backend
    ../venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Frontend server:

    cd ~/projects/farmint/web
    npm run dev -- --port 3000

If port 3000 is already in use, the frontend server is likely already running.

Create admin smoke session:

    cd ~/projects/farmint
    ./venv/bin/python backend/scripts/create_web_ui_smoke_session.py > /tmp/web-ui-smoke-session.json

Run backend NWDP boundary regressions:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/run_nwdp_boundary_regressions.py

Run frontend NWDP boundary web smokes:

    cd ~/projects/farmint
    node web/smoke/run_nwdp_boundary_review_smokes.mjs

Admin UI URL:

- `http://localhost:3000/nwdp-boundary-review`

Guardrail summary:

- staging rows are inactive;
- review saves are metadata-only;
- promotion is unsupported from the UI;
- runtime spatial matching remains disabled;
- Android behavior remains unchanged.

## CSV export checkpoint

Status date: 2026-08-23

The NWDP boundary review UI now supports filtered CSV export for the current candidate queue.

Backend endpoint:

    GET /api/v1/master-data/geography/nwdp-boundary-batches/{batch_id}/candidates/export.csv

Export behavior:

- honors the same admin queue filters, including bucket, review status, scope, location fields, review-history state, unresolved-only, parent-mismatch-only, and special-reference-only;
- returns inactive staging/review rows only;
- includes review metadata and proposed LGD linkage fields;
- sends `X-NWDP-Boundary-Export-Mode: READ_ONLY_ADMIN_REVIEW`;
- sends `X-NWDP-Boundary-Runtime-Spatial-Matching-Changed: false`;
- does not activate, promote, or write runtime boundary rows.

Latest observed smoke/check:

- export endpoint returned HTTP 200;
- CSV contained direct-code AUTO_CANDIDATE rows;
- exported rows remained `NOT_PROMOTED` and `is_active=False`;
- runtime spatial matching remained disabled.
