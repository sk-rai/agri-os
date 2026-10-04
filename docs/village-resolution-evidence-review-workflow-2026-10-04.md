# Village resolution evidence review workflow — 2026-10-04

## Outcome

The existing geography readiness screen and existing
`GET /api/v1/master-data/geography/village-resolution` endpoint are reused for
the canonical unresolved evidence cohort. No cohort-specific lookup endpoint is
introduced.

The read-only Playwright smoke validates the current active snapshot:

- Rajasthan has 98 `TWO_SESSION_REVIEW_ELIGIBLE` villages;
- Rajasthan has 15 source-collision rows;
- eligible results exclude collision rows;
- filtering does not create review decisions or mutate geography.

## Reusable review model

Migration `067` adds a snapshot-linked review record and immutable event
history. A review is keyed by the active evidence snapshot and evidence item,
so a future validated snapshot can reuse the same workflow without introducing
another endpoint or table.

Primary decisions are:

- `ACCEPT_FOR_SECOND_REVIEW`;
- `REJECT`;
- `HOLD`.

Only evidence marked `TWO_SESSION_REVIEW_ELIGIBLE`, with a source feature and
without a source collision, can be accepted into the second-review queue.

Second decisions are:

- `APPROVE`;
- `REJECT`;
- `HOLD`.

The second reviewer must:

- be an independently authenticated enterprise administrator;
- differ from the primary reviewer;
- submit the exact confirmation phrase
  `COMPLETE SECOND VILLAGE EVIDENCE REVIEW`.

## API surface

The reusable API is deliberately generic:

- `GET /api/v1/master-data/geography/village-resolution/reviews` lists the
  active-snapshot review queue and immutable events;
- `POST /api/v1/master-data/geography/village-resolution/reviews` records a
  primary decision;
- `POST /api/v1/master-data/geography/village-resolution/reviews/{review_id}/second-review`
  records the independent second decision.

These routes are review infrastructure, not per-cohort lookup endpoints.

## Safety boundary

An `APPROVED` evidence review is not an applied canonical mapping. This
workflow:

- does not update `geography_villages`;
- does not create or change PIN links;
- does not create candidate or runtime crosswalks;
- does not change project geography;
- does not expose a village to Android;
- does not authorize automatic application.

Any future apply operation requires a separate design, validation suite,
authorization, rollback contract, and explicit gate.

## Validation

- `backend/scripts/test_village_resolution_evidence_filter_web_smoke_static.py`
- `web/smoke/village_resolution_evidence_filter_smoke.mjs`
- `backend/scripts/test_village_resolution_evidence_review_workflow_static.py`
- `backend/scripts/test_village_resolution_evidence_review_workflow.py`
