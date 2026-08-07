# Crop climate and geography suitability roadmap

Status date: 2026-07-27

This document defines the next backend metadata slice after Android MVP profile migration: richer crop profiles, climatic/agro-ecological regions, and crop-season-geography suitability rules.

The goal is to make Android and admin experiences useful for testing and demos without hardcoding agronomic rules in Android. Android should render backend suitability labels, warnings, and advisory context; backend should own source attribution, confidence, and override policy.

## Why this matters

Current backend audits show Android emulator readiness is green, with 18 crops, all-India LGD/PIN geography, crop workflows, finance summaries, advisories, and product/input starter data. The next gap is richness: the system should be able to say not only "Rice exists" but also "Rice is usually suitable for this season/region/soil/rainfall profile, with these caveats."

This supports:

- crop onboarding warnings;
- crop/season/geography recommendations;
- stage and advisory targeting;
- crop analytics by climatic region;
- demo/client confidence when comparing regions and seasons;
- future agronomy review workflows.

## Recommended data-source stack

Use multiple evidence layers rather than a single "truth" table.

### 1. Climatic/agro-ecological region base layer

Preferred source candidates:

- ICAR-NBSS&LUP agro-ecological regions/sub-regions. Use as the agronomic reference layer because it combines soil, climate, physiography, and length of growing period.
- India-WRIS geospatial datasets where available for agro-ecological sub-regions.
- ESDAC/EUDASM India agro-ecological subregion map as a public mirror/reference for NBSS&LUP map documentation.
- Planning Commission/NITI-style 15 agro-climatic regions as a higher-level human-readable grouping, not as the detailed suitability boundary.

Backend use:

- store region code/name/source/version;
- map regions to states/districts/blocks where exact geometry import is not yet available;
- later import geometry/polygon boundaries when we are ready for spatial joins;
- keep source evidence and confidence per mapping.

### 2. Climate normals and rainfall evidence

Preferred source candidates:

- IMD district-wise rainfall normals and rainfall monitoring data;
- IMD climatological normals for station/district climate benchmarks;
- Mausam SANKALP / Agromet advisory products for district/block rainfall insights where accessible.

Backend use:

- classify geography into rainfall bands;
- store annual and seasonal rainfall normals;
- support warning rules such as dryland/irrigated suitability and high-rainfall disease-risk advisory targeting;
- avoid using live rainfall APIs inside Android.

### 3. Crop-season empirical evidence

Preferred source candidates:

- data.gov.in district-wise, crop-wise, season-wise area/production/yield statistics from the Directorate of Economics and Statistics, Ministry of Agriculture and Farmers Welfare;
- state agriculture department crop surveys where available;
- state agriculture university crop calendars and package-of-practices documents;
- ICAR/KVK crop advisories for crop-stage and season evidence.

Backend use:

- infer "commonly grown" crop-season-district combinations;
- rank suitability confidence by observed area/production history;
- separate empirical prevalence from agronomic suitability. A crop can be common because of market/irrigation/project behavior even if climatic suitability needs caveats.

### 4. Soil and land capability evidence

Preferred source candidates:

- ICAR-NBSS&LUP soil maps and land resource datasets;
- existing local Soil Health Card / SLUSI / manually captured soil snapshots;
- later: SoilGrids or other global sources only as secondary enrichment when approved.

Backend use:

- map crop suitability to soil texture/drainage/pH/salinity constraints;
- generate non-blocking warnings;
- improve input/fertilizer advisory context.

## Recommended backend model

Do not overload the existing `crops` table too much. It already has `suitable_seasons` and `suitable_soil_types`, but geographic and climate suitability needs versioned evidence.

Recommended first implementation can be config/JSON-seeded, then migrated to tables once stable.

### Region profile

`crop_climate_region_profile.v1`

Fields:

- `region_code`
- `region_name`
- `region_system`: `AGRO_CLIMATIC_ZONE`, `AGRO_ECOLOGICAL_REGION`, `AGRO_ECOLOGICAL_SUB_REGION`, `RAINFALL_BAND`, `STATE_AGRO_CLIMATIC_ZONE`
- `parent_region_code`
- `country_code`
- `state_codes`
- `district_lgd_codes`
- `block_lgd_codes`
- `rainfall_band_mm`
- `temperature_band_c`
- `length_of_growing_period_days`
- `dominant_soil_groups`
- `irrigation_context`
- `source_references`
- `confidence`
- `effective_from`
- `expires_at`
- `status`

### Crop suitability rule

`crop_climate_suitability_rule.v1`

Fields:

- `crop_code`
- `season_code`
- `region_code`
- `geography_scope`: country/state/district/block/village/PIN/region
- `suitability_status`: `HIGHLY_SUITABLE`, `SUITABLE`, `CONDITIONAL`, `NOT_TYPICAL`, `UNSUITABLE`, `UNKNOWN`
- `confidence`: `GOVERNMENT_SOURCE`, `EMPIRICAL_CROP_STATS`, `STATE_PACKAGE_OF_PRACTICES`, `EXPERT_REVIEW`, `LOCAL_DEMO_SEED`
- `rainfall_min_mm`
- `rainfall_max_mm`
- `temperature_min_c`
- `temperature_max_c`
- `soil_requirements`
- `irrigation_required`
- `typical_sowing_window`
- `typical_harvest_window`
- `warning_rules`
- `source_references`
- `review_status`
- `review_notes`

### Android-facing suitability response

Android should receive a compact interpreted result, not raw source tables:

```json
{
  "schema_version": "crop_geography_suitability.v1",
  "crop_code": "RICE",
  "season_code": "KHARIF",
  "geography": {
    "state_lgd_code": "29",
    "district_lgd_code": "572",
    "pin_code": "560001"
  },
  "region_matches": [
    {
      "region_code": "HIGH_RAINFALL_SOUTHERN_PLATEAU_DEMO",
      "region_system": "AGRO_ECOLOGICAL_SUB_REGION",
      "confidence": "LOCAL_DEMO_SEED"
    }
  ],
  "suitability": {
    "status": "SUITABLE",
    "confidence": "LOCAL_DEMO_SEED",
    "warnings": [],
    "requires_confirmation": false
  }
}
```

## Initial seed target

Build a first scenario pack with 45 crop-season entries:

- 15 Kharif-oriented entries;
- 15 Rabi-oriented entries;
- 15 Zaid/summer/perennial/demo entries.

Recommended crop spread:

- Cereals: rice, wheat, maize, pearl millet, sorghum.
- Pulses: chickpea, pigeon pea, green gram, black gram, lentil.
- Oilseeds: mustard, groundnut, soybean, sunflower, sesame.
- Cash/fibre: sugarcane, cotton, jute.
- Vegetables: potato, onion, tomato, cucumber, bottle gourd, okra, brinjal, chilli.
- Horticulture/perennial: mango, banana, guava, citrus, apple, grapes, pomegranate.
- Fodder/other demo crops: berseem, fodder maize, watermelon, muskmelon.

Each crop should have:

- category/taxonomy assignment;
- aliases/local names;
- suitable seasons;
- propagation options;
- typical duration;
- workflow coverage where applicable;
- suitability rules for at least a few representative climatic/geographic regions;
- review status and source references.

## Implementation order

### Slice 1: audit and contract

1. Add `backend/scripts/audit_crop_climate_suitability_readiness.py`.
2. Check:
   - crop count by season/category;
   - crop records missing aliases, duration, seasons, propagation;
   - region profile count;
   - crop-season-region rule count;
   - rules without source references;
   - Android-safe suitability endpoint/sample availability.
3. Document the output in Android/backend handoff docs.

### Slice 2: config-backed seed pack

1. Add a JSON seed file or Python config for demo climatic regions.
2. Add seed rules for the 45-entry starter pack.
3. Mark all non-verified rows as `LOCAL_DEMO_SEED` or `MANUAL_REVIEW`.
4. Do not claim government-verified suitability unless the source is attached.

### Slice 3: API surface

Add backend endpoint:

```text
GET /api/v1/crop-catalog/suitability?crop_code={crop}&season_code={season}&state_lgd_code={state}&district_lgd_code={district}&pin_code={pin}
```

Response should include:

- matched region(s);
- suitability status;
- warnings;
- whether Android must ask farmer/agent for confirmation;
- source/confidence summary.

### Slice 4: admin UI

Add admin page or extend crop taxonomy page to show:

- crop profile completeness;
- climatic/geographic suitability rules;
- source references;
- review status;
- manual override notes.

### Slice 5: richer source ingestion

Only after the model is stable:

- import NBSS&LUP/India-WRIS agro-ecological region boundaries or district mappings;
- import IMD rainfall/climate normal references;
- import district-wise crop-season area/production/yield statistics;
- add source batch/audit metadata.

## Failure preemption

- Agro-climatic zones, agro-ecological regions, and rainfall bands are not the same thing. Keep them as separate region systems.
- District/state crop production proves prevalence, not pure suitability.
- Suitability often changes with irrigation. Store `irrigation_required` and warning text instead of blocking.
- Crop names vary across sources. Use crop aliases and source-specific mappings before importing.
- State package-of-practices documents may disagree across states. Keep source-scoped rules.
- Climate normals are historical; live weather snapshots should be separate.
- Android should never be the place where suitability rules are hardcoded.

## Additional research needed

Useful manual/review work:

1. Pick the first 3-5 demo states/regions for high-quality suitability coverage.
2. Collect official state agriculture university/package-of-practices PDFs for those states.
3. Decide whether the first suitability demo should be India-wide broad coverage or high-confidence coverage for a few states.
4. Obtain/confirm credentials or terms for any API-based downloads, especially OGD/data.gov.in and IMD endpoints.
5. Confirm whether client demos will focus on field crops, horticulture, natural farming, or input-company workflows first.


## Implementation checkpoint - 2026-07-27

The starter metadata foundation is now implemented locally:

- Alembic revision `051_add_crop_climate_suitability_metadata.py` adds climate region, region mapping, and crop suitability rule tables.
- `backend/scripts/seed_crop_climate_suitability.py --apply` seeded:
  - 5 state-level starter climatic/agro-ecological region profiles;
  - Maharashtra, Karnataka, Uttar Pradesh, Punjab, and West Bengal state mappings;
  - 45 crop-season-region suitability rules;
  - 12 additional crop masters and 2 additional crop categories where missing.
- `backend/scripts/audit_crop_climate_suitability_readiness.py` verifies starter readiness.

Latest local audit result:

- 30 active crops;
- 5 climate regions;
- 5 climate region mappings;
- 45 crop suitability rules;
- 26 crops with suitability rules;
- selected state LGD mappings: Maharashtra `27`, Karnataka `29`, Uttar Pradesh `9`, Punjab `3`, West Bengal `19`.

Current confidence remains `LOCAL_DEMO_SEED` / `MANUAL_REVIEW`. These rows are good for Android/demo warnings and admin exploration, but should not be represented as government-verified until source documents or datasets are attached.

Next refinement targets:

1. Add 4 more Zaid/summer rules if we want exactly 15 Zaid entries alongside 15 Rabi and 15+ Kharif.
2. Refine state-level region mappings into district/block-level mappings using official AESR/agro-climatic-zone crosswalks or source geometry.
3. Add Android-safe suitability lookup endpoint and sample payload.
4. Upgrade source references from starter notes to reviewed ICAR/NBSS&LUP, IMD, data.gov.in, and state package-of-practices evidence.

## CoRE Stack source checkpoint - 2026-07-27

A local CoRE Stack GEE layer CSV has been inspected from:

    data/staged/core_stack/CoRE Stack GEE Layers Links - Datasets.csv

The extracted climate/ecology layer manifest is generated by:

    backend/scripts/build_core_stack_climate_layer_manifest.py

Generated manifest path:

    data/staged/core_stack/core_stack_climate_layer_manifest.json

Relevant CoRE Stack layers:

- Agro-Ecological Zone
  - GEE asset: `projects/ext-datasets/assets/datasets/Agro_Ecological_Zones`
  - class property: `physio_reg`
  - class count: 20
- Agro-Climatic Zone
  - GEE asset: `projects/ext-datasets/assets/datasets/Agro_Climatic_Zones`
  - class property: `regionname`
  - class count: 15
- Biogeographic Zone
  - GEE asset: `projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india`
  - class property: `biogeozone`
  - class count: 10

Integration decision:

- LGD remains canonical geography.
- CoRE Stack becomes a source/reference intelligence layer.
- Android must not call GEE or external map services.
- CoRE classes should map into `geography_climate_regions`.
- LGD links should go through `geography_climate_region_mappings`.
- Current selected-state village records have no latitude/longitude centroids, so village centroid to polygon mapping is not available yet.
- Immediate mapping should remain state/district fallback.
- Better mapping later requires CoRE polygon export plus LGD district/block/village boundaries or parcel GPS point-in-polygon at runtime.

Source caution:

- The Aikosh page shows CC BY 4.0 and describes the dataset as redirected/secondary.
- Keep imported CoRE-derived rows in review status until source and methodology are reviewed.
- Do not upgrade suitability confidence to `GOVT_SOURCE` merely because a class exists in the CoRE layer.

## District fallback mapping checkpoint - 2026-07-27

Because selected-state LGD villages currently have no stored latitude/longitude centroids, village-to-climate-zone polygon matching is not available yet.

A district-level fallback mapping script has been added:

    backend/scripts/seed_climate_region_district_fallback_mappings.py

Local apply result:

- 186 district fallback mappings;
- Karnataka: 31 districts;
- Maharashtra: 35 districts;
- Punjab: 23 districts;
- Uttar Pradesh: 75 districts;
- West Bengal: 22 districts.

These rows use:

- `scope_level = DISTRICT`;
- `confidence = LOCAL_DEMO_DISTRICT_FALLBACK`;
- `review_status = MANUAL_REVIEW`.

This is an approximation for Android/demo/admin suitability warnings, not polygon-derived climatic truth. Future refinement should replace or supplement these rows with CoRE polygon overlay, official district-zone crosswalks, or parcel GPS point-in-polygon matching.

## Village coordinate enrichment caution

It is technically possible to enrich LGD villages by sending village name, district, state, and PIN context to geocoding providers. However, this must be treated as a provider-gated backend enrichment workflow, not a scraper and not an Android responsibility.

Guidelines:

- Do not call Google/Bing/Azure/OSM geocoding directly from Android.
- Do not bulk geocode against public OSM Nominatim; the public service is not intended for systematic bulk geocoding.
- Review provider terms before storing coordinates. Some providers restrict long-term caching/storage of geocoded latitude/longitude values.
- Store provider-derived points as `GEOCODED_LABEL_POINT`, not as true `CENTROID`.
- Preserve source query, provider, provider place ID where available, confidence, review status, attribution, expiry/refresh requirement, and actor/job audit data.
- Prefer official LGD/Census/geospatial boundaries or CoRE polygon overlay for durable climate-zone mapping.


## CoRE Stack class import status - 2026-07-27

The CoRE Stack class importer is now available at:

    backend/scripts/import_core_stack_climate_regions.py

It imports class metadata from:

    data/staged/core_stack/core_stack_climate_layer_manifest.json

Local imported class-reference rows:

- 20 agro-ecological zone classes;
- 15 agro-climatic zone classes;
- 10 biogeographic zone classes.

These rows are metadata only. They do not replace LGD geography and do not yet define district/block/village mappings. All imported rows remain `MANUAL_REVIEW` with confidence `CORE_STACK_CLASS_REFERENCE`.

The next step is polygon/LGD overlay: export or obtain CoRE geometries, intersect them with official district/block/village boundaries or parcel GPS points, and write reviewed mappings into `geography_climate_region_mappings`.


## Polygon overlay readiness audit - 2026-07-27

Read-only audit script:

    backend/scripts/audit_climate_polygon_overlay_readiness.py

Latest local result:

- CoRE class metadata is ready:
  - 20 agro-ecological zone classes;
  - 15 agro-climatic zone classes;
  - 10 biogeographic zone classes.
- Demo district fallback is ready:
  - 186 district mappings across Maharashtra, Karnataka, Uttar Pradesh, Punjab, and West Bengal.
- LGD state/district reference data is ready:
  - 35 states with LGD codes;
  - 778 districts with LGD codes.
- CoRE polygon exports are not yet available locally.
- Village point overlay is not ready:
  - `geography_villages.latitude` and `geography_villages.longitude` columns exist;
  - all selected-state village coordinate counts are currently zero.

Current conclusion: district fallback remains the best available demo approximation. Authoritative mapping needs CoRE polygon export plus LGD boundary geometry or parcel GPS point overlay.


## CoRE GEE export checklist

Manual export and validation steps are tracked in:

    docs/core-stack-gee-export-checklist.md

This checklist explains the CoRE GEE layers, expected local export filenames, what geometry/properties they contain, and how exports will later support LGD/parcel overlay.


## LGD boundary source checklist

Boundary geometry source review is tracked in:

    docs/lgd-boundary-source-checklist.md

Preferred approach: use Survey of India/India Maps boundary geometry, LGD Directory for canonical codes, and OGD Admin Boundaries only after schema/source review.


## CoRE polygon/LGD overlay execution plan

Backend execution planning is tracked in:

    docs/core-polygon-lgd-overlay-plan.md

Read-only scripts:

    backend/scripts/plan_core_polygon_lgd_overlay.py
    backend/scripts/verify_core_polygon_lgd_overlay_plan.py

Current scope is backend-only planning/readiness. No Android Maestro flow is required until reviewed polygon-derived mappings change backend `land-intelligence-context` output for a test location.


## CoRE/LGD overlay input validation

Dry-run local input validation is tracked in:

    backend/scripts/validate_core_lgd_overlay_inputs.py
    docs/core-lgd-overlay-input-validation.md

Latest local result: expected CoRE GeoJSON exports and LGD boundary candidates are not staged yet, so `ready_for_dry_run_overlay` is false. This is backend-only; no Android Maestro flow is required until backend land-intelligence responses change.


## CoRE/LGD source download probe

Safe source/download probing is tracked in:

    backend/scripts/probe_core_lgd_download_sources.py
    docs/core-lgd-download-source-probe.md

Latest local result: source pages are reachable, but `earthengine` and `aikosh` CLIs are not installed in WSL, so automatic CoRE export/download is not currently available from this environment. Manual GEE export remains the safest immediate route unless authenticated tooling or direct file URLs are configured.


## CoRE GeoJSON normalization

CoRE GEE exports were staged locally and normalized with:

    backend/scripts/normalize_core_geojson_exports.py
    docs/core-geojson-normalization.md

Latest local result: all three CoRE layers are polygon-only after normalization, and `all_core_exports_ready = true`. Dry-run overlay readiness remains false because LGD-compatible boundary geometry is not staged yet.


## CoRE/LGD overlay candidate generation

Dry-run district overlay candidate generation is tracked in:

    backend/scripts/generate_core_lgd_overlay_candidates.py
    backend/scripts/verify_core_lgd_overlay_candidates.py
    docs/core-lgd-overlay-candidate-generation.md

Latest local result: 2,355 candidate rows generated for 785 Bharatlas LGD districts across three CoRE region systems, with zero no-overlap rows. These are manual-review artifacts only; no `geography_climate_region_mappings` rows were written. DB import remains blocked on source/provenance and overlay-method review.


## CoRE/LGD overlay candidate review

Dry-run candidate review is tracked in:

    backend/scripts/review_core_lgd_overlay_candidates.py
    docs/core-lgd-overlay-candidate-review.md

Latest local result: 2,355 district overlay candidates are ready for manual review, but not DB import. There are 68 rows below 60% dominant overlap. Import remains blocked on Bharatlas source/provenance review, low-overlap review, and decision on whether to use equal-area reprojection for ranking.


## BharatAtlas boundary source review

BharatAtlas district boundary source review is tracked in:

    backend/scripts/review_bharatlas_boundary_source.py
    docs/bharatlas-boundary-source-review.md

Latest local result: BharatAtlas LGD Districts is acceptable for dry-run/manual-review overlay candidates, but not authoritative government source. The file has 785 features, 36 state codes, 783 distinct district codes, and required LGD fields. DB import remains blocked on duplicate district-code review, low-overlap candidate review, and importer/precedence design.

## CoRE/LGD equal-area overlay comparison

Equal-area comparison is tracked in:

    backend/scripts/compare_core_lgd_overlay_equal_area.py
    docs/core-lgd-overlay-equal-area-review.md

Latest local result: equal-area reprojection changed 0 of 2,355 dominant district/region candidates. The low-overlap count remains 68 rows below 60%, so those rows should be treated as genuine manual-review cases rather than projection artifacts. DB import remains blocked on duplicate district-code review, low-overlap manual review, and MANUAL_REVIEW importer/precedence design.


## BharatAtlas/backend LGD district crosswalk

Backend/BharatAtlas district crosswalk review is tracked in:

    backend/scripts/audit_bharatlas_backend_lgd_district_crosswalk.py
    docs/bharatlas-backend-lgd-district-crosswalk-review.md

Latest local result: 716 exact LGD district matches, 50 matched name variants, 1 state-code mismatch for district LGD `766`, 16 BharatAtlas-only rows, 11 backend-only rows, and no duplicate LGD district codes. BharatAtlas remains suitable for dry-run/manual-review overlay work, but not automatic DB import. Existing fallback mappings should remain active until polygon-derived mappings are reviewed and intentionally promoted.


## CoRE/LGD low-overlap review

Low-overlap overlay review is tracked in:

    backend/scripts/review_core_lgd_low_overlap_rows.py
    docs/core-lgd-low-overlap-review.md

Latest local result: 68 low-overlap rows below 60% were bucketed into 38 ecological/climatic transition-zone rows, 19 manual-review rows, 9 coastal/island geometry rows, and 2 source-version drift rows. These rows are ready for manual review but not automatic DB import. Existing fallback mappings should remain active until reviewed polygon-derived mappings are intentionally promoted.


## CoRE/LGD manual-review import plan

Manual-review import planning is tracked in:

    backend/scripts/plan_core_lgd_manual_review_import.py
    docs/core-lgd-manual-review-import-plan.md

Latest local result: 2,298 of 2,355 polygon-derived district/region candidates would be staged as inactive `MANUAL_REVIEW` rows. 57 rows would be excluded for LGD/source-version issues. The plan preserves existing fallback mappings and keeps polygon-derived rows ineffective in `land-intelligence-context` until reviewed and intentionally promoted.


## Survey of India ABDB boundary source validation

Survey of India boundary source validation is tracked in:

    backend/scripts/validate_survey_of_india_boundary_source.py
    docs/survey-of-india-boundary-source-review.md

Latest local result: SOI ABDB metadata and state/district/subdistrict shapefiles are staged locally. The district layer has 808 records and includes `STATE_LGD` / `DIST_LGD` fields. Metadata identifies the district dataset as `SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA`, published 2026-05-06 at 1:50,000 scale. SOI is acceptable as preferred official geometry source for review, but not automatic import because the district layer includes 31 invalid/blank/not-available district LGD rows and 28 invalid/blank/not-available state LGD rows.


## Survey of India district name/code alignment

SOI ABDB district attribute alignment is tracked in:

    backend/scripts/audit_soi_district_name_code_alignment.py
    docs/soi-district-name-code-alignment-review.md

Latest local result: SOI remains a preferred official geometry reference source, but the current extracted district shapefile's `DIST_LGD` attribute is not safe as a direct backend LGD key. Only 2 rows matched backend by both name and code, while 565 rows had a code that points to a different backend district. For the current CoRE overlay pipeline, BharatAtlas remains the preferred operational LGD-keyed geometry source until a reliable SOI crosswalk is created.
