# Geography Enrichment and Analytics Model

Status date: 2026-07-25

## Purpose

Define how Agri-OS should connect LGD, India Post PIN data, DigiPin, and future Census data without mixing their roles.

This document guides the all-India geography DB apply slice and keeps the design ready for Census 2026 when official datasets become available.

## Source roles

### LGD

LGD remains the canonical operational geography source for India.

Use LGD for:

- state, district, sub-district/block, and village identity;
- current government codes and official hierarchy;
- Android geography selectors and farmer/parcel administrative location fields;
- backend targeting and project geography scope.

LGD should not be overwritten by Census names or postal office names.

### India Post / OGD PIN directory

PIN data is postal reference data, not village identity.

Use PIN data for:

- PIN-code validation;
- PIN-to-village candidate lookup;
- post office metadata;
- postal district/state metadata;
- delivery/non-delivery hints;
- approximate postal lat/lng where supplied.

PIN codes are many-to-many with villages and post offices.

### DigiPin

DigiPin is coordinate-derived precision location.

Use DigiPin for:

- farmer home GPS precision when enrollment GPS is present;
- parcel centroid precision when parcel GPS/centroid is present;
- future geospatial grouping and nearest-service calculations.

Do not preload DigiPin for all PINs. Compute it at runtime from backend-validated coordinates.

### Census

Census is reference and analytics enrichment.

Use Census for:

- Census location codes;
- historical/reference names;
- population and demographic indicators;
- household and amenity indicators;
- rural/urban classification;
- underserved-area analysis;
- market opportunity and service coverage analytics.

Census should not replace LGD as canonical runtime geography.

Census 2026 should be loaded as a new versioned source when released, not merged directly into LGD rows.

## Recommended modular database shape

### Current compatibility tables

Keep these stable for Android:

- geography_states
- geography_districts
- geography_blocks
- geography_villages

These remain LGD-backed operational tables.

### Import provenance

Add or maintain import batch metadata for source snapshots:

- source_system
- source_resource_id
- source_url
- license
- retrieved_at
- applied_at
- actor_id
- reason
- raw_manifest_path
- validation_report_path
- row counts
- checksums
- status

This lets us refresh LGD, postal, DigiPin-related enrichment, and Census independently.

### Postal references

Use a dedicated table for India Post rows:

- pin_code
- office_name
- office_type
- delivery_status
- circle_name
- region_name
- division_name
- postal_district_name
- postal_state_name
- latitude
- longitude
- source/import metadata
- active flag

This table answers: what postal offices and metadata exist for this PIN?

### Village PIN links

Use a dedicated many-to-many table for LGD village to PIN links:

- village_lgd_code
- geography_village_id when matched locally
- pin_code
- state_lgd_code
- district_lgd_code
- subdistrict_lgd_code
- source/import metadata
- active flag

This table answers: which LGD villages are candidates for this PIN?

The existing geography_villages.pin_codes array can be maintained as Android compatibility cache, derived from this table.

### Future Census locations

Use separate Census tables later:

- census_year
- location_level
- census_state_code
- census_district_code
- census_subdistrict_code
- census_location_code
- census_name
- rural_urban_classification
- parent census codes
- source/import metadata

This table answers: what did Census say existed in a given census year?

### Future Census-to-LGD crosswalk

Use a separate crosswalk table:

- census_year
- census location reference
- LGD entity type
- LGD code
- geography table id when matched
- match_method
- confidence_score
- review_status
- reviewed_by
- reviewed_at
- notes

Match methods can include:

- exact_code
- exact_name_same_parent
- normalized_name_same_parent
- fuzzy_name_same_parent
- manual_review
- no_match

This table answers: which Census location corresponds to which current LGD entity, and how confident are we?

### Future Census indicators

Use a metric table rather than adding hundreds of columns:

- census_year
- census location reference
- indicator_set
- indicator_code
- indicator_label
- value_numeric
- value_text
- unit
- dimensions
- source/import metadata

Examples:

- total_population
- male_population
- female_population
- households
- literacy_rate
- main_workers
- cultivators
- agricultural_laborers
- drinking_water_near_premises
- electricity_availability
- road_access
- bank_access
- education_facility
- health_facility

This model can absorb Census 2026 without migration churn.

## Analytics enrichment ideas

### PIN-based analytics

Once postal references and village PIN links are loaded, backend analytics can support:

- farmer count by PIN;
- parcel count and area by PIN;
- active crop cycles by PIN;
- advisory/broadcast targeting by PIN;
- weather/advisory reach by postal area;
- PINs with farmer activity but weak LGD village linkage;
- PINs with high crop concentration;
- service center or field-agent route planning by PIN cluster.

### Census-based analytics later

Once Census is linked, backend analytics can support:

- farmer penetration by village population;
- crop-cycle coverage as percentage of households or cultivator population;
- underserved village ranking;
- advisory reach versus population;
- input demand opportunity by rural population and crop concentration;
- field-agent workload versus settlement density;
- finance/P&L benchmarking by demographic/amenity bands;
- irrigation/advisory targeting using amenity indicators;
- rural infrastructure-aware product planning.

### DigiPin-based analytics

DigiPin can support:

- parcel-level precision grouping;
- near-duplicate farmer/parcel detection;
- nearby farmer clusters for field-agent visits;
- weather/soil snapshot spatial matching;
- proximity to dealers, warehouses, service centers, and aggregation points.

## Runtime guardrails

Android should:

- use backend geography and PIN endpoints;
- send GPS when available;
- display backend-returned DigiPin;
- treat PIN as postal/address metadata;
- treat village/LGD as administrative identity.

Android should not:

- infer village from postal office name;
- compute canonical DigiPin;
- preload Census data;
- make live OGD/Census calls;
- compute analytics locally.

## DB apply implications for the current OGD snapshot

The immediate DB apply slice should:

1. Load LGD state/district/subdistrict/village identity into current compatibility tables.
2. Load India Post records into a postal reference table.
3. Load LGD village-PIN rows into a village-PIN link table.
4. Dedupe source rows before insert/upsert.
5. Maintain geography_villages.pin_codes as derived compatibility cache.
6. Record source manifest and validation report paths.
7. Report unresolved cases, including LGD PINs not in postal data and postal PINs without LGD village links.
8. Avoid physical deletes; use active/current flags and import provenance.
9. Leave Census tables empty/not created until a Census source snapshot is selected, unless a lightweight import batch/source table is shared across all source types.

## Decision

Proceed with LGD/PIN DB apply now using modular postal and village-link tables.

Do not block on Census. Census 2026 should be incorporated later as a versioned enrichment layer through separate Census location, crosswalk, and indicator tables.
