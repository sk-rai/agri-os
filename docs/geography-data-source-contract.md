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

## NWDP / GSI village boundary polygon source

NWDP/GSI village boundary resources are a candidate future polygon reference layer for village-scale spatial context.

This layer should be treated separately from existing LGD, PIN/postal, Census/reference, parcel geometry, and DigiPin layers.

Intended use:

- project service-area planning;
- GPS-to-village candidate validation;
- village-boundary cohorting;
- advisory targeting support;
- future review-assistive insurance/subsidy evidence workflows.

Boundary:

- village boundary is not cadastral parcel truth;
- village boundary is not land ownership proof;
- GPS parcel point or polygon remains the field precision evidence;
- DigiPin remains backend-generated from coordinates;
- Android should not ship or compute canonical boundary matching locally.

Before ingestion, create a source manifest and pilot-state audit covering resource URLs, formats, license labels, checksums, CRS, geometry validity, attributes, and LGD crosswalk readiness. The first NWDP manifest audit found a portal caveat: Uttarakhand SHP is missing from the expected matrix while Telangana SHP appears twice, so all-India ingestion should remain blocked until reviewed.

Detailed source-readiness note: `docs/nwdp-village-boundary-source-readiness.md`.

## OGD geography operational runbook

The local development database has been populated from the OGD all-India geography snapshot. Cloud or Render environments must not assume this local data exists. They should reproduce the load from source snapshots using the same staged-data workflow.

### Local authoritative snapshot

Current local authoritative OGD geography apply:

- source: OGD LGD villages with PIN codes + OGD all-India PIN directory;
- staged snapshot: `data/staged/ogd_geography/20260725T095703Z`;
- active authoritative import batch: `e1c2c445-c1ee-4acf-af27-c2b9e909147f`;
- loaded active postal references: `165617`;
- loaded active village-PIN links: `560316`;
- villages with PIN compatibility cache: `560151`.

Interrupted local apply attempts were soft-deactivated in `geography_import_batches` and kept only as local audit history.

### Cloud/Render reproduction sequence

For a fresh environment:

1. Configure `DATA_GOV_IN_API_KEY` outside source control.
2. Fetch OGD raw snapshots.
3. Validate and stage raw snapshots.
4. Run Alembic migrations through revision `049`.
5. Apply the staged OGD geography snapshot.
6. Run SQL-only fast verification.
7. Run Android backend closeout checks.

Use the latest source snapshot available at deployment time. Do not copy local database rows blindly into production unless an explicit database migration/seed process has been approved.

### Verification command

After apply, run:

`backend/scripts/apply_ogd_geography_snapshot.py --staged-dir <staged-dir> --refresh-mode INCREMENTAL_REFRESH --fast-verify`

The verification should report:

- `postal_references` equals staged postal references;
- `village_pin_links` equals staged village-PIN links;
- `unmatched_links` is `0`;
- `bad_postal_lat` is `0`;
- `bad_postal_lng` is `0`.

### Refresh cadence

Recommended cadence:

- monthly or as-needed API fetch and fast verification for update checks;
- incremental refresh when OGD totals/checksums change;
- annual full refresh with `--expire-missing` only after reviewing validation and diff summaries.

Census 2026 remains a separate future enrichment source and should not be merged into LGD identity rows.

## Runtime PIN lookup guardrail

The Android PIN lookup endpoint returns backend-computed guardrail status from the loaded OGD geography tables.

Runtime behavior:

- PIN validation first checks active India Post/OGD postal references.
- LGD village candidates come from active LGD village-PIN links.
- A valid postal PIN may have zero LGD village candidates, especially for urban/core postal areas.
- Android must treat `VALID_POSTAL_PIN_NO_LGD_VILLAGES` as a valid PIN state, not junk input.
- Android may ask the user to enter/select village manually when no LGD candidates exist.
- Unknown PINs return `PIN_NOT_FOUND`.
- Malformed PINs remain request-validation errors.

This keeps postal identity, LGD village identity, and user-entered fallback village text separate.

## Census and analytics enrichment checkpoint

Census should remain a separate enrichment layer for aliases, demographic indicators, household/amenity indicators, and business-opportunity analytics. The LGD/PIN DB apply should therefore add modular postal reference and village-PIN link structures now, while keeping Census crosswalk and indicator tables separate for Census 2026 or any curated Census 2011 import.

See `docs/geography-enrichment-analytics-model.md`.

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

## Local file fallback

The primary near-term import path can use locally acquired CSV/XML source files while Data.gov.in OTP/API-key authorization is pending. These local files must still be treated as raw source snapshots with license/source metadata, checksums, validation summaries, and no direct database mutation outside the staged import/apply workflow.
