# CoRE/LGD Low-Overlap Review

Status date: 2026-08-07

This document records the low-overlap review pass for dry-run CoRE polygon to LGD district overlay candidates.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/review_core_lgd_low_overlap_rows.py

Inputs:

    data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.csv
    data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.csv

Outputs:

    data/staged/core_stack/overlay_candidates/low_overlap_review/core_lgd_low_overlap_review.json
    data/staged/core_stack/overlay_candidates/low_overlap_review/core_lgd_low_overlap_review.csv

The script is read-only and does not write database rows.

## Latest local result

Summary:

- low-overlap threshold: 60%;
- low-overlap rows: 68;
- ready for manual low-overlap review: yes;
- safe for automatic DB import: no.

Bucket counts:

| Review bucket | Row count | Interpretation |
| --- | ---: | --- |
| `ECO_CLIMATIC_TRANSITION_ZONE` | 38 | District likely spans a real ecological/climatic transition boundary. |
| `MANUAL_REVIEW_REQUIRED` | 19 | Low dominant overlap without a simple automated explanation. |
| `COASTAL_OR_ISLAND_GEOMETRY` | 9 | Coastal, island, enclave, or narrow geometry likely affects overlap. |
| `SOURCE_VERSION_DRIFT` | 2 | Crosswalk says source-version mismatch; exclude from automatic import. |

By region system:

| Region system | Low-overlap rows |
| --- | ---: |
| `CORE_STACK_AGRO_CLIMATIC_ZONE` | 3 |
| `CORE_STACK_AGRO_ECOLOGICAL_ZONE` | 24 |
| `CORE_STACK_BIOGEOGRAPHIC_ZONE` | 41 |

## Interpretation

The equal-area comparison showed zero dominant-class changes, so the 68 low-overlap rows are not projection artifacts.

Most low-overlap rows are expected manual-review cases where a district intersects more than one ecological/climatic region. This can happen around:

- coastal districts;
- island or enclave-like geometries;
- districts along ecological transition boundaries;
- small/urban districts;
- source-version drift between LGD master and BharatAtlas geometry.

## Import decision

Do not import automatically.

Future importer should:

1. write all polygon-derived rows as `MANUAL_REVIEW`;
2. exclude `SOURCE_VERSION_CONFLICT` and `SOURCE_VERSION_DRIFT` rows from automatic import;
3. keep existing fallback rows active;
4. require manual review before promoting low-overlap rows;
5. keep LGD master as canonical for code/state/name truth;
6. treat BharatAtlas as operational geometry only, not canonical administrative truth.

## Android / web impact

No Android Maestro flow is required for this review.

Android and web behavior changes only after reviewed polygon-derived mappings are imported and backend `land-intelligence-context` output changes. Even then, polygon-derived climate context should be shown as guidance, not as a hard eligibility blocker.
