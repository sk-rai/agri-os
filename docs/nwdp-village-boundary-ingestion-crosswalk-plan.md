# NWDP village boundary ingestion and crosswalk plan

Status date: 2026-08-21

This document defines the conservative ingestion and review design for NWDP/GSI village boundary data.

Current status: design only. No boundary geometry should be written to the database until the reviewed import path is implemented separately.

## Source evidence summary

Karnataka pilot findings:

- NWDP Karnataka SHP/GeoJSON contains 29,789 village-boundary features.
- Source attributes include `stcode`, `dtcode`, `sdcode`, `bkcode`, `vlcode`, `district`, `subdistric`, `block`, and `village`.
- Direct `vlcode` to backend `geography_villages.lgd_code` match rate is about 81.9353%.
- 5,371 distinct `vlcode` values remain unmatched.
- Normalized name matching recovers only about 15.3364% of unmatched records.
- Parent codes align strongly:
  - district `dtcode`: 30 of 30 matched;
  - `sdcode`: 227 of 228 matched;
  - `bkcode`: 173 of 177 matched;
  - all unmatched village features still had district and `sdcode` parent-code coverage.
- CRS is EPSG:7755, `WGS 84 / India NSF LCC`.
- Transform to EPSG:4326 is viable.
- Coarse geometry/topology audit passed:
  - 29,789 of 29,789 transformed centers inside buffered Karnataka envelope;
  - zero empty-point shapes;
  - zero zero-area shapes;
  - zero duplicate bbox signatures.

## Design principle

Follow the same conservative pattern used for CoRE/LGD climate, ecological, and biospheric zone work:

1. Generate candidate rows.
2. Keep candidate rows inactive by default.
3. Auto-classify only obvious buckets.
4. Require manual review for ambiguity, non-resolution, source-version drift, and special features.
5. Promote only after explicit review.
6. Preserve backend LGD master as identity source of truth.
7. Treat NWDP/SOI geometry as reference boundary geometry, not cadastral truth.

## Proposed table family

Future tables, if implemented:

- `geography_boundary_sources`
- `geography_boundary_import_batches`
- `geography_boundary_features`
- `geography_boundary_crosswalk_candidates`
- `geography_boundary_crosswalk_reviews`
- `geography_boundary_promotions`

These names are conceptual. Final schema can be adjusted during implementation.

## Boundary source table

`geography_boundary_sources` should record:

- source code, for example `NWDP_GSI_VILLAGE_BOUNDARY`;
- producer agency;
- portal URL;
- resource URL;
- resource format;
- state/UT;
- license/terms label if available;
- source update timestamp if available;
- checksum;
- CRS;
- transform target CRS;
- source caveats;
- created/imported timestamp.

## Import batch table

`geography_boundary_import_batches` should record:

- source id;
- state/UT;
- file checksum;
- row count;
- CRS parse status;
- geometry plausibility status;
- crosswalk summary;
- import status;
- dry-run flag;
- created by;
- created timestamp.

Suggested statuses:

- `DISCOVERED`
- `DOWNLOADED`
- `AUDITED`
- `CANDIDATES_GENERATED`
- `MANUAL_REVIEW_READY`
- `PROMOTION_READY`
- `PROMOTED`
- `BLOCKED`
- `SUPERSEDED`

## Feature table

`geography_boundary_features` should store one source feature per row after an approved import path exists.

Suggested fields:

- batch id;
- source feature id;
- source state code;
- source district code;
- source subdistrict code;
- source block code;
- source village code;
- source district name;
- source subdistrict name;
- source block name;
- source village name;
- source agency;
- source geometry checksum;
- source geometry raw CRS;
- transformed geometry in backend target CRS;
- transformed centroid or label point;
- geometry validation status;
- feature category.

Feature categories:

- `VILLAGE_BOUNDARY`
- `TOWN_OR_CT_FEATURE`
- `FOREST_BEAT_OR_SPECIAL_SETTLEMENT`
- `RIVER_OR_RESERVOIR`
- `OTHER_NON_VILLAGE_REFERENCE`
- `UNKNOWN_REVIEW_REQUIRED`

## Crosswalk candidate buckets

Candidate generation should bucket every feature.

### Bucket 1: direct village code match

Condition:

- source `vlcode` exactly matches backend `geography_villages.lgd_code`.

Candidate status:

- `DIRECT_VLCODE_MATCH`

Assignment:

- backend village id can be proposed automatically;
- backend district/block must still be checked for consistency;
- row remains inactive until import/promotion policy is approved.

### Bucket 2: parent-code match plus scoped name match

Condition:

- source district/subdistrict or block code matches backend parent geography;
- source village name matches backend village canonical/census/alias name within that parent scope.

Candidate status:

- `PARENT_SCOPED_NAME_MATCH`

Assignment:

- backend village id can be proposed as a review candidate;
- reviewer should accept or reject;
- not auto-promoted.

### Bucket 3: parent-code match but village code unresolved

Condition:

- source district and subdistrict/block parent codes match;
- source `vlcode` does not match backend village LGD code;
- scoped name match is absent or ambiguous.

Candidate status:

- `PARENT_MATCH_VILLAGE_UNRESOLVED`

Assignment:

- district/subdistrict assignment may be proposed;
- village assignment must remain manual-review gated;
- geometry can be retained as source reference only.

### Bucket 4: district-only scoped match

Condition:

- district code/name matches;
- block/subdistrict is missing, stale, or ambiguous;
- village name appears in the district but not confidently under the same backend block.

Candidate status:

- `DISTRICT_SCOPED_AMBIGUOUS`

Assignment:

- district assignment can be proposed;
- tehsil/block and village assignment require manual review.

### Bucket 5: special non-village feature

Condition examples:

- `vlcode=999999`;
- names such as river, reservoir, lake, canal, beat, plantation, or other non-village reference features;
- blank or non-standard block/village code patterns.

Candidate status:

- `SPECIAL_REFERENCE_FEATURE`

Assignment:

- do not assign as a backend village;
- optionally assign to district/subdistrict as reference geometry after review;
- keep out of parcel village-boundary lookup unless explicitly approved.

### Bucket 6: blocked source caveat

Condition:

- missing expected resource;
- duplicate or mislabeled resource;
- malformed geometry;
- CRS parse failure;
- out-of-state transformed coordinates;
- source version issue.

Candidate status:

- `BLOCKED_SOURCE_CAVEAT`

Assignment:

- no automatic assignment;
- source/admin review required.

## Review statuses

Crosswalk candidates should use explicit review status values:

- `AUTO_CANDIDATE`
- `MANUAL_REVIEW`
- `REVIEW_ACCEPTED`
- `REVIEW_REJECTED`
- `PROMOTION_READY`
- `PROMOTED`
- `SUPERSEDED`
- `BLOCKED`

Default behavior:

- direct `vlcode` matches can start as `AUTO_CANDIDATE`;
- all non-direct matches should start as `MANUAL_REVIEW`;
- no candidate becomes effective until promotion.

## Confidence labels

Suggested confidence labels:

- `NWDP_DIRECT_VLCODE`
- `NWDP_PARENT_SCOPED_NAME`
- `NWDP_PARENT_ONLY_VILLAGE_UNRESOLVED`
- `NWDP_DISTRICT_ONLY_AMBIGUOUS`
- `NWDP_SPECIAL_REFERENCE_FEATURE`
- `NWDP_BLOCKED_SOURCE_CAVEAT`

## Promotion rules

No automatic promotion.

A promoted row should require:

1. source batch is audited;
2. CRS transform is verified;
3. geometry plausibility passes;
4. candidate bucket is eligible;
5. reviewer accepts the crosswalk;
6. previous active boundary mapping is preserved or superseded with audit history;
7. downstream consumers are explicitly enabled.

## Runtime rules

Before runtime point-in-polygon is enabled:

- transformed geometry must be stored in the backend target CRS;
- boundary-to-LGD crosswalk must be promoted;
- special features must be excluded or explicitly handled;
- parcel geometry conflicts must continue to use manual review rules;
- Android must not compute or infer village boundaries locally.

## Manual review surface

A future admin review view should show:

- source village name/code;
- source district/subdistrict/block name/code;
- proposed backend district/block/village;
- candidate bucket and confidence label;
- transformed centroid preview;
- source geometry metadata;
- duplicate/ambiguous match warnings;
- reviewer decision;
- reviewer note;
- audit history.

## Related import plan

Manual-review candidate import and promotion design is tracked separately in:

- `docs/nwdp-boundary-manual-review-import-plan.md`


## MVP decision

NWDP Karnataka is ready for ingestion-design planning, not DB ingestion.

The immediate next implementation should be a read-only candidate planner that outputs CSV/JSON candidate rows by bucket, similar to the CoRE/LGD manual-review import plan.
