# Global Geography Model Roadmap

## Principle

Agri-OS geography must support India first without hardcoding India-only assumptions into the platform. The model should support country-specific administrative hierarchies, government source identifiers, aliases, postal codes, and operational groupings.

## India profile

For India, Local Government Directory should be the canonical government hierarchy where available, with Census names/codes and PIN-code associations as supporting reference metadata.

Typical India hierarchy:

- Country: India
- State / Union Territory
- District
- Sub-district / Block / Tehsil / Taluk, depending on state terminology
- Village / Town / Locality
- PIN-code association, many-to-many with villages/localities

## Global profile

Other countries may have different levels and names. Examples:

- Country > Province > District > Municipality > Village
- Country > State > County > Sub-county > Parish
- Country > Region > Department > Commune
- Country > Province > Regency > District > Village

The platform should model levels generically rather than assuming fixed `state/district/block/village` columns everywhere.

## Recommended canonical model

- `geo_entity`: generic node with `country_code`, `level_code`, `name`, `parent_id`, `source_system`, `source_code`, `status`, `effective_from`, `expires_at`.
- `geo_entity_alias`: local names, spellings, translations, Census names, search aliases.
- `geo_entity_postal_code`: many-to-many postal/PIN/ZIP relationships.
- `geo_admin_level_profile`: per-country hierarchy definitions and labels.
- `geo_import_batch`: source file/URL, checksum, actor, validation report, applied/expired status.
- Existing India-specific tables can remain as optimized compatibility views/tables during migration.

## Governance

Canonical government fields must not be manually edited in ways that contradict the source dataset. Admins can add aliases, display labels, translations, operational groupings, and expiry/deactivation metadata. Canonical corrections should happen through verified import/versioning with source evidence.

## Android behavior

Android should consume backend geography metadata and not assume that every country has state/district/block/village. The UI should render the country-specific cascade declared by the backend. For India, Android can keep the current state/district/block/village/PIN flow while the backend evolves toward the generic model.

## Implementation path

1. Keep current India geography APIs stable for Android MVP.
2. Add a read-only audit/roadmap for country-specific hierarchy support.
3. Add generic geography metadata endpoint describing active levels and labels.
4. Add all-India LGD/Census import validation using current tables or staging tables.
5. Add generic `geo_entity` model/migration only when ready to support non-India geography or multi-country imports.
6. Maintain compatibility endpoints until Android can render generic country profiles.

## Current metadata endpoint

`GET /api/v1/master-data/geography/hierarchy-profile` exposes the current India compatibility cascade plus the global target model and governance rules. This lets Android consume geography levels from backend metadata before the generic `geo_entity` migration is introduced.

Global geography readiness audit checkpoint
Added `backend/scripts/audit_global_geography_readiness.py` to verify the geography hierarchy profile endpoint, current India compatibility counts, and explicit remaining gaps before all-India/global rollout.

Pre-Android global geography audit checkpoint
`backend/scripts/pre_android_handoff_check.py` now includes the global geography readiness audit, ensuring the hierarchy-profile endpoint and India/global geography gaps stay visible during handoff validation.

Geography data source contract checkpoint
Added `docs/geography-data-source-contract.md`, documenting LGD as canonical India geography, India Post/OGD PIN datasets as postal reference, Census as enrichment/reference data, and the decision to replicate validated source snapshots locally rather than relying on live external APIs at runtime.
