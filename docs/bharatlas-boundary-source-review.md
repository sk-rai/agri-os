# BharatAtlas Boundary Source Review

Status date: 2026-08-06

This document records the source/provenance decision for the staged BharatAtlas LGD district boundary GeoJSON.

## File

Local staged file:

    data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson

Source page:

    https://bharatlas.com/view/lgd_districts

## Decision

BharatAtlas LGD Districts is acceptable for:

- dry-run CoRE/LGD overlay candidate generation;
- backend pipeline development;
- manual-review QA.

BharatAtlas LGD Districts is not accepted as:

- `GOVT_SOURCE`;
- `OFFICIAL_BOUNDARY`;
- `AUTHORITATIVE_BOUNDARY`;
- production-trusted mapping without review.

If later imported, derived rows must remain:

- `confidence = POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW`;
- `review_status = MANUAL_REVIEW`;
- source metadata must record BharatAtlas as an unofficial republication.

## Rationale

BharatAtlas appears to provide clean downloadable district boundary geometry with LGD-compatible fields, and the file is very useful for building and validating the overlay pipeline.

However, BharatAtlas is not an official government website. It is an open-source/community geospatial platform that republishes/cleans data reported to originate from government sources such as LGD, Survey of India, Bhuvan/NRSC, NIC, and Bharat Maps.

For official/legal/production-authoritative use, prefer direct government sources such as:

- Survey of India / India Maps;
- Bharat Maps / NIC;
- LGD Directory for canonical codes;
- reviewed OGD/Data.gov.in boundary resources where available.

## Review script

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/review_bharatlas_boundary_source.py

The script is read-only and does not write database rows.

## Latest local review result

File summary:

- feature count: 785;
- state code count: 36;
- distinct district code count: 783;
- geometry types: Polygon/MultiPolygon only;
- required LGD fields present: yes.

Detected useful fields:

- `state_lgd`
- `dist_lgd`
- `stcode11`
- `dtcode11`
- `stname`
- `dtname`

Readiness:

- acceptable for dry-run candidates: yes;
- acceptable as authoritative source: no;
- ready for DB import without review: no.

## Caveats before import

The file contains 785 district features but 783 distinct `dist_lgd` values. Before any import, review duplicate/multi-feature district-code cases and confirm they are expected geometry multipart/admin-update behavior rather than data quality issues.

Also review:

1. BharatAtlas license/provenance terms;
2. low-overlap overlay candidates;
3. whether overlap ranking should use equal-area projection;
4. fallback precedence against existing demo district fallback rows.

## Android impact

No Android Maestro flow is required for this source review.

Android continues to consume backend-owned outputs only after reviewed mappings are imported.
