# Backend Metadata Readiness Roadmap

This roadmap defines the metadata and scenario-readiness work needed before Android implementation starts in earnest.

The goal is not just to have APIs. The backend must contain enough realistic, configurable, auditable metadata to test real farmer, crop, geography, advisory, and financial scenarios.

## Guiding principles

- Android must not hardcode geography, crop stages, seasons, local units, crop suitability, advisory rules, cost logic, or provider calls.
- Backend owns canonical metadata, validation, warnings, branching, costs, and summaries.
- Android displays backend-provided forms, options, warnings, decision points, advisories, and summaries.
- Metadata must be importable, auditable, testable, and tenant/project configurable.
- Trusted internet/government sources can be used for seed data only with source, attribution, license/usage note, and retrieval date.

## 1. Geography metadata readiness

Current concern: geography appears to be heavily focused on one state. Android testing needs broader coverage.

Target state:

- LGD is the canonical administrative hierarchy.
- Census data is supported as alias/reference metadata, not as the primary hierarchy.
- All India states and districts should be available.
- Blocks/subdistricts and villages should be progressively imported where data is available.
- PIN-code to village mapping remains a helper for parcel onboarding, not the canonical hierarchy.

Required audit:

- state count;
- district count;
- block/subdistrict count;
- village count;
- LGD code coverage;
- Census code/name alias coverage;
- PIN-code coverage;
- duplicate or conflicting code/name detection;
- stale source/retrieval metadata.

## 2. Crop catalog scenario pack

Android and backend testing should have at least 15–25 crops across classifications.

Suggested minimum coverage:

- cereals: rice, wheat, maize, pearl millet;
- pulses: chickpea, pigeon pea, green gram, black gram;
- oilseeds: mustard, groundnut, soybean, sunflower;
- cash crops: sugarcane, cotton;
- vegetables: potato, onion, tomato, cucumber, bottle gourd;
- horticulture/perennial: mango, apple, banana, guava, citrus;
- minor/regional crops where project scope requires them.

Each crop should include:

- crop code;
- local names/aliases;
- classification/taxonomy;
- suitable seasons;
- suitable geographies/climate hints;
- propagation options;
- default lifecycle type;
- typical duration;
- soil/climate suitability metadata.

## 3. Seasons and local land units

Seasons such as Kharif, Rabi, and Zaid must remain backend-configurable.

Local land units must be backend-owned and region/project configurable.

Required capabilities:

- configurable season option sets;
- region/project-specific land unit registry;
- conversion factors to normalized units;
- store original reported unit/value;
- compute internally in acre/hectare;
- present summaries back in farmer/project preferred local units;
- support units such as acre, hectare, bigha, biswa, katha, guntha, and regional variants.

Financial summaries must compute from normalized units but display both normalized and local-unit views.

## 4. Input/provider/company metadata

Testing needs realistic providers and inputs.

Seed/prepopulate:

- major seed companies;
- fertilizer companies;
- pesticide/agrochemical companies;
- machinery/service providers;
- FPOs/cooperatives where available;
- buyers/traders/warehouses where relevant.

Company data should use discovery candidates first, not direct live profile mutation. All source references and verification states should be stored.

Input catalog should include:

- seeds;
- fertilizers;
- pesticides;
- herbicides;
- irrigation inputs;
- labor operations;
- machinery operations;
- harvest/post-harvest inputs.

## 5. Crop stages, branching, and decision paths

Crop lifecycle must support decision points, not only linear stages.

Examples:

- paddy: nursery + transplanting path vs direct-seeded path;
- sugarcane: ratoon crop vs fresh planting after harvest;
- horticulture: already-established orchard current-stage onboarding;
- vegetables: nursery vs direct sowing;
- pest/disease branch: preventive vs corrective treatment path.

Backend should define:

- decision node code;
- eligible crop/season/geography;
- choices;
- downstream stages enabled/disabled by choice;
- required observations before decision;
- audit trail of farmer/agent choice;
- Android display labels and warnings.

## 6. Perennial/orchard and mid-cycle onboarding

Many horticulture farmers will already have established orchards. Android must not force sowing/nursery questions when the crop is already at flowering, fruiting, dormancy, harvest, or maintenance stage.

Required support:

- lifecycle type: annual, perennial, ratoon, already-established;
- crop cycle can start at current stage;
- orchard age/year of planting;
- current stage selection;
- crop/season/geography suitability warnings;
- configurable override rules;
- warning confirmation and reason capture;
- stage-specific advisory and task generation from the chosen current stage.

Warnings should be backend-configurable and non-blocking where appropriate:

- crop not typical for selected geography;
- crop not typical for selected season;
- stage inconsistent with crop calendar;
- orchard age inconsistent with selected stage;
- project scope mismatch;
- farmer can proceed after confirmation where project policy allows.

## 7. Stage cost and harvest P&L

Recommendations should carry stage-specific cost metadata. Backend should summarize:

- stage cost;
- cumulative cost;
- input/labor/machinery cost split;
- expected yield;
- realized yield;
- sale price;
- gross revenue;
- net profit/loss;
- per-acre/per-hectare/per-local-unit summaries;
- total parcel/crop-cycle summary.

Android should display backend-calculated summaries, not calculate core P&L locally.

## 8. Advisory and broadcast seed content

Broadcast/advisory testing needs realistic seed content.

Seed content categories:

- generic seasonal advisories;
- crop-specific advisories;
- stage-specific advisories;
- weather-risk advisories;
- pest/disease scouting advisories;
- fertilizer/irrigation reminders;
- post-harvest advisories;
- orchard-specific advisories;
- multimedia broadcasts.

Trusted sources:

- ICAR/KVK advisories;
- state agriculture departments;
- IMD/weather safety advisories;
- government pest/disease bulletins;
- open-license/public-domain media;
- internally generated generic media for tests.

Every sourced advisory/media item should store:

- source URL;
- source organization;
- retrieval date;
- license/usage note;
- adapted summary text;
- crop/season/stage/geography tags;
- language;
- attribution metadata;
- media type and attachment metadata.

Broadcast scenarios to test:

- all-farmer broadcast;
- crop-specific broadcast;
- stage-specific broadcast;
- geography-specific broadcast;
- weather-risk broadcast;
- language-specific broadcast;
- multimedia broadcast;
- urgent alert;
- scheduled advisory;
- expired/cancelled advisory;
- failed delivery retry;
- farmer read/ack flow.

## 9. Web UI functional/screenshot test sweep

Before Android starts, admin web should be walked through with automated UI tooling.

The sweep should:

- login;
- visit each admin route;
- capture screenshots;
- test search/filter/list actions;
- test safe dry-run actions;
- test CSV template downloads and validation where possible;
- avoid destructive/publish actions unless using a test tenant;
- produce screenshot artifacts;
- produce JSON result report;
- produce Markdown summary of works/fails/blocked.

## Recommended next execution order

1. Add metadata readiness audit scripts for geography, crops, inputs, workflows, advisories, and units.
2. Run audit and document current coverage.
3. Build all-India LGD/census import/update plan.
4. Build crop scenario seed pack.
5. Build local unit conversion registry.
6. Build perennial/orchard/mid-cycle onboarding contract.
7. Build workflow decision-node contract.
8. Build cost/P&L backend summary contract.
9. Build advisory/broadcast seed content import plan.
10. Build web UI screenshot/functional sweep runner.

## Metadata readiness audit script

Run `backend/scripts/audit_metadata_readiness.py` to inspect current geography, crop, input/provider, and workflow metadata coverage before expanding Android scenario testing.

Metadata readiness current-state checkpoint
The repository now includes `docs/backend-metadata-readiness-current-state.md`, summarizing the first metadata audit baseline: crops/workflows are already rich enough for Android MVP testing, while all-India geography expansion and agricultural product seeding remain the next backend metadata priorities.

Product catalog scenario seed checkpoint
The first Android product scenario seed pack is in place. Next product metadata work should add remaining manufacturer coverage, organic inputs, seed products, and explicit pricing/effective-date metadata.

Season and land-unit readiness audit checkpoint
Added `backend/scripts/audit_season_land_unit_readiness.py` to measure backend season metadata, parcel unit usage, and readiness for normalized acre/hectare calculations with local-unit display.

## Metadata governance rule

All metadata mutations must be admin/backoffice controlled and audit logged. This applies to geography aliases/imports, crop taxonomy, crop seasons, local unit conversions, input/product catalog rows, workflow templates, advisory seed content, and broadcast templates. The preferred mutation model is append/update/expire rather than physical delete: rows should keep `created_at`, `updated_at`, actor metadata, reason, and where relevant `effective_from`, `expires_at`, `status`, or `is_active`. Runtime consumers should decide visibility/validity from status plus effective/expiry windows. Physical deletion should be reserved for failed imports, temporary staging rows, or explicit maintenance tasks with audit trail.

## Geography canonical-data guardrail

Geography records sourced from Local Government Directory, Census, or other government reference datasets must be treated as canonical reference data. Admin UI/API edits must not allow changing LGD codes, government names, hierarchy parentage, or other canonical fields in a way that contradicts the source dataset. Allowed admin actions should be limited to adding local aliases, display labels, translations, PIN-code associations, operational grouping, temporary deactivation/expiry, or import-batch corrections with source evidence. Corrections to canonical geography should flow through a verified import/versioning process with source URL/file, import batch ID, actor, timestamp, and reason. Runtime Android search should use canonical records plus approved aliases, while preserving the government-backed identifiers for audit and interoperability.

Season and land-unit registry checkpoint
Added a config-backed season and land-unit registry with Kharif/Rabi/Zaid/Perennial support, canonical acre/hectare conversion, and explicit unsafe placeholders for variable local units such as Bigha/Biswa until geography-scoped conversion is known.

Season and land-unit Android exposure checkpoint
The profile forms/options API now exposes backend-configured season and land-unit registry metadata. Android can keep displaying familiar values such as BIGHA/BISWA/KATHA/GUNTHA, while backend metadata marks variable local units as requiring geography-scoped conversion before normalized acre/hectare calculations and P&L summaries.

Area normalization contract checkpoint
The season/land-unit registry now includes an area normalization result contract. Safe units convert to acres/hectares, while unsupported or geography-variable local units return explicit statuses instead of silently producing unsafe financial/P&L calculations.

Perennial and long-duration crop onboarding checkpoint
Added a backend policy contract for annual crops, perennial orchards, plantation crops, perennial spices, and agroforestry/timber systems. Android should allow existing orchards/plantations/agroforestry parcels to start at their current stage, while showing backend-configured warnings for missing establishment year, unusual stage, season/calendar mismatch, or geography mismatch.

Workflow BBCH and crop-system customization checkpoint
Added `docs/workflow-crop-system-bbch-customization.md`. BBCH remains the baseline crop-stage classification spine, while client/project workflow customizations layer labels, stage durations, decision nodes, recommendations, costs, and crop-system onboarding metadata on top through workflow templates/versions/overrides.

Workflow BBCH/crop-system audit checkpoint
Added `backend/scripts/audit_workflow_bbch_crop_system_readiness.py` to measure BBCH range coverage, propagation-step stages, recommendation cost coverage, decision-like recommendations, and missing crop-system metadata on workflow templates.

Workflow crop-system metadata backfill checkpoint
Added `backend/scripts/backfill_workflow_crop_system_metadata.py` to backfill crop-system, BBCH baseline, allowed start stages, warning rules, and decision-node metadata on existing Rice/Sugarcane workflow templates and versions without changing stage rows.

Global geography model checkpoint
Added `docs/global-geography-model-roadmap.md`. Geography should evolve from India-specific state/district/block/village tables toward a generic country/profile/entity model that supports each country's administrative hierarchy, while preserving stable India APIs for Android MVP.

Geography data source contract checkpoint
Added `docs/geography-data-source-contract.md`, documenting LGD as canonical India geography, India Post/OGD PIN datasets as postal reference, Census as enrichment/reference data, and the decision to replicate validated source snapshots locally rather than relying on live external APIs at runtime.

OGD geography probe checkpoint
A read-only OGD geography source probe is now defined in `backend/scripts/probe_ogd_geography_sources.py`. It supports the LGD villages-with-PIN resource and the All India PIN-code directory resource, redacts API keys, performs no database writes, and is intended to inspect schemas before the all-India staged import/diff pipeline is built.

All-India geography import checkpoint
An all-India geography import plan now defines the phased flow: source probe, raw snapshot acquisition, staging validation, diff, admin-approved apply, and local runtime serving. LGD remains canonical; PIN/post-office associations are separate postal references; Census is reserved for aliases, demographics, and business-opportunity enrichment without overriding LGD identity.

OGD acquisition next step
Generate the Data.gov.in API key, run the OGD source probe with `--include-sample`, fetch one raw page from each resource, and validate the manifest before implementing the staging mapper. Runtime Android/web APIs should continue using local replicated data, not live OGD calls.
