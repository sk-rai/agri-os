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

## Reusable activation verification and next-batch planning

Activation verification is now district-scoped:

    backend/scripts/verify_core_lgd_activation.py --state 29 --district 524 --district-name Bagalkote

The next-batch planner recommends high-overlap pilot-state district groups that still have inactive `POLY_REV` rows in `MANUAL_REVIEW`, one candidate in each CoRE region system, and an active fallback to supersede:

    backend/scripts/plan_core_lgd_next_activation_batch.py --limit 12
    backend/scripts/plan_core_lgd_next_activation_batch.py --state 29 --limit 8
    backend/scripts/plan_core_lgd_next_activation_batch.py --state 3 --limit 8

The planner is read-only. Rows still require review approval before the district-scoped activation apply script can change behavior.

## Balanced three-district activation pilot

A balanced pilot batch has been promoted after approval, dry-run, and verifier checks:

- Karnataka: Bengaluru Urban (`state_lgd_code=29`, `district_lgd_code=525`)
- Maharashtra: Beed (`state_lgd_code=27`, `district_lgd_code=470`)
- Punjab: Malerkotla (`state_lgd_code=3`, `district_lgd_code=737`)

Each promoted district has 3 active `POLY_APPR` mappings, one per CoRE region system, with review status `PROMOTED` and version `clap_v1`. Each previous starter fallback row is inactive with supersession metadata.


## Second balanced three-district activation pilot

A second balanced pilot batch has been promoted after approval, dry-run, activation, verifier checks, and land-intelligence response inspection:

- Karnataka: Bengaluru Rural (`state_lgd_code=29`, `district_lgd_code=526`)
- Maharashtra: Hingoli (`state_lgd_code=27`, `district_lgd_code=477`)
- Punjab: Sri Muktsar Sahib (`state_lgd_code=3`, `district_lgd_code=39`)

Each promoted district has 3 active `POLY_APPR` mappings, one per CoRE region system, with review status `PROMOTED` and version `clap_v1`. Each previous starter fallback row is inactive with supersession metadata.

### Clean 5-district activation batch — 2026-08-08

A guarded clean batch was approved and activated after dry-run review:

- Karnataka: Ballari (`29/528`), Bidar (`29/529`)
- Maharashtra: Ahmednagar/Ahilyanagar (`27/466`), Akola (`27/467`)
- Punjab: Amritsar (`3/27`)

Resulting active CoRE/LGD coverage:

- `POLY_APPR` active promoted rows: 36
- active promoted districts: 12
- Maharashtra: 4 districts / 12 rows
- Karnataka: 5 districts / 15 rows
- Punjab: 3 districts / 9 rows
- inactive superseded `LOCAL_DEMO_DISTRICT_FALLBACK` rows: 12
- active `LOCAL_DEMO_DISTRICT_FALLBACK` rows remaining: 174

Activation was scoped district-by-district through the guarded backend workflow.
