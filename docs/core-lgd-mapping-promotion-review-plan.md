# CoRE/LGD Mapping Promotion Review Plan

Status date: 2026-08-07

This document records the read-only promotion review plan for inactive polygon-derived CoRE/LGD candidate mappings.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/plan_core_lgd_mapping_promotion_review.py

The script is read-only. It does not write database rows.

## Source rows

The planner reads inactive/manual-review rows in `geography_climate_region_mappings` with:

| Field | Value |
| --- | --- |
| `confidence` | `POLY_REV` |
| `review_status` | `MANUAL_REVIEW` |
| `is_active` | `false` |
| `version` | `clri_v1` |

These rows were imported from the BharatAtlas/CoRE equal-area overlay review plan.

## Promotion policy

No row is automatically promoted.

The planner classifies rows into review buckets:

| Bucket | Meaning |
| --- | --- |
| `PILOT_REVIEW_REPLACES_FALLBACK` | Candidate is in pilot states and has high overlap; would replace an active fallback only after explicit promotion |
| `GENERAL_REVIEW_REPLACES_FALLBACK` | Candidate is outside pilot states and would replace an active fallback only after explicit promotion |
| `GENERAL_REVIEW_NEW_MAPPING` | Candidate is outside pilot states and has no active fallback |
| `MANUAL_REVIEW_LOW_OVERLAP` | Candidate requires deeper review because overlap is below threshold or low-overlap bucket flagged it |
| `BLOCKED_*` | Source-version/crosswalk issue; should not be promoted |

Pilot states:

- Karnataka (`29`)
- Maharashtra (`27`)
- Punjab (`3`)

High-overlap threshold:

- 80% district overlap

## Latest local result

Summary:

| Decision | Count |
| --- | ---: |
| `PILOT_REVIEW_REPLACES_FALLBACK` | 236 |
| `GENERAL_REVIEW_REPLACES_FALLBACK` | 264 |
| `GENERAL_REVIEW_NEW_MAPPING` | 1,617 |
| `MANUAL_REVIEW_LOW_OVERLAP` | 181 |
| Blocked rows | 0 |

By region system:

| Region system | Pilot replaces fallback | General replaces fallback | General new | Manual low-overlap |
| --- | ---: | ---: | ---: | ---: |
| Agro-climatic zone | 87 | 97 | 579 | 3 |
| Agro-ecological zone | 76 | 84 | 541 | 65 |
| Biogeographic zone | 73 | 83 | 497 | 113 |

## Interpretation

The planner found a useful pilot set: 236 high-overlap candidate rows in Karnataka, Maharashtra, and Punjab. These are good candidates for an admin review surface because they cover already-seeded fallback districts and would let us compare fallback vs polygon-derived region assignments before changing production behavior.

The 181 low-overlap rows should not be promoted without manual geographic review.

## Android / web impact

No Android Maestro flow is required for this planner.

Android and web behavior remains unchanged because all `POLY_REV` rows are inactive.

Testing is needed only after a future explicit promotion step changes effective `land-intelligence-context` output.
