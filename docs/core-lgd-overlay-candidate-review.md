# CoRE/LGD Overlay Candidate Review

Status date: 2026-08-06

This document records the first review/audit pass over the dry-run district overlay candidates.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/review_core_lgd_overlay_candidates.py

Input:

    data/staged/core_stack/overlay_candidates/district_core_overlay_candidates.csv

The review script is read-only and does not write database rows.

## Latest local result

Summary:

- candidate rows: 2,355;
- districts: 785;
- region systems: 3;
- ready for manual review: yes;
- ready for DB import: no.

Rows below 60% dominant overlap:

| Region system | Minimum overlap % | Median overlap % | Low-overlap rows |
| --- | ---: | ---: | ---: |
| `CORE_STACK_AGRO_CLIMATIC_ZONE` | 53.0926 | 99.9303 | 3 |
| `CORE_STACK_AGRO_ECOLOGICAL_ZONE` | 42.6883 | 99.6335 | 24 |
| `CORE_STACK_BIOGEOGRAPHIC_ZONE` | 39.3395 | 99.7601 | 41 |

Total low-overlap rows below 60%:

    68

## Lowest-overlap examples

### Agro-Climatic Zone

- Rajasthan / Anoopgarh: 53.0926% — Trans Gangetic Plain Region
- Punjab / Rupnagar: 55.7644% — Western Himalayan Region
- Punjab / Pathankot: 57.5358% — Western Himalayan Region

### Agro-Ecological Zone

- Andhra Pradesh / East Godavari: 42.6883% — Deccan Plateau / Telangana / Eastern Ghats hot semi-arid eco-region
- Maharashtra / Nandurbar: 49.4313% — Central Highlands / Malwa / Gujarat Plain / Kathiawar semi-arid eco-region
- Jharkhand / Ranchi: 50.2084% — Eastern Plateau / Chhotanagpur / Eastern Ghats hot subhumid eco-region
- Odisha / Bhadrak: 51.4870% — Eastern Coastal Plain hot subhumid to semi-arid eco-region
- Gujarat / Surendranagar: 52.3061% — Western Plain / Kachchh / Kathiawar hot arid eco-region

### Biogeographic Zone

- Andhra Pradesh / East Godavari: 39.3395% — Deccan Peninsula
- Dadra, Nagar Haveli, Daman & Diu / Daman: 44.7697% — Western Ghats
- Odisha / Jajapur: 44.8721% — Gangetic Plain
- Chhattisgarh / Korba: 45.2139% — Deccan Peninsula
- Odisha / Cuttack: 47.9051% — Deccan Peninsula

## Interpretation

Most district candidates have very high dominant overlap, but low-overlap rows are expected near:

- district borders;
- coastal/fringe districts;
- newly split or updated districts;
- districts spanning ecological transition zones;
- possible boundary source/version mismatch.

These rows need manual review before any import.

## Import decision

Do not import these candidates yet.

Remaining blockers:

1. Bharatlas source/provenance/license decision;
2. review of low-overlap rows;
3. decision on whether to rerun area ranking with equal-area projection;
4. importer design that writes `MANUAL_REVIEW` rows only;
5. fallback precedence strategy between existing district fallback rows and polygon-derived rows.

## Android impact

No Android Maestro flow is required for candidate review.

Android testing becomes relevant only after reviewed mappings are imported and backend `land-intelligence-context` output changes for known test locations.
