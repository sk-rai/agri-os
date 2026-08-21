# NWDP / GSI village boundary source readiness note

Status date: 2026-08-21

## Source summary

The National Water Data Portal lists a `Village Boundary` dataset produced by the Geological Survey of India.

Portal page:

- https://nwdp.nwic.gov.in/dataset/village-boundary

Visible dataset description:

- The village boundary layer demarcates geographic boundaries of villages across India.
- Resources are listed state-wise.
- Formats shown include KML, GeoJSON, and SHP.
- Dataset-level producer agency is Geological Survey of India.
- Dataset-level last update shown in the portal content is May 2, 2025, 5:38 PM UTC+05:30.

Example checked resource:

- Karnataka GeoJSON resource metadata:
  - https://nwdp.nwic.gov.in/dataset/village-boundary/resource/1fd9b5a0-2a73-4404-9e45-7c1f3968e545
  - format: GeoJSON
  - license label: Other (Open)
  - last updated: May 2, 2025

## Fit with AgriFabric geography model

This source is a strong candidate for a future village-boundary reference layer.

It should fit beside existing geography layers, not replace them:

- LGD/admin geography: canonical administrative identity and hierarchy.
- PIN/postal data: broad postal context and lookup guardrails.
- Village boundary polygons: spatial locality/reference context.
- GPS parcel point or polygon: field-captured precision evidence.
- DigiPin: backend-generated digital address from coordinates.
- Land intelligence: informational, non-blocking project guidance.

The clean product message is:

PIN is context. Village boundary is locality context. GPS, parcel polygon, and DigiPin are precision evidence.

## Candidate use cases

Village boundary polygons can support:

- GPS-to-village candidate lookup;
- validation when selected village and captured GPS disagree;
- FPO/project service-area setup by actual village polygons;
- farmer cohort targeting by village boundary;
- project traceability and coverage maps;
- advisory targeting by locality plus crop/project/stage;
- field-agent route planning and coverage analysis;
- insurance/subsidy review support where declared village, parcel GPS, crop evidence, and claim metadata disagree;
- joining future climate, water, soil, and satellite layers to village-scale context.

## Claim boundaries

Village boundary is not cadastral or ownership truth.

Do not claim:

- exact parcel ownership;
- claim approval or rejection;
- automated fraud detection;
- cadastral-grade plot boundaries;
- legal land title validation.

Claim-safe phrasing:

AgriFabric can use village boundary layers as governed reference geography for planning, validation, and review workflows, while parcel precision remains based on captured GPS, plot geometry, and backend-generated DigiPin.

## Ingestion should be gated

Do not bulk-ingest this directly into production tables without a manifest/audit step.

Recommended first step:

1. Build a source manifest for all state resources.
2. Record resource title, state/UT, format, URL, license label, last updated date, file size, checksum, and download status.
3. Validate that KML, GeoJSON, and SHP resources are consistently named and available.
4. Download one pilot state first, preferably Karnataka for current demo alignment.
5. Inspect attributes for state, district, subdistrict/block/taluk, village name, codes, and source IDs.
6. Validate geometry type, CRS, invalid geometries, duplicates, and empty features.
7. Load into a separate reference table, not parcel or farmer tables.
8. Link to existing geography tables through reviewed crosswalks and confidence scores.

## Observed portal caution

The visible portal listing appears to have minor labeling inconsistency around the Uttarakhand entries, where an SHP row appears labelled as Telangana in the pasted/visible content.

This may be a portal display issue, but it reinforces the need for a manifest audit before relying on the resource list programmatically.

## Suggested backend model boundary

Future table family, if implemented:

- `geography_boundary_sources`
- `geography_village_boundary_import_batches`
- `geography_village_boundaries`
- `geography_village_boundary_crosswalks`

The boundary layer should carry:

- source agency;
- source URL;
- license label;
- source updated date;
- import batch;
- geometry;
- geometry validity status;
- matched LGD village ID, if reviewed;
- match confidence and review status.

## Android boundary

Android should not ship village boundary datasets or perform canonical boundary matching locally.

Android may:

- capture GPS/parcel geometry;
- show backend-returned candidate village/locality;
- show boundary validation hints if backend provides them;
- display backend-generated DigiPin.

Backend should own:

- source ingestion;
- spatial lookup;
- validation;
- crosswalks;
- confidence scoring;
- audit history.

## Demo / landing positioning

This source strengthens the geography/DigiPin story, but should remain a future enrichment/reference layer until ingestion and validation are implemented.

Suggested copy:

AgriFabric separates administrative identity, postal context, village boundary context, and parcel-level precision evidence. Village boundary layers can support project planning, cohort validation, and future risk review, while GPS, plot geometry, and backend-generated DigiPin remain the precision evidence for field records.
