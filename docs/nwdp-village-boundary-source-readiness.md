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

## Manifest audit finding

Read-only manifest audit script:

- `backend/scripts/audit_nwdp_village_boundary_resources.py`

Latest observed result:

- expected state/UT count: 36;
- expected formats: KML, GeoJSON, SHP;
- expected resource matrix: 108 state-format pairs;
- observed resources: 108;
- observed unique expected pairs: 107;
- GeoJSON rows: 36;
- KML rows: 36;
- SHP rows: 36;
- missing expected pair: Uttarakhand SHP;
- duplicate observed pair: Telangana SHP appears twice;
- resource URLs were discovered for all observed rows;
- no downloads or database writes were attempted.

Interpretation:

The portal appears broadly useful, but the visible resource matrix is not clean enough for automatic all-India ingestion. The Uttarakhand/Telangana SHP inconsistency should be treated as a source caveat until resolved or intentionally handled.

Pilot recommendation:

Karnataka is a clean candidate for a first pilot download and geometry audit because the manifest shows one KML, one GeoJSON, and one SHP resource for Karnataka.

All-India ingestion boundary:

Do not proceed to all-India boundary ingestion until the manifest issue is resolved, excluded by policy, or handled through a reviewed override in the acquisition manifest.

## Karnataka pilot audit finding

Read-only pilot script:

- `backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py`

Latest Karnataka GeoJSON pilot result:

- NWDP resource page resolved to a ZIP download: `vb_soi_ka_geojson.zip`;
- script extracted the GeoJSON from the ZIP;
- feature count: 29,789;
- geometry type: 29,789 MultiPolygon features;
- source agency inside feature attributes: Survey of India (SOI);
- state fields include `stcode=29`, `state=KA`, and `state_name=Karnataka`;
- district fields include `dtcode` and `district`;
- subdistrict/taluk/block candidates include `sdcode`, `subdistric`, `bkcode`, and `block`;
- village fields include `vlcode` and `village`;
- exact LGD/code candidate field detected: `vlcode`;
- optional read-only DB crosswalk executed successfully after script hardening;
- sampled `vlcode` to `geography_villages.lgd_code` match result: 2 matched out of 5 sampled values.

Interpretation:

The Karnataka file is more promising than pure fuzzy SOI alignment because it has structured code fields, especially `vlcode`. However, the sample DB crosswalk is only partial. It is not yet safe to assume automatic LGD linkage across the full state.

Spatial caution:

The raw coordinate bbox is `[180.0, 90.0, 3847351.8078999966, 3402551.8718999997]`, which indicates projected/non-WGS84 coordinates. CRS must be identified and geometry transformed before GPS point-in-polygon or parcel-overlap use.

Current decision:

- good candidate for deeper full-code coverage audit;
- not ready for ingestion;
- not ready for runtime spatial matching;
- not ready for all-India rollout.

Next required audit:

Run a full Karnataka `vlcode` coverage audit against `geography_villages.lgd_code` to calculate:

- total features;
- distinct `vlcode` count;
- blank/null `vlcode` count;
- matched `vlcode` count;
- unmatched `vlcode` count;
- duplicate `vlcode` count;
- sample unmatched values with village/district/subdistrict names;
- whether unmatched values correspond to missing LGD data, Census-only settlements, forest beats, hamlets, deleted/merged villages, or code-system mismatch.

## Karnataka full `vlcode` coverage audit finding

Read-only full coverage audit:

- script: `backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py`
- mode: `--full-vlcode-coverage`
- database writes: none
- geometry ingestion: none

Latest observed result:

- total features: 29,789;
- geometry type: 29,789 MultiPolygon features;
- non-blank `vlcode` features: 29,789;
- distinct `vlcode` count: 29,732;
- duplicate `vlcode` count: 2;
- backend `geography_villages.lgd_code` count: 576,082;
- matched distinct `vlcode` count: 24,361;
- unmatched distinct `vlcode` count: 5,371;
- distinct-code match rate: 81.9353%;
- lightweight local SOI reference overlap: 0 matched tokens from available staged reference files.

Interpretation:

The NWDP Karnataka boundary file is materially useful because most distinct `vlcode` values match backend LGD village codes directly. This makes it a stronger boundary-to-LGD candidate than the previously available local SOI reference files.

However, the match is not complete enough for automatic ingestion. The 5,371 unmatched distinct `vlcode` values must be classified before any reviewed ingestion design.

Known blockers:

- CRS remains unidentified and coordinates are projected/non-WGS84;
- unmatched codes require classification;
- duplicate `vlcode` values require inspection;
- local SOI reference overlap did not help in the lightweight comparison;
- all-India ingestion remains blocked by the NWDP manifest caveat and state-level reconciliation requirements.

Next required audit:

Classify unmatched Karnataka `vlcode` records by:

- district;
- subdistrict;
- block code;
- `bkcode=0` versus populated block codes;
- population zero versus non-zero;
- rural/urban marker;
- village names that equal subdistrict/taluk/town names;
- forest beat / special settlement naming patterns;
- whether unmatched names can be scoped-name matched to backend LGD records;
- duplicate `vlcode` examples.

Current decision:

Karnataka should proceed to unmatched-classification audit, not ingestion.


## Karnataka unmatched name-match audit finding

Read-only unmatched name-match audit:

- script: `backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py`
- mode: `--unmatched-name-match`
- database writes: none
- geometry ingestion: none

Latest observed result:

- unmatched input records checked: 5,425;
- scoped district + subdistrict/block + village name matches: 252;
- district + village-only matches: 580;
- records with no normalized name match: 4,593;
- name-match recovery rate among unmatched records: 15.3364%.

Interpretation:

The unmatched set is not mainly a spelling-variation problem.

Some records can be explained by alias/name/admin drift, for example:

- `Shimoga` versus `Shivamogga`;
- `Linga Pura` versus `Lingapura`;
- same village name found under a different backend block;
- duplicate common names within a district.

However, most unmatched records did not match by normalized backend names either. This points to deeper reconciliation issues such as source vintage mismatch, code-system drift, district/subdistrict/block reorganization, Census/SOI-style settlement records not present in current LGD, and special non-village features such as rivers/reservoirs.

Current decision:

NWDP Karnataka village boundaries are promising but reconciliation-gated.

Do not ingest automatically. Use a reviewed crosswalk workflow that separates:

- direct `vlcode` matches;
- scoped name matches;
- ambiguous district-only matches;
- special non-village features;
- unresolved records requiring manual/source review.

## Karnataka parent-code drift audit finding

Read-only parent-code drift audit:

- `backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py --parent-code-drift`

Latest observed result:

- distinct NWDP `dtcode` values: 30;
- backend district-code matches for NWDP `dtcode`: 30;
- unmatched NWDP `dtcode` values: 0;
- distinct NWDP `sdcode` values: 228;
- backend block-code matches for NWDP `sdcode`: 227;
- unmatched NWDP `sdcode` values: 1;
- distinct NWDP `bkcode` values: 177;
- backend block-code matches for NWDP `bkcode`: 173;
- unmatched NWDP `bkcode` values: 4;
- unmatched village features checked: 5,425;
- unmatched village features with matching district code: 5,425;
- unmatched village features with matching `sdcode`: 5,425;
- unmatched village features with matching `bkcode`: 5,166;
- unmatched village features with district and `sdcode` match but `bkcode` missing: 259;
- unmatched village features with no parent-code match: 0.

Interpretation:

The remaining Karnataka mismatch is not primarily a parent-geography problem. District and subdistrict/block parent codes align strongly with the backend geography model. The difficult part is concentrated at the village `vlcode` and settlement-feature layer.

This is better than a fully ambiguous shape source: parent codes can still provide a high-confidence review scope. However, the 5,371 unmatched distinct `vlcode` values cannot be auto-linked just because their district and subdistrict parents match.

Current decision:

- use direct `vlcode` matches as the first high-confidence candidate bucket;
- use parent-code matches to scope review and reduce false positives;
- keep unmatched `vlcode` records in a reconciliation queue;
- treat `vlcode=999999` and river/reservoir-style features as special non-village/reference geometry candidates;
- do not run automatic ingestion or runtime point-in-polygon until CRS and crosswalk policy are resolved.

Next technical audits:

- identify the NWDP/SOI coordinate reference system from the SHP ZIP `.prj` or source metadata;
- classify unmatched `vlcode` values by code range and source vintage;
- compare unmatched rows against backend `census_village_code` where available;
- design a reviewed boundary crosswalk table before any persisted ingestion.


## Karnataka SHP CRS audit finding

Read-only CRS audit script:

- `backend/scripts/audit_nwdp_karnataka_shp_crs.py`

Latest observed result:

- Karnataka SHP resource resolved to `vb_soi_ka_shp.zip`;
- ZIP size: 14,941,558 bytes;
- ZIP SHA-256: `fa7f7dabd7c55e59a5e8c4e916f556294969c8a993057a574bc67a9d11f9c3e7`;
- archive members: `vb_soi_ka.dbf`, `vb_soi_ka.prj`, `vb_soi_ka.shp`, `vb_soi_ka.shx`;
- `.prj` file present: `vb_soi_ka.prj`;
- `.prj` SHA-256: `d27ca1c7705221fea351dd7713fd0d98b169f2eb0201d4a2a81e69c6d1e08629`;
- projected CRS name: `WGS_1984_India_NSF_LCC`;
- projection: `Lambert_Conformal_Conic`;
- geographic base: `GCS_WGS_1984`;
- datum: `D_WGS_1984`;
- unit: meter.

Interpretation:

The raw coordinates in the NWDP Karnataka GeoJSON/SHP are projected coordinates, not longitude/latitude. This explains the earlier raw bbox `[180.0, 90.0, 3847351.8078999966, 3402551.8718999997]`.

Current decision:

- CRS metadata is good enough for transform planning;
- source is still not ready for runtime spatial matching;
- geometry must be transformed to WGS84 and spot-checked against Karnataka lon/lat bounds before any point-in-polygon use;
- CRS readiness and `vlcode` crosswalk readiness should stay separate: CRS is solvable, while village-code reconciliation remains review-gated.

Next technical audit:

Use pyproj/GDAL/Fiona or equivalent geospatial tooling to transform a small sample of Karnataka SHP geometry from `WGS_1984_India_NSF_LCC` to WGS84, then verify transformed bounds and sample village locations.


## Karnataka SHP geometry/topology audit finding

Read-only geometry/topology audit script:

- `backend/scripts/audit_nwdp_karnataka_shp_geometry_topology.py`

Latest observed result:

- record count: 29,789;
- shape type counts: `POLYGON`: 29,789;
- source CRS: EPSG:7755, `WGS 84 / India NSF LCC`;
- target CRS for audit: EPSG:4326;
- transformed dataset corner bbox: lon/lat `[73.895883, 11.511405, 78.604372, 18.497884]`;
- all transformed dataset bbox corners were inside the buffered Karnataka envelope;
- transformed feature centers inside buffered Karnataka envelope: 29,789;
- transformed feature centers outside buffered Karnataka envelope: 0;
- zero-area shapes: 0;
- empty-point shapes: 0;
- duplicate bbox signatures: 0;
- projected area summary in square metres:
  - min: 9,384.58;
  - p05: 700,765.058;
  - median: 3,748,660.537;
  - p95: 19,719,736.41;
  - max: 1,625,874,306.052;
- point count summary:
  - min: 4;
  - median: 34;
  - max: 3,552;
- part count summary:
  - min: 1;
  - median: 1;
  - max: 63.

Interpretation:

The Karnataka SHP geometry looks spatially plausible after CRS transform. The full transformed centroid audit found no out-of-envelope feature centers, and the lightweight topology checks found no empty, zero-area, or duplicate-bbox records.

Current decision:

- CRS and coarse geometry plausibility are strong enough for deeper ingestion planning;
- boundary-to-LGD crosswalk is still the gating issue;
- runtime spatial matching remains blocked until a reviewed crosswalk policy, transformed storage model, and full geometry validation approach are designed.

Next technical audit:

Design the boundary ingestion model and reviewed crosswalk workflow before writing any geometry to the database. The first ingestion design should separate direct `vlcode` matches, unmatched `vlcode` records, special non-village features, and records requiring manual/source review.


## Ingestion and crosswalk design checkpoint

The conservative ingestion/crosswalk design is tracked in:

- `docs/nwdp-village-boundary-ingestion-crosswalk-plan.md`

The design follows the same pattern used for CoRE/LGD climate, ecological, and biospheric region mapping:

- generate inactive candidate rows;
- allow high-confidence direct-code candidates;
- route non-resolution and ambiguity to manual review;
- allow gated district/subdistrict assignment where parent codes match;
- block village assignment unless direct code or reviewed scoped match is accepted;
- promote only through explicit reviewed activation.


## Karnataka crosswalk candidate planning finding

Read-only candidate planner:

- `backend/scripts/plan_nwdp_karnataka_boundary_crosswalk_candidates.py`

Latest observed result:

- total candidate rows: 29,789;
- `AUTO_CANDIDATE`: 23,196;
- `MANUAL_REVIEW`: 6,593;
- clean direct `vlcode` matches: 23,196;
- direct `vlcode` matches with parent mismatch: 1,063;
- parent-matched but village-unresolved rows: 4,388;
- district-scoped ambiguous rows: 626;
- parent-scoped name-match rows: 233;
- parent-scoped ambiguous name rows: 28;
- special reference features: 255.

Interpretation:

The source is suitable for a reviewed candidate workflow. It is not suitable for automatic ingestion. The candidate planner follows the same pattern as the CoRE/LGD mapping work: high-confidence candidates may be staged inactive, while unresolved rows remain manual-review gated.

Detailed plan:

- `docs/nwdp-karnataka-boundary-crosswalk-candidate-plan.md`


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
Related runbook: `docs/nwdp-village-boundary-manifest-audit-runbook.md`.

Related pilot plan: `docs/nwdp-karnataka-village-boundary-pilot-audit-plan.md`.
