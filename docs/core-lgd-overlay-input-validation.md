# CoRE/LGD Overlay Input Validation

Status date: 2026-08-06

This document records the dry-run validator for local CoRE polygon exports and LGD-compatible boundary candidates.

## Purpose

Before generating overlay candidates or importing rows into `geography_climate_region_mappings`, backend should verify that local geospatial inputs are present and structurally usable.

The validator is intentionally read-only:

- no Google Earth Engine calls;
- no boundary source downloads;
- no database writes;
- no overlay candidate generation;
- no Android calls.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/validate_core_lgd_overlay_inputs.py

## What it checks

### CoRE Stack exports

Expected directory:

    data/staged/core_stack/exports/

Expected files:

- `Agro_Ecological_Zones.geojson`
- `Agro_Climatic_Zones.geojson`
- `Biogeographic_Zone_pan_india.geojson`

For each file, the validator checks:

- readable GeoJSON;
- root type is `FeatureCollection`;
- non-zero feature count;
- polygon/multipolygon geometry types;
- empty geometry count;
- sample property keys;
- required class property coverage:
  - `physio_reg`;
  - `regionname`;
  - `biogeozone`;
- bounding box;
- CRS declaration, or GeoJSON default WGS84 lon/lat note.

### Boundary candidates

Expected staging root:

    data/staged/boundaries/

The validator recursively detects:

- `.geojson`
- `.json`
- `.shp`

For GeoJSON boundary candidates, it checks the same structural geometry properties and searches for likely LGD-code hint fields for:

- state;
- district;
- block/subdistrict;
- village.

For Shapefiles, it reports sidecar presence:

- `.shp`
- `.shx`
- `.dbf`
- `.prj`

The current script does not parse Shapefile geometry directly. Convert to GeoJSON or inspect with GIS/geopandas before overlay.

## Latest local result

Current local validation result:

- CoRE export directory not present;
- all three expected CoRE GeoJSON exports missing;
- boundary staging directory not present;
- boundary candidates found: 0;
- malformed inputs found: no;
- ready for dry-run overlay: no.

This is expected until CoRE exports and reviewed boundary candidates are staged locally.

## Readiness meaning

`ready_for_dry_run_overlay` becomes true only when:

- all three CoRE exports are structurally ready;
- at least one boundary GeoJSON candidate is structurally ready;
- at least one boundary candidate has likely LGD-code hint fields;
- no malformed inputs are found.

This still does not mean mappings are production-authoritative. It only means the next dry-run overlay candidate generator has enough local input to start.

## Android impact

No Android Maestro flow is required for this validation step.

Android continues to consume backend-owned context through:

    GET /api/v1/profile/land-intelligence-context

Maestro should be considered later only after reviewed polygon-derived mappings change backend response payloads for known test locations.
