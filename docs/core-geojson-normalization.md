# CoRE GeoJSON Normalization

Status date: 2026-08-06

Google Earth Engine exported the CoRE zone files successfully, but a few features arrived as `GeometryCollection` instead of plain `Polygon` or `MultiPolygon`. The overlay path should use polygon-only geometries, so backend now has a local normalization step.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/normalize_core_geojson_exports.py

The script reads raw exports from:

    data/staged/core_stack/exports/

and writes derived normalized files to:

    data/staged/core_stack/exports_normalized/

It does not overwrite the original Google Earth Engine exports.

## Output files

Expected normalized files:

- `Agro_Ecological_Zones.normalized.geojson`
- `Agro_Climatic_Zones.normalized.geojson`
- `Biogeographic_Zone_pan_india.normalized.geojson`

Do not commit raw or normalized GeoJSON files unless explicitly approved.

## Latest local result

Normalization result:

- all three source exports present;
- all normalized outputs polygon-only;
- no DB writes;
- no external calls.

Geometry conversion summary:

| Layer | Before | After |
| --- | --- | --- |
| Agro-Ecological Zone | 2 GeometryCollection, 4 MultiPolygon, 14 Polygon | 6 MultiPolygon, 14 Polygon |
| Agro-Climatic Zone | 1 GeometryCollection, 5 MultiPolygon, 9 Polygon | 6 MultiPolygon, 9 Polygon |
| Biogeographic Zone | 2 GeometryCollection, 7 MultiPolygon, 17 Polygon | 9 MultiPolygon, 17 Polygon |

The GeometryCollection features contained polygon parts plus non-polygon artifacts such as `LineString` or `Point`. The script extracts polygon parts into `MultiPolygon` and reports that non-polygon children were dropped for overlay suitability.

## Validator impact

After normalization, the input validator prefers normalized files when present:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/validate_core_lgd_overlay_inputs.py

Latest local result:

- `all_core_exports_ready = true`;
- `normalized_core_export_dir_exists = true`;
- `ready_for_dry_run_overlay = false`.

The remaining blocker is boundary geometry under:

    data/staged/boundaries/

## Android impact

No Android Maestro flow is required for this normalization step.

Android remains a consumer of backend land-intelligence responses only.
