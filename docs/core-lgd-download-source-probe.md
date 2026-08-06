# CoRE/LGD Download Source Probe

Status date: 2026-08-06

This document records the safe probe for whether CoRE polygon and LGD boundary inputs can be acquired automatically from the current WSL environment.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/probe_core_lgd_download_sources.py

The probe is read-only:

- no downloads;
- no Google Earth Engine export tasks;
- no portal scraping;
- no database writes.

## Source trail

### CoRE Stack climate/ecology layers

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

GEE assets:

    projects/ext-datasets/assets/datasets/Agro_Ecological_Zones
    projects/ext-datasets/assets/datasets/Agro_Climatic_Zones
    projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india

### Boundary geometry candidates

Survey of India ABDB:

    https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-

India Maps product portal:

    https://indiamaps.gov.in/product

LGD directory:

    https://lgdirectory.gov.in/demo/downloadDirectory.do

OGD Admin Boundaries:

    https://www.data.gov.in/catalog/admin-boundaries

## Latest local probe result

Current WSL environment:

- `earthengine` CLI present: no;
- `aikosh` CLI present: no;
- source pages reachable: mostly yes;
- India Maps product portal probe hit local SSL certificate verification failure;
- automatic CoRE export/download from WSL: not currently available;
- automatic boundary download: not currently approved/recommended.

Interpretation:

- CoRE files likely need manual Google Earth Engine export unless Earth Engine CLI/auth or a direct Aikosh/CoRE file download path is configured.
- Survey of India/India Maps boundary files should be handled manually/portal-mediated until access, license, and download flow are reviewed.
- OGD Admin Boundaries may be investigated separately if a direct API/ZIP URL and schema are confirmed.

## Next action

Manual CoRE export remains the safest immediate route:

1. open Google Earth Engine Code Editor;
2. load the three FeatureCollections;
3. export each as GeoJSON;
4. place them under:

       data/staged/core_stack/exports/

Then rerun:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/validate_core_lgd_overlay_inputs.py

## Android impact

No Android work is required for this source probe.

Android does not call Google Earth Engine, Aikosh, Survey of India, India Maps, LGD download pages, or OGD boundary catalogs.
