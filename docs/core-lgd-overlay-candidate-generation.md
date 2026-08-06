# CoRE/LGD Overlay Candidate Generation

Status date: 2026-08-06

This document records the first dry-run district overlay candidate generation using:

- normalized CoRE Stack polygon exports;
- Bharatlas LGD district boundary GeoJSON.

This is not a database import. Candidate rows remain manual-review artifacts.

## Commands

Generate candidates:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/generate_core_lgd_overlay_candidates.py

Verify candidates:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/verify_core_lgd_overlay_candidates.py

## Dependency

The generator requires:

    shapely==2.0.6

This is pinned in:

    backend/requirements.txt

The script refuses to run polygon intersections without `shapely`; it does not use bbox-only approximations.

## Inputs

Normalized CoRE files:

    data/staged/core_stack/exports_normalized/Agro_Ecological_Zones.normalized.geojson
    data/staged/core_stack/exports_normalized/Agro_Climatic_Zones.normalized.geojson
    data/staged/core_stack/exports_normalized/Biogeographic_Zone_pan_india.normalized.geojson

District boundary candidate:

    data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson

Detected district boundary fields:

- `state_lgd`
- `stcode11`
- `dist_lgd`
- `dtcode11`
- `stname`
- `dtname`

## Outputs

Generated local review files:

    data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.json
    data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv

Do not commit these generated candidate files unless explicitly approved.

## Latest local result

Candidate generation result:

- districts seen: 785;
- CoRE features seen: 61;
- candidate rows: 2,355;
- no-overlap rows: 0;
- candidate files written: yes;
- DB writes: no.

Verifier result:

- JSON/CSV row counts match;
- district count: 785;
- one row per district per CoRE region system;
- `CORE_STACK_AGRO_ECOLOGICAL_ZONE`: 785 rows;
- `CORE_STACK_AGRO_CLIMATIC_ZONE`: 785 rows;
- `CORE_STACK_BIOGEOGRAPHIC_ZONE`: 785 rows;
- all rows are `DISTRICT` scope;
- all rows remain `MANUAL_REVIEW`;
- ready for manual review: yes;
- ready for DB import: no.

## Method

For each LGD district polygon and each CoRE region system:

1. intersect district polygon with each CoRE zone polygon;
2. calculate overlap area in source lon/lat coordinate units;
3. choose the dominant overlap candidate by area;
4. emit one candidate row per district and region system.

Important caution: area is calculated in source coordinate units for dry-run ranking only. Before authoritative production use, review whether an equal-area projection should be added.

## Android impact

No Android Maestro flow is required for candidate generation.

Android should only be tested later if reviewed/imported mappings change:

    GET /api/v1/profile/land-intelligence-context

for known test PIN/district/parcel contexts.

## Next backend step

Before DB import:

1. review sample candidate rows across several states/districts;
2. verify Bharatlas source/license/provenance is acceptable for this use;
3. decide whether dry-run ranking needs equal-area reprojection;
4. design importer that writes mappings as `MANUAL_REVIEW`;
5. preserve district fallback rows until reviewed polygon-derived rows are trusted.
