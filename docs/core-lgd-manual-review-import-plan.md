# CoRE/LGD Manual-Review Import Plan

Status date: 2026-08-07

This document records the conservative import plan for CoRE polygon to LGD district climate mappings.

The current plan is read-only. No database rows have been written.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/plan_core_lgd_manual_review_import.py

Inputs:

    data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.csv
    data/staged/core_stack/overlay_candidates/low_overlap_review/core_lgd_low_overlap_review.csv
    data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.csv

Outputs:

    data/staged/core_stack/manual_review_import_plan/core_lgd_manual_review_import_plan.json
    data/staged/core_stack/manual_review_import_plan/core_lgd_manual_review_import_plan.csv

The script is read-only and does not write database rows.

## Latest local result

Summary:

- total candidate rows: 2,355;
- rows that would be staged as manual-review candidates: 2,298;
- rows excluded from import plan: 57;
- existing same-region district mapping collisions: 0;
- safe to run DB import now: no.

Exclusion reasons:

| Reason | Count |
| --- | ---: |
| `district missing in backend LGD master` | 54 |
| `crosswalk category BHARATLAS_ONLY` | 48 |
| `crosswalk category STATE_CODE_MISMATCH` | 3 |
| `low-overlap bucket SOURCE_VERSION_DRIFT` | 2 |

Counts overlap because one row can have more than one exclusion reason.

## Planned import policy

If implemented later, the importer should write candidate rows with:

| Field | Planned value |
| --- | --- |
| `review_status` | `MANUAL_REVIEW` |
| `confidence` | `POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW` |
| `is_active` | `false` |
| effective in `land-intelligence-context` | no |
| fallback replacement | no |
| LGD source of truth | backend LGD master |
| geometry source role | BharatAtlas operational geometry only |

## Source hierarchy

Use this hierarchy:

1. backend LGD master: canonical district/state code and name truth;
2. CoRE GEE exports: climate/ecological polygon source;
3. BharatAtlas: operational LGD-compatible district geometry;
4. existing fallback mappings: active app/web behavior until reviewed polygon rows are promoted.

## Import decision

Do not import yet.

The planner is ready for importer design, but DB writes should wait until:

1. excluded rows are reviewed;
2. the state-code mismatch for LGD `766` is resolved;
3. source-version drift rows are handled;
4. manual-review UI/admin workflow or review process is defined;
5. promotion semantics are defined separately from candidate insertion.

## Android / web impact

No Android Maestro flow is required for this import plan.

Android and web behavior changes only after reviewed polygon-derived mappings are imported and promoted into effective `land-intelligence-context` output. Even then, climate context should remain guidance, not a hard eligibility blocker.
