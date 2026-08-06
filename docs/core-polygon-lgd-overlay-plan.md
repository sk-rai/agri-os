# CoRE Polygon/LGD Overlay Execution Plan

Status date: 2026-08-06

This plan turns the existing CoRE Stack export checklist and LGD boundary checklist into a backend execution path. It is intentionally plan-only: no polygon exports, boundary files, overlay candidates, or database mappings are created by this document.

## Goal

Produce reviewed climate/ecology mappings between CoRE Stack zone polygons and canonical LGD geography so backend intelligence can move beyond the current approximate district fallback.

Target database table:

    geography_climate_region_mappings

Initial polygon-derived rows should remain:

- `review_status = MANUAL_REVIEW`;
- confidence similar to `POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW`;
- source metadata attached before any production trust upgrade.

## Current state

Already done:

- CoRE Stack AEZ/ACZ/biogeographic class manifest generated.
- 45 CoRE class-reference rows imported into climate region metadata.
- Selected-state district fallback mappings are available as approximate demo guidance.
- Readiness audit exists:

      backend/scripts/audit_climate_polygon_overlay_readiness.py

Still missing:

- local CoRE polygon exports;
- reviewed LGD-compatible boundary geometry;
- geometry validation;
- LGD code crosswalk review;
- overlay candidate generation/import.

## Inputs

### CoRE Stack polygon exports

Expected local path:

    data/staged/core_stack/exports/

Required GeoJSON exports:

| CoRE layer | GEE asset | Class property | Backend region system |
| --- | --- | --- | --- |
| Agro-Ecological Zone | `projects/ext-datasets/assets/datasets/Agro_Ecological_Zones` | `physio_reg` | `CORE_STACK_AGRO_ECOLOGICAL_ZONE` |
| Agro-Climatic Zone | `projects/ext-datasets/assets/datasets/Agro_Climatic_Zones` | `regionname` | `CORE_STACK_AGRO_CLIMATIC_ZONE` |
| Biogeographic Zone | `projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india` | `biogeozone` | `CORE_STACK_BIOGEOGRAPHIC_ZONE` |

See:

    docs/core-stack-gee-export-checklist.md

### LGD-compatible boundary geometry

Preferred source order:

1. Survey of India / India Maps boundary geometry;
2. LGD Directory for canonical codes/crosswalk validation;
3. Open Government Data admin boundaries after source/schema review.

Expected local staging root:

    data/staged/boundaries/

See:

    docs/lgd-boundary-source-checklist.md

## Execution phases

### Phase 0: source and license review

Record for every geometry source:

- source URL;
- license/usage terms;
- file date/version;
- CRS/projection;
- geometry level;
- whether attributes include LGD codes;
- whether a reviewed name/code crosswalk is required.

Output:

    data/staged/boundaries/review_notes/

Do not commit large/raw boundary files unless explicitly approved.

### Phase 1: local file validation

Check:

- all three CoRE exports exist;
- files are readable;
- expected class property exists;
- feature count is non-zero;
- geometries are polygon or multipolygon.

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/audit_climate_polygon_overlay_readiness.py

### Phase 2: geometry validation

Validate:

- CRS;
- invalid or empty geometries;
- self-intersections;
- duplicate class names/codes;
- tiny sliver geometries;
- whether an equal-area projection is needed for area overlap.

Output should be a geometry QA report before any mapping import.

### Phase 3: LGD crosswalk

Map boundary attributes to canonical backend LGD records:

- state LGD code;
- district LGD code;
- later block/village LGD code if boundary quality supports it.

Unmatched or ambiguous names must remain separate for manual review.

### Phase 4: overlay candidate generation

First backend implementation should be dry-run only:

- district polygon × CoRE polygon area intersection;
- dominant CoRE region by overlap area;
- overlap percentage;
- secondary overlaps for edge cases;
- source metadata.

Recommended initial output:

    data/staged/core_stack/overlay_candidates/

### Phase 5: reviewed mapping import

Only after review, write approved mappings into:

    geography_climate_region_mappings

Do not delete fallback rows in the first import. Instead, keep fallback rows available until polygon-derived rows are reviewed and the backend selection logic is intentionally updated.

## Android impact

Android must not call Google Earth Engine, Survey of India, India Maps, OGD, or any external map/geocoding provider for this workflow.

Android continues to call backend-safe endpoints such as:

    GET /api/v1/profile/land-intelligence-context

No Android Maestro flow is required for this planning step.

Maestro becomes useful later only when backend output changes, for example after polygon-derived mappings are imported and a known test PIN/district/parcel starts returning a different `climate_context` or crop suitability guidance. At that point Android can reuse an existing land-intelligence/profile guidance flow rather than creating a GEE-specific Android flow.

## Plan/verifier scripts

Read-only plan:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/plan_core_polygon_lgd_overlay.py

Read-only verifier:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/verify_core_polygon_lgd_overlay_plan.py

Expected verifier result now:

- required planning artifacts present;
- plan script runs;
- plan is read-only;
- Android Maestro is correctly marked not required for the planning step.

## Next backend implementation after this plan

The next code-bearing backend step should be a dry-run geometry validator, not a DB importer.

Suggested future script:

    backend/scripts/validate_core_lgd_overlay_inputs.py

It should inspect local GeoJSON/boundary files and report CRS, feature counts, required property coverage, and LGD-code/crosswalk readiness without writing database rows.
