# BharatAtlas / Backend LGD District Crosswalk Review

Status date: 2026-08-07

This document tracks comparison between the staged BharatAtlas LGD district boundary file and the backend `geography_districts` / `geography_states` master data.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/audit_bharatlas_backend_lgd_district_crosswalk.py

Input:

    data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson

Outputs:

    data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.json
    data/staged/core_stack/lgd_crosswalk/bharatlas_backend_lgd_district_crosswalk.csv

The script is read-only and does not write database rows.

## Latest local result

Summary:

- BharatAtlas district features: 785;
- BharatAtlas distinct district LGD codes: 783;
- backend district rows: 778;
- backend distinct district LGD codes: 778;
- exact matches: 716;
- matched name variants: 50;
- state-code mismatches: 1;
- BharatAtlas-only rows: 16;
- backend-only rows: 11;
- duplicate BharatAtlas district LGD codes: 0;
- duplicate backend district LGD codes: 0;
- ready for manual crosswalk review: yes;
- safe for dry-run overlay review: yes;
- safe for automatic DB import: no.

## State-code mismatch

One hard mismatch was found:

| District LGD code | Backend district/state | BharatAtlas district/state | Decision |
| --- | --- | --- | --- |
| `766` | MAUGANJ, Madhya Pradesh | Itanagar capital complex, Arunachal Pradesh | Exclude from automatic import; requires manual LGD/source-version review. |

This is not a spelling or alias issue. It is a source-version/code conflict.

## Interpretation

Most overlapping LGD district codes are usable for dry-run overlay review. The 50 name variants are mostly spelling/spacing/case differences and should be handled as alias/crosswalk review, not automatic rejection.

The 16 BharatAtlas-only and 11 backend-only rows show source-version drift. Backend-only rows include newer districts for which BharatAtlas geometry may not yet exist. BharatAtlas-only rows include older/census or UT-style district geometry rows that backend geography master does not currently contain.

The single state-code mismatch must be manually reviewed before any importer can be trusted.

## Recommendation

Use BharatAtlas `dist_lgd` as the district geometry key for dry-run/manual-review overlay work.

Do not mark BharatAtlas as an authoritative government source. It can be treated as an operational LGD-compatible boundary republication for candidate review, with source/provenance caveats.

Do not import automatically.

Future importer should:

1. write polygon-derived rows as `MANUAL_REVIEW`;
2. keep existing fallback rows active until reviewed polygon mappings are trusted;
3. treat `BHARATLAS_ONLY` and `BACKEND_ONLY` rows as source-version drift;
4. exclude `STATE_CODE_MISMATCH` rows from automatic import;
5. require manual crosswalk for unresolved name variants;
6. avoid replacing district fallback mappings automatically.

## Android / web impact

No Android Maestro flow is required for this crosswalk review.

Android and web behavior changes only after reviewed polygon-derived mappings are imported and backend `land-intelligence-context` output changes.
