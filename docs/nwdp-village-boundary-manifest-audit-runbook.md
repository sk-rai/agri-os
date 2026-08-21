# NWDP village boundary manifest audit runbook

Status date: 2026-08-21

## Purpose

This runbook covers the read-only manifest audit for the NWDP/GSI Village Boundary dataset.

The audit is intentionally limited:

- no KML, GeoJSON, or SHP downloads;
- no database writes;
- no geometry ingestion;
- no cadastral, ownership, or parcel-truth claims.

## Script

`backend/scripts/audit_nwdp_village_boundary_resources.py`

The script reads the National Water Data Portal village-boundary dataset page and extracts visible state/UT resource rows by format.

It checks:

- expected state/UT and format matrix;
- observed resources;
- missing state-format rows;
- duplicate state-format rows;
- unknown state labels;
- rows where a resource label is visible but URL could not be discovered;
- possible label inconsistencies.

## Run

From repo root:

- `cd backend`
- `../venv/bin/python scripts/audit_nwdp_village_boundary_resources.py > /tmp/nwdp-village-boundary-manifest-audit.json`
- `python3 -m json.tool /tmp/nwdp-village-boundary-manifest-audit.json | head -220`

Optional saved output:

- `../venv/bin/python scripts/audit_nwdp_village_boundary_resources.py --output /tmp/nwdp-village-boundary-manifest-audit.json`

Optional offline parse if the portal page is saved locally:

- `../venv/bin/python scripts/audit_nwdp_village_boundary_resources.py --html-file /tmp/nwdp-village-boundary.html`

## Expected interpretation

A green result for `complete_expected_state_format_matrix` only means the portal listing appears complete.

It does not mean:

- resources were downloaded;
- files are valid;
- geometries are valid;
- CRS is usable;
- attributes can be crosswalked to LGD;
- the data is cadastral;
- the data proves land ownership.

## Latest known manifest caveat

The first audit run found a useful but imperfect matrix:

- 108 visible resources;
- 107 unique expected state-format pairs;
- Uttarakhand SHP missing from the expected matrix;
- Telangana SHP duplicated;
- all observed rows had discoverable URLs;
- no downloads or database writes were attempted.

This means selected clean states can be considered for pilot download/audit, but all-India ingestion should remain blocked until the manifest caveat is resolved or explicitly reviewed.

## Next safe step after manifest audit

If the manifest is clean enough, the next step is a pilot download audit for one state, preferably Karnataka.

That pilot should validate:

- download status;
- checksum;
- file size;
- CRS;
- geometry type;
- feature count;
- invalid geometries;
- attribute names;
- state/district/subdistrict/village fields;
- LGD code availability, if present;
- license/source metadata;
- reviewed crosswalk readiness.

## Product boundary

Village boundaries are reference locality context.

AgriFabric should continue to separate:

- LGD/admin identity;
- PIN/postal context;
- village boundary locality context;
- GPS parcel point or polygon;
- backend-generated DigiPin;
- informational land intelligence.

Claim-safe phrase:

AgriFabric can use village boundary layers as governed reference geography for project planning, cohort validation, and future review workflows, while parcel precision remains based on GPS, plot geometry, and backend-generated DigiPin.
