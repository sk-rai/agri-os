# NWDP Karnataka village boundary pilot audit runbook

Status date: 2026-08-21

## Purpose

This runbook covers the first Karnataka-only read-only pilot audit for the NWDP/GSI village-boundary GeoJSON.

The pilot answers whether the file has usable LGD identifiers or whether crosswalks will require scoped name matching and manual review.

## Script

`backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py`

The script can:

- discover the Karnataka GeoJSON URL from the NWDP manifest page;
- download only that one GeoJSON to `/tmp` or a supplied cache path;
- compute file size and SHA-256;
- inspect GeoJSON top-level type;
- count features;
- list property fields;
- count geometry types;
- compute a rough bounding box;
- detect candidate code/name fields;
- classify likely crosswalk case;
- optionally attempt a read-only sample crosswalk to `geography_villages`.

It does not:

- write to the database;
- ingest geometries;
- download all-India files;
- validate cadastral truth;
- establish ownership.

## Basic run

From repo root:

- `cd backend`
- `../venv/bin/python scripts/audit_nwdp_karnataka_village_boundary_pilot.py --output /tmp/nwdp-karnataka-boundary-pilot.json > /tmp/nwdp-karnataka-boundary-pilot.raw 2>&1`
- `echo "nwdp_karnataka_pilot_exit=$?"`
- `tail -220 /tmp/nwdp-karnataka-boundary-pilot.raw`

## Optional local-file run

If the GeoJSON has already been downloaded:

- `../venv/bin/python scripts/audit_nwdp_karnataka_village_boundary_pilot.py --geojson /tmp/nwdp-karnataka-village-boundary.geojson --output /tmp/nwdp-karnataka-boundary-pilot.json`

## Optional DB read crosswalk

Only run this if the backend DB is available and loaded with geography tables:

- `../venv/bin/python scripts/audit_nwdp_karnataka_village_boundary_pilot.py --geojson /tmp/nwdp-karnataka-village-boundary.geojson --with-db-crosswalk --output /tmp/nwdp-karnataka-boundary-pilot-db.json`

This is still read-only. It samples candidate LGD/code fields and checks whether those values match `geography_villages.lgd_code`.

## Latest pilot finding

The Karnataka pilot successfully extracted GeoJSON from the NWDP ZIP resource and inspected 29,789 MultiPolygon features.

Important fields found:

- `vlcode`;
- `village`;
- `dtcode`;
- `district`;
- `sdcode`;
- `subdistric`;
- `bkcode`;
- `block`;
- `stcode`;
- `state`.

Read-only sample DB crosswalk found that `vlcode` partially matches `geography_villages.lgd_code`: 2 of 5 sampled values matched.

This is promising, but not ingestion-ready. The next step is full-state `vlcode` coverage analysis.

Also, coordinates appear projected/non-WGS84, so CRS identification is mandatory before any spatial runtime use.

## Crosswalk interpretation

### Case A or B: code candidates present

If exact LGD or village-code candidate fields are present, inspect whether values match loaded LGD village codes.

If they match, the source may be usable for high-confidence crosswalk after parent consistency checks.

### Case C: scoped name matching required

If village and district names are present but LGD codes are absent, match only inside district/subdistrict scope and treat duplicates as manual-review cases.

### Case D: weak attributes

If attribute fields do not carry usable code or name hierarchy, keep the layer as standalone reference geometry until a reviewed crosswalk is built.

## Latest full coverage finding

The full Karnataka `vlcode` coverage audit matched 24,361 of 29,732 distinct NWDP `vlcode` values to backend `geography_villages.lgd_code`.

This is an 81.9353% distinct-code match rate.

Decision:

- promising source for reviewed boundary-to-LGD linkage;
- not complete enough for automatic ingestion;
- next audit should classify the 5,371 unmatched codes;
- CRS must be identified before any spatial use.

## Geometry caution

This script performs only lightweight GeoJSON inspection. Before ingestion, run a proper geospatial validation step with geometry libraries to check:

- CRS;
- invalid geometries;
- self-intersections;
- empty geometries;
- polygon versus multipolygon handling;
- overlap/outlier behavior.

## Product boundary

Even a successful pilot means only that Karnataka village boundaries may be useful as reference locality context.

It does not mean:

- parcel ownership is proven;
- cadastral boundaries are available;
- insurance claims can be approved or rejected automatically;
- Android should perform canonical spatial matching locally.

Backend should own boundary ingestion, validation, crosswalks, confidence scoring, and audit history.
