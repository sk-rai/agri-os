# NWDP Karnataka village boundary pilot audit plan

Status date: 2026-08-21

## Purpose

The Karnataka pilot should answer one practical question before any all-India boundary work:

Can the NWDP/GSI village boundary files be reliably crosswalked to our existing LGD geography hierarchy, or do they require fuzzy/manual reconciliation like the earlier SOI shapefile alignment work?

This pilot is intentionally scoped to one state and should remain outside production ingestion until reviewed.

## Why Karnataka first

Karnataka is a good first pilot because:

- current Android/FPO demo fixtures use Karnataka-style geography;
- the NWDP manifest audit shows one visible KML, one GeoJSON, and one SHP resource for Karnataka;
- there is no Karnataka-specific duplicate/missing format issue in the manifest audit;
- we already have PIN/village and project demo context around Karnataka villages.

## Primary questions

The pilot should determine:

1. Does the file contain LGD village identifiers?
2. Does it contain district identifiers that match our loaded geography?
3. Does it contain subdistrict, taluk, tehsil, or block identifiers?
4. Are identifiers numeric, stable, and documented?
5. If LGD IDs are missing, are village/district/subdistrict names clean enough for deterministic crosswalk?
6. Are there duplicate village names within districts or subdistricts?
7. Are geometries valid enough for point-in-polygon and parcel-overlap checks?
8. What CRS is used?
9. Are polygons or multipolygons used?
10. Is feature count plausible against Karnataka LGD village counts?

## Attribute audit checklist

For each candidate file, especially GeoJSON and SHP, capture:

- file format;
- file size;
- checksum;
- CRS;
- geometry type;
- feature count;
- attribute field names;
- sample feature attributes;
- candidate state code/name fields;
- candidate district code/name fields;
- candidate subdistrict/taluk/tehsil/block code/name fields;
- candidate village code/name fields;
- any LGD code fields;
- any Census code fields;
- any object/source IDs;
- null/blank rate for key fields;
- duplicate key candidates;
- non-ASCII or local-language name fields;
- name normalization issues.

## Crosswalk decision tree

### Case A: LGD village IDs are present and match

If the file has usable LGD village IDs:

- map boundary features directly to `geography_villages`;
- verify district/subdistrict parent consistency;
- store match method as `LGD_CODE`;
- mark confidence high unless geometry or duplicate issues appear.

This is the cleanest case.

### Case B: District/subdistrict IDs present, village LGD missing

If district/subdistrict IDs match but village IDs are missing:

- use district/subdistrict as a hard scope;
- match village names within that scope;
- store match method as `SCOPED_NAME_MATCH`;
- require duplicate-name review before high confidence.

This is usable but needs review.

### Case C: Only names are present

If only state/district/subdistrict/village names are present:

- normalize names;
- compare against loaded LGD names and aliases;
- flag duplicates;
- store match method as `FUZZY_NAME_MATCH` or `MANUAL_REVIEW`;
- do not treat this as automatic authoritative linkage.

This is similar to the SOI challenge and should remain review-gated.

### Case D: Attributes are weak or undocumented

If attributes are weak, missing, or inconsistent:

- use boundary layer only as standalone reference geometry;
- avoid joining to LGD automatically;
- use for visual/planning experiments only;
- require a separate crosswalk project before app/runtime use.

## Geometry audit checklist

The pilot should test:

- CRS detection and transformation to WGS84 if needed;
- invalid geometry count;
- empty geometry count;
- polygon versus multipolygon distribution;
- bounding box sanity for Karnataka;
- self-intersections;
- duplicate geometries;
- very small or very large polygon outliers;
- point-in-polygon performance on sample GPS points;
- overlap behavior for parcel polygons.

## AgriFabric model implications

If crosswalk is clean, NWDP village boundaries can strengthen:

- project geography setup;
- village-scoped FPO cohorting;
- GPS-to-village validation;
- advisory targeting by spatial village context;
- field-agent coverage analysis;
- future insurance/subsidy review evidence.

If crosswalk is weak, the layer is still useful, but only as:

- provider reference geography;
- visual planning context;
- manual review assist;
- future enrichment candidate.

## Claim boundaries

Even if the pilot succeeds:

- village boundary is not cadastral truth;
- village boundary does not prove land ownership;
- village boundary does not replace parcel GPS or plot polygon;
- village boundary does not replace LGD administrative identity;
- DigiPin remains backend-generated from coordinates;
- Android should not perform canonical village-boundary matching locally.

Safe phrase:

The Karnataka pilot checks whether NWDP/GSI village boundaries can be joined to AgriFabric's LGD geography model and used as reference locality context for planning, validation, and future review workflows.

## Suggested pilot outputs

The pilot should produce:

- JSON audit report;
- one small attribute summary table;
- geometry validity summary;
- crosswalk readiness decision;
- sample matched and unmatched features;
- recommendation: proceed, hold, or manual-review required.

Suggested schema names for future scripts:

- `nwdp_village_boundary_karnataka_pilot_audit.v1`
- `nwdp_village_boundary_crosswalk_readiness.v1`

## Pilot result checkpoint

The first Karnataka audit confirmed that the downloaded GeoJSON is inside a ZIP resource and contains 29,789 MultiPolygon features.

Structured attributes include `vlcode`, `village`, `dtcode`, `district`, `sdcode`, `subdistric`, `bkcode`, `block`, `stcode`, and `state`.

The initial DB sample crosswalk matched 2 of 5 sampled `vlcode` values against `geography_villages.lgd_code`.

Decision:

- continue to full `vlcode` coverage audit;
- do not ingest yet;
- identify CRS before any spatial matching;
- treat unmatched codes as a reconciliation question, not an Android/runtime blocker.

## Full coverage checkpoint

The full Karnataka `vlcode` coverage audit produced the first meaningful source-confidence number:

- 29,732 distinct NWDP `vlcode` values;
- 24,361 matched backend LGD village codes;
- 5,371 unmatched distinct codes;
- 81.9353% match rate.

This means the source is promising but not ingestion-ready.

Next step: classify the unmatched records before deciding whether a reviewed crosswalk table, manual review queue, or source-specific exception strategy is needed.

## Unmatched name-match checkpoint

The unmatched-name audit showed that only 15.3364% of unmatched records can be recovered by normalized name matching.

This means the remaining mismatch is not mostly simple spelling variation. The likely causes include source vintage mismatch, village-code drift, administrative reorganization, Census/SOI settlement records, and special non-village features.

Next step: parent-code drift audit using `dtcode`, `sdcode`, and `bkcode`.

## Parent-code drift checkpoint

The parent-code drift audit showed strong parent alignment:

- 30 of 30 distinct NWDP `dtcode` values matched backend district codes;
- 227 of 228 distinct NWDP `sdcode` values matched backend block codes;
- 173 of 177 distinct NWDP `bkcode` values matched backend block codes;
- all 5,425 unmatched village features still had matching district and `sdcode` parent codes;
- 5,166 unmatched village features also had matching `bkcode`;
- 0 unmatched village features lacked parent-code coverage entirely.

This narrows the problem. The unresolved issue is not that NWDP is floating outside the backend parent geography hierarchy; it is that a material number of village-level `vlcode` values do not match current backend LGD village codes.

Next steps:

- inspect the SHP `.prj` or source metadata to identify CRS;
- compare unmatched `vlcode` values against backend `census_village_code`;
- design a reviewed boundary-crosswalk queue with buckets for direct code match, parent-scoped name match, special non-village features, and unresolved records.

## CRS checkpoint

The SHP CRS audit found a valid `.prj` file and identified the source CRS as `WGS_1984_India_NSF_LCC`, a Lambert Conformal Conic projected CRS using WGS 1984 as the geographic base.

This resolves the earlier bbox warning: the Karnataka boundary coordinates are projected meters, not WGS84 lon/lat.

Next step: run a transform sample audit before spatial use. The transform audit should prove:

- source CRS can be parsed by pyproj/GDAL;
- transformed bbox falls within plausible Karnataka lon/lat bounds;
- a small set of transformed feature centroids lands in expected districts;
- geometry remains valid enough for reference-boundary use after transformation.


## Geometry/topology checkpoint

The geometry/topology audit transformed all 29,789 feature centers from EPSG:7755 to EPSG:4326 and found every center inside a buffered Karnataka lon/lat envelope.

It also found:

- zero empty-point shapes;
- zero zero-area shapes;
- zero duplicate bbox signatures.

This means coarse geometry plausibility is strong. The remaining gate is no longer CRS or gross spatial placement; it is crosswalk governance and ingestion design.

Next step: design the boundary ingestion and crosswalk workflow before any DB write path is implemented.


## Recommended next implementation step

Create a read-only pilot script that downloads only the Karnataka GeoJSON or accepts a locally downloaded file, then reports:

- metadata;
- attribute fields;
- sample features;
- CRS/geometry summary;
- candidate LGD fields;
- exact-code crosswalk feasibility;
- name-based crosswalk risk.

The script should not write to the database.

Related runbook and script: `docs/nwdp-karnataka-village-boundary-pilot-audit-runbook.md`, `backend/scripts/audit_nwdp_karnataka_village_boundary_pilot.py`.
