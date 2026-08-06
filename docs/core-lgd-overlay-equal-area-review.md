# CoRE/LGD Equal-Area Overlay Comparison

Status date: 2026-08-06

This document records the equal-area review pass for the dry-run CoRE polygon to LGD district overlay candidates.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/compare_core_lgd_overlay_equal_area.py

Inputs:

    data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson
    data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson
    data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson
    data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson
    data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv

Outputs are local staged artifacts only:

    data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.json
    data/staged/core_stack/overlay_candidates/equal_area/district_core_overlay_equal_area_comparison.csv

The script does not call external services and does not write database rows.

## Projection

The comparison uses an India Albers equal-area projection:

    +proj=aea +lat_1=12 +lat_2=32 +lat_0=0 +lon_0=78 +datum=WGS84 +units=m +no_defs

This avoids using degree-squared geometry area as the ranking measure.

## Latest local result

Summary:

- compared rows: 2,355;
- districts: 785;
- region systems: 3;
- dominant class changes after equal-area reprojection: 0;
- baseline low-overlap rows below 60%: 68;
- equal-area low-overlap rows below 60%: 68;
- ready for equal-area manual review: yes;
- ready for DB import: no.

| Region system | Dominant class changes | Baseline low-overlap rows | Equal-area low-overlap rows | Baseline min overlap % | Equal-area min overlap % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `CORE_STACK_AGRO_CLIMATIC_ZONE` | 0 | 3 | 3 | 53.0926 | 52.9643 |
| `CORE_STACK_AGRO_ECOLOGICAL_ZONE` | 0 | 24 | 24 | 42.6883 | 42.6918 |
| `CORE_STACK_BIOGEOGRAPHIC_ZONE` | 0 | 41 | 41 | 39.3395 | 39.3263 |

## Interpretation

Equal-area ranking did not change the selected dominant CoRE class for any district/region-system row.

That means the earlier 68 low-overlap rows are not primarily caused by latitude/longitude area distortion. They should be treated as real manual-review rows caused by one or more of:

- districts crossing ecological or climatic transition boundaries;
- coastal, island, or narrow/fringe district geometry;
- district split/version mismatch between LGD-compatible boundaries and CoRE source layers;
- genuine ambiguity where one district is materially split across two CoRE regions.

## Import decision

Do not import yet.

The area-method blocker is now reduced: equal-area comparison supports keeping the existing dominant candidates for manual review. Remaining blockers are:

1. duplicate district-code review in the BharatAtlas/LGD boundary file;
2. manual review of the 68 low-overlap rows;
3. importer design that writes polygon-derived rows as `MANUAL_REVIEW` only;
4. precedence strategy so existing district fallback rows remain active until polygon-derived rows are reviewed and trusted.

## Android and web impact

No Android Maestro flow is required for this comparison.

There is no direct web or Android behavior change until backend imports reviewed polygon-derived mappings and the `land-intelligence-context` output changes. Today, the existing district fallback remains the safer production/demo path.

Once reviewed mappings are imported, Android and web should display them as guidance, with provenance/confidence labels, not as hard eligibility blockers.
