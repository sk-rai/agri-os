# Village resolution local-evidence API reuse — 2026-10-04

## Decision

No cohort-specific endpoint is introduced. The existing admin-only
`GET /api/v1/master-data/geography/village-resolution` endpoint remains the
single canonical-village resolution read surface.

Its existing state, district, resolution-status, search and pagination behavior
is backward-compatible. Optional local-evidence filters and fields are additive.

## Snapshot read model

Migration 066 adds a versioned snapshot header and village evidence items. The
active snapshot contains all 7,493 canonical villages classified by the
validated local-evidence report, rather than a hard-coded 140-row cohort.

The snapshot can therefore serve current and future reconciliation runs without
adding routes for every new state, village set or evidence batch. Only one
snapshot may be active.

## Controlled refresh

`load_canonical_village_resolution_evidence_snapshot.py` validates the
local-evidence delta and collision-aware packet. Its default mode is a
transactionally rolled-back dry run. Loading requires `--apply` and the
explicit confirmation phrase `LOAD CANONICAL LOCAL EVIDENCE SNAPSHOT`.

Activation changes only the evidence read model. It does not update canonical
villages, PIN links, NWDP candidates, runtime crosswalks, project resolutions or
Android behavior remains unchanged.

## Additive API fields

Each village may now include:

- local evidence disposition and candidate count;
- best match rank and basis;
- the single source-feature identity where applicable;
- source reuse count and collision status;
- review eligibility;
- prior candidate evidence.

Optional filters select evidence disposition, review eligibility and collision
status. Villages outside an active snapshot retain null evidence fields.

## Review boundary

`TWO_SESSION_REVIEW_ELIGIBLE` is evidence readiness, not approval.
`CONFLICT_REVIEW_REQUIRED` cannot be accepted while one NWDP source is shared
by multiple canonical villages. Ambiguous and no-candidate rows remain blocked.

The endpoint is read-only. No review decision, canonical mapping, runtime
activation, project resolution or Android exposure is performed.
