# CoRE Stack GEE Export Checklist

Status date: 2026-07-27

This checklist records how to export CoRE Stack agro-ecological, agro-climatic, and biogeographic zone geometry from Google Earth Engine for backend climate/geography mapping.

## Purpose

The CoRE Stack layers provide polygon boundaries for climate/ecology zones across India. These polygons can later be intersected with LGD district/block/village boundaries or parcel GPS points to produce reviewed `geography_climate_region_mappings`.

Android must not call Google Earth Engine directly. Android consumes backend-safe intelligence endpoints only.

## Current backend state

Closed:

- CoRE layer manifest generated.
- CoRE class names imported into `geography_climate_regions`.
- Five selected-state district fallback mappings seeded for demo use.
- Android land intelligence endpoint and sample added.

Active next:

- Export CoRE geometries.
- Locate compatible LGD boundary geometries.
- Build polygon overlay workflow.

## Source trail

Primary discovery page:

    https://aikosh.indiaai.gov.in/web/datasets/details/agro_ecological_climatic_and_biogeographic_zone.html

CoRE Stack dataset directory:

    https://core-stack.org/datasets-contents/

CoRE Stack GEE directory app:

    https://ee-corestackdev.projects.earthengine.app

Methodology/manual:

    https://core-stack.org/core-stack-technical-manual-v2/

Local source CSV:

    data/staged/core_stack/CoRE Stack GEE Layers Links - Datasets.csv

Local manifest:

    data/staged/core_stack/core_stack_climate_layer_manifest.json

Safe source probe:

    backend/scripts/probe_core_lgd_download_sources.py
    docs/core-lgd-download-source-probe.md

## Source layers

### Agro-Ecological Zone

GEE asset:

    projects/ext-datasets/assets/datasets/Agro_Ecological_Zones

Class property:

    physio_reg

Expected local export names:

    data/staged/core_stack/exports/Agro_Ecological_Zones.geojson
    data/staged/core_stack/exports/Agro_Ecological_Zones.shp

Backend region system:

    CORE_STACK_AGRO_ECOLOGICAL_ZONE

### Agro-Climatic Zone

GEE asset:

    projects/ext-datasets/assets/datasets/Agro_Climatic_Zones

Class property:

    regionname

Expected local export names:

    data/staged/core_stack/exports/Agro_Climatic_Zones.geojson
    data/staged/core_stack/exports/Agro_Climatic_Zones.shp

Backend region system:

    CORE_STACK_AGRO_CLIMATIC_ZONE

### Biogeographic Zone

GEE asset:

    projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india

Class property:

    biogeozone

Expected local export names:

    data/staged/core_stack/exports/Biogeographic_Zone_pan_india.geojson
    data/staged/core_stack/exports/Biogeographic_Zone_pan_india.shp

Backend region system:

    CORE_STACK_BIOGEOGRAPHIC_ZONE

## What these files contain

Each export should contain geospatial features.

Each feature normally has:

- geometry:
  - polygon or multipolygon boundary;
  - coordinate pairs in longitude/latitude or projected coordinates depending on export format;
- properties:
  - zone class/name field such as `regionname`, `physio_reg`, or `biogeozone`;
  - possible source/style/helper fields.

These are not village coordinates. They are zone boundaries.

## Recommended export format

Preferred first export:

    GeoJSON

Reason:

- easiest to inspect locally;
- easy to validate with Python and GIS tools;
- suitable for early overlay experiments.

Secondary export:

    Shapefile

Reason:

- common GIS compatibility;
- may be useful with QGIS or geopandas workflows.

## Google Earth Engine export concept

For each layer:

1. Load the FeatureCollection.
2. Export the FeatureCollection to Google Drive or Cloud Storage.
3. Download the exported file locally.
4. Copy it into:

       data/staged/core_stack/exports/

5. Run:

       cd ~/projects/farmint/backend
       ../venv/bin/python scripts/audit_climate_polygon_overlay_readiness.py

## Example GEE snippets

Agro-Climatic Zone:

    var acz = ee.FeatureCollection('projects/ext-datasets/assets/datasets/Agro_Climatic_Zones');

    Export.table.toDrive({
      collection: acz,
      description: 'Agro_Climatic_Zones',
      fileFormat: 'GeoJSON'
    });

Agro-Ecological Zone:

    var aez = ee.FeatureCollection('projects/ext-datasets/assets/datasets/Agro_Ecological_Zones');

    Export.table.toDrive({
      collection: aez,
      description: 'Agro_Ecological_Zones',
      fileFormat: 'GeoJSON'
    });

Biogeographic Zone:

    var bgz = ee.FeatureCollection('projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india');

    Export.table.toDrive({
      collection: bgz,
      description: 'Biogeographic_Zone_pan_india',
      fileFormat: 'GeoJSON'
    });

## Local validation after download

Expected directory:

    data/staged/core_stack/exports/

Expected files:

    Agro_Ecological_Zones.geojson
    Agro_Climatic_Zones.geojson
    Biogeographic_Zone_pan_india.geojson

Run readiness audit:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/audit_climate_polygon_overlay_readiness.py

Expected improvement:

- `core_polygon_exports_ready` should become true once all expected exports are present.
- `ready_for_polygon_overlay` should become true if district LGD reference remains ready.

## Overlay strategy

Preferred mapping order:

1. Parcel GPS point-in-polygon where parcel centroid exists.
2. Village point-in-polygon if village coordinates are available and source-reviewed.
3. District polygon intersection when official LGD district boundaries are available.
4. Current district fallback only where polygon-derived mapping is unavailable.

## Cautions

- Do not overwrite LGD hierarchy with CoRE zones.
- Do not treat CoRE class membership as crop suitability by itself.
- Do not mark mappings as authoritative until source, geometry, and overlay method are reviewed.
- Do not geocode villages in bulk without provider terms/rate/cache review.
- Keep Android as a backend consumer only.
