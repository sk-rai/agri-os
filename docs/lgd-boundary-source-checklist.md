# LGD Boundary Source Checklist

Status date: 2026-07-27

This checklist tracks boundary sources needed for CoRE polygon to LGD geography overlay.

## Purpose

The backend already has LGD tabular geography: states, districts, blocks, villages, and PIN linkage.

For polygon-derived climate/ecology mapping, we also need boundary geometry. The target is to intersect:

- CoRE Stack agro-climatic/agro-ecological/biogeographic polygons;
- official administrative boundaries;
- optional parcel GPS points.

## Recommended source priority

### 1. Survey of India / India Maps

Preferred source for official boundary geometry.

Relevant products include:

- Administrative Boundary Database;
- state/district/sub-district boundary database;
- village boundary database.

Use for:

- district polygon overlay;
- sub-district/taluk overlay;
- village polygon overlay if available and usable.

Source links:

- https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-
- https://onlinemaps.surveyofindia.gov.in/Digital_Products.aspx
- https://indiamaps.gov.in/product

Notes:

- Verify download/access requirements.
- Verify license/usage restrictions.
- Verify whether attributes include LGD codes directly.
- If LGD codes are missing, build a reviewed crosswalk using state/district names and LGD directory.

### 2. LGD Directory

Preferred source for official administrative codes and names.

Use for:

- state/district/sub-district/block/village codes;
- tabular crosswalk;
- validating boundary attributes.

Source link:

- https://lgdirectory.gov.in/demo/downloadDirectory.do

Notes:

- LGD is authoritative for codes, but not necessarily polygon geometry.
- Use LGD as the canonical identity layer.

### 3. Open Government Data Admin Boundaries

Possible secondary/open boundary source.

Source link:

- https://www.data.gov.in/catalog/admin-boundaries

Notes:

- Validate freshness.
- Validate geometry level and attribute schema.
- Do not assume LGD-code compatibility without inspection.

### 4. Third-party shapefile mirrors

Use only as research hints unless licensing and provenance are clear.

Examples include GIS blogs or public mirrors claiming SOI-derived shapefiles.

Policy:

- Do not use as authoritative production source.
- Do not mark mappings as official if derived from unverified third-party mirrors.

## Expected local staging paths

Place downloaded/exported boundary files under:

    data/staged/boundaries/

Suggested structure:

    data/staged/boundaries/soi/
    data/staged/boundaries/ogd/
    data/staged/boundaries/lgd_directory/
    data/staged/boundaries/review_notes/

Do not commit large boundary files unless explicitly approved. Keep them staged/local.

## Minimum viable overlay path

For selected-state demo improvement:

1. Obtain district boundary polygons for Maharashtra, Karnataka, Uttar Pradesh, Punjab, and West Bengal.
2. Verify state/district names and codes against LGD.
3. Intersect district polygons with CoRE polygons.
4. Assign each LGD district to the dominant CoRE region by area overlap.
5. Store mapping confidence as `POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW`.
6. Keep `MANUAL_REVIEW` until reviewed.

## Full production overlay path

1. Obtain official district/sub-district/village boundary geometry.
2. Normalize geometry projection to WGS84 or a suitable equal-area projection for area calculations.
3. Validate geometry integrity.
4. Join/crosswalk boundary attributes to LGD codes.
5. Intersect with CoRE AEZ/ACZ/biogeographic polygons.
6. Generate mapping candidates.
7. Review edge cases where one administrative unit overlaps multiple zones.
8. Write reviewed rows into `geography_climate_region_mappings`.

## Review checks

Before importing overlay mappings:

- source URL recorded;
- license/usage terms recorded;
- file date/version recorded;
- geometry level confirmed;
- LGD code fields confirmed or crosswalk reviewed;
- projection/CRS confirmed;
- overlap method documented;
- manual-review status retained.

## Android rule

Android does not consume boundary files.

Android continues to call backend intelligence endpoints, such as:

    GET /api/v1/profile/land-intelligence-context

Backend owns all climate/geography overlay logic.
