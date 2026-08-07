# CoRE/LGD Admin Review Surface

Status date: 2026-08-07

This document records the admin read-only review surface for CoRE/LGD polygon-derived mapping candidates.

## Backend endpoint

Endpoint:

    GET /api/v1/master-data/geography/core-lgd-mapping-review

Permission:

    Admin VIEW

Supported filters:

- `state_lgd_code`
- `district_lgd_code`
- `region_system`
- `promotion_decision`
- `search`
- `offset`
- `limit`

The endpoint is read-only. It does not activate, promote, or mutate mapping rows.

## Web admin page

Page:

    /core-lgd-review

Sidebar:

    Configuration → CoRE LGD Review

The page supports:

- state filter;
- district LGD filter;
- CoRE region-system filter;
- promotion-decision filter;
- search;
- pagination;
- side-by-side comparison of inactive `POLY_REV` candidates and active fallback mappings.

## Automated checks

Backend endpoint regression:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/test_core_lgd_admin_review_endpoint.py

Web smoke test:

    cd ~/projects/farmint/backend
    eval "$(../venv/bin/python scripts/create_web_ui_smoke_session.py --tenant-id default --role ENTERPRISE_ADMIN --format exports)"

    cd ~/projects/farmint/web
    node smoke/core_lgd_review_smoke.mjs

Latest local result:

- backend endpoint regression passed;
- web smoke passed;
- screenshot captured locally at `web/smoke/screenshots/core-lgd-review.png`.

The screenshot is a local artifact and is not committed by default.

## Governance

This surface intentionally does not include promotion controls.

Promotion/activation must be implemented as a separate explicit review workflow with stronger guardrails.

## Android / web impact

No Android Maestro flow is required for this read-only admin surface.

Android land-intelligence behavior remains unchanged because `POLY_REV` rows are inactive.


## Review decision workflow

The admin surface supports review decisions for inactive `POLY_REV` rows:

- `APPROVED_FOR_PROMOTION`
- `REJECTED`
- `MANUAL_REVIEW`

Endpoint:

    PATCH /api/v1/master-data/geography/core-lgd-mapping-review/{mapping_id}/review

Permission:

    Admin EDIT

This endpoint updates review metadata/status only. It never activates a mapping row and does not change land-intelligence behavior. Approved rows require a later explicit promotion workflow.


## Approved mapping activation planning

Approved candidates are not activated automatically. The read-only planner:

    backend/scripts/plan_core_lgd_approved_mapping_activation.py

reports only inactive `POLY_REV` rows with `review_status=APPROVED_FOR_PROMOTION`.

Current expected baseline after regression reset:

- approved rows: 0
- eligible rows: 0
- DB writes: false

A later apply workflow must be explicit and must run verifier/Android smoke coverage because activation changes land-intelligence behavior.


## Bagalkote activation pilot

Bagalkote, Karnataka (`state_lgd_code=29`, `district_lgd_code=524`) has been promoted as the first CoRE/LGD activation pilot.

Result:

- activated rows: 3
- active confidence: `POLY_APPR`
- review status: `PROMOTED`
- version: `clap_v1`
- superseded active fallback rows: 1
- land-intelligence mapping precision: `SOURCE_DERIVED`

Scripts:

    backend/scripts/apply_core_lgd_approved_mapping_activation.py
    backend/scripts/verify_core_lgd_bagalkote_activation.py

The apply script is district-scoped, dry-run by default, and requires explicit `--apply`.
