# Geography Data Source Contract

## Purpose

Define how Agri-OS should acquire, validate, store, and refresh geography and PIN-code data while keeping LGD as canonical India administrative geography and Census/India Post as enrichment/reference layers.

## Existing reusable repo assets

The repo already contains an Uttar Pradesh LGD import path:

- `backend/scripts/acquire_master_data/fetch_lgd_up.py`
- `backend/scripts/acquire_master_data/parse_lgd_xls.py`
- `backend/scripts/acquire_master_data/load_geography_up.py`

These scripts are useful as the starting point, especially their SpreadsheetML parsing and flexible column detection. They should be refactored before all-India use because they are UP-specific, assume fixed files in `data/raw/lgd/`, and `--reset` physically deletes current rows.

## Source roles

### LGD: canonical administrative geography

Local Government Directory is the canonical source for officially recognized Indian administrative geography. LGD records should drive state/district/sub-district/village identity and codes.

Primary source options:

- Data.gov LGD catalog: https://www.data.gov.in/catalog/local-government-directory-lgd
- LGD download directory: https://lgdirectory.gov.in/demo/downloadDirectory.do
- OGD resource: Local Government Directory (LGD) - Villages with PIN Codes
- OGD API resource id: `f17a1608-5f10-4610-bb50-a63c80d83974`
- API path to test after key generation: `GET /resource/f17a1608-5f10-4610-bb50-a63c80d83974`

### India Post / OGD PIN directory: postal reference

PIN-code data should come from Department of Posts / OGD postal datasets. PIN/post office coverage is many-to-many with villages/localities and should not be treated as a village identity source.

Primary source options:

- India Post PIN-code list: https://www.indiapost.gov.in/rti/pincodelist
- OGD resource: All India Pincode Directory till last month
- OGD API resource id: `5c2f62fe-5afa-4119-a499-fec9d604d5bd`
- API path to test after key generation: `GET /resource/5c2f62fe-5afa-4119-a499-fec9d604d5bd`

### Census: comprehensive reference and enrichment

Census geography is valuable for comprehensive settlement, demographic, and planning indicators, but it should not overwrite LGD canonical recognition. Census can contain places that do not map cleanly to active LGD villages, including settlements vulnerable to reclassification, merger, displacement, or eviction risk. Those records are still important as reference/enrichment for underserved-area analysis and future business opportunity planning.

Census should be used for:

- aliases and historical/reference names
- census village/town codes
- population and demographic indicators
- settlement coverage analysis
- underserved-area and market opportunity analysis

Census should not be used to mutate LGD canonical codes/names directly.

Primary source options:

- Census population finder: https://censusindia.gov.in/census.website/data/population-finder
- Census 2011 Location Code Directory / ORGI: https://censusindia.gov.in/nada/index.php/catalog/42648
- OGD Census village directory catalog: https://www.data.gov.in/catalog/complete-villages-directory-indiastatedistrictsub-district-level-census-2011

## License

Data.gov resources are under Government Open Data License - India: https://data.gov.in/government-open-data-license-india

Every import batch should persist source URL/resource id, license, retrieval timestamp, checksum, row counts, validation report, actor, and applied/expired status.

## Runtime decision: local replicate vs direct API

Agri-OS should replicate geography and PIN data locally for runtime use. Direct OGD/API calls should be limited to acquisition, scheduled refresh, validation, and admin reconciliation workflows.

Reasons to replicate locally:

- Android needs offline-first geography lookup.
- Village/PIN search needs predictable low latency.
- PIN-to-village mapping requires reconciliation and many-to-many handling.
- Admin edits/aliases/expiry must be audited locally.
- Runtime should not depend on API key availability, rate limits, or external downtime.
- Snapshot imports make validation, rollback, and diff review possible.

Direct API use is acceptable for:

- source acquisition
- refresh checks
- admin preview/diff
- reconciliation jobs
- metadata provenance validation

## Import model

The all-India importer should support:

- `detect`: inspect source fields and sample rows
- `validate`: produce counts, duplicate checks, parent/child integrity checks, and diff summary without writing
- `stage`: store normalized rows in import-batch tables
- `apply`: admin-approved apply with actor/reason
- `expire_missing`: optional logical expiry for source rows missing from newer feed
- no physical delete by default

## Data model direction

MVP can continue using current India tables:

- `geography_states`
- `geography_districts`
- `geography_blocks`
- `geography_villages`

Next-phase India/global model should add generic entities:

- `geo_entity` for country-specific hierarchy nodes
- `geo_entity_alias` for local names/translations/Census aliases
- `geo_entity_postal_code` for many-to-many PIN/postal relationships
- `geo_admin_level_profile` for country-specific level labels and order
- `geo_import_batch` for source/audit/provenance

## Governance

- LGD canonical fields are not manually editable in admin UI.
- Admins may add aliases, labels, translations, PIN associations, operational grouping, and expiry/deactivation metadata.
- Canonical corrections must come through verified import/versioning.
- Census enrichment may be attached as reference metadata but cannot override LGD canonical identity.
- PIN-code refresh should reconcile candidates rather than blindly replacing village identity.

## Immediate next implementation

1. Create OGD API-key setup notes.
2. Add read-only OGD resource probe script for the two resource ids.
3. Refactor UP loader patterns into generic all-India detect/validate helpers.
4. Add validation summaries before any local DB mutation.
5. Decide final local schema for PIN/post office many-to-many mapping.

OGD geography probe checkpoint
A read-only OGD geography source probe is now defined in `backend/scripts/probe_ogd_geography_sources.py`. It supports the LGD villages-with-PIN resource and the All India PIN-code directory resource, redacts API keys, performs no database writes, and is intended to inspect schemas before the all-India staged import/diff pipeline is built.

All-India geography import checkpoint
An all-India geography import plan now defines the phased flow: source probe, raw snapshot acquisition, staging validation, diff, admin-approved apply, and local runtime serving. LGD remains canonical; PIN/post-office associations are separate postal references; Census is reserved for aliases, demographics, and business-opportunity enrichment without overriding LGD identity.
