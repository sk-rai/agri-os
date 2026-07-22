# Backend Metadata Readiness Current State

Generated from `backend/scripts/audit_metadata_readiness.py` after the metadata readiness roadmap was added.

## Current audit snapshot

- Crops: 18 configured crops, meeting the Android scenario target of at least 15 crops.
- Crop seasons: Kharif 11, Rabi 7, Zaid 7.
- Crop taxonomy: 11 crop categories, 20 taxonomy nodes, 9 propagation types.
- Workflow coverage: 2 workflow templates, 15 workflow versions, 90 stages, 362 recommendations.
- Cost coverage: 362 recommendations include `typical_cost_per_acre`.
- Geography: 1 state, 75 districts, 350 blocks, 110,274 villages.
- PIN-code support: 110,274 villages have PIN-code metadata.
- Input catalog: 15 input categories, 30 agricultural inputs, 11 manufacturers.
- Product catalog: 0 agricultural products currently seeded.

## Interpretation

The backend has enough crop/workflow richness to test Android MVP flows across multiple crops, seasons, stages, and recommendation cost summaries. The biggest metadata gap is breadth rather than depth: geography is deep for the currently loaded state but not yet all-India, and the product catalog still needs seed/provider product rows.

## Android testing implications

- Android can start testing crop, parcel, soil, workflow, weather, enrichment, and recommendation flows now.
- Geography tests should explicitly be marked as current-state or single-state coverage until all-India LGD/Census import is completed.
- Product/provider UI tests should distinguish manufacturer/provider discovery from actual product catalog selection until agricultural products are seeded.
- Perennial/orchard current-stage onboarding, backend decision nodes, and harvest P&L summaries remain roadmap items.

## Recommended next implementation order

1. Add metadata readiness current-state docs and keep the audit script as the repeatable baseline.
2. Add all-India geography import/audit contract using LGD as canonical hierarchy and Census fields as reference aliases.
3. Seed agricultural products for existing manufacturers and inputs.
4. Add configurable season registry and local land-unit conversion registry.
5. Add workflow decision-node/perennial current-stage contracts.
6. Add stage cost rollup and harvest profit/loss summary contract.
7. Add trusted-source advisory and multimedia broadcast seed packs.

Product catalog readiness audit checkpoint
Added `backend/scripts/audit_product_catalog_readiness.py` as a read-only audit for manufacturer/input/product coverage before seeding Android product scenarios.

## Product catalog seed checkpoint

The Android product catalog scenario seed script now creates 9 representative products and packages across 8 manufacturers. The seeded scenarios cover Urea, DAP, MOP/Potash, Zinc Sulphate, Tricyclazole, Chlorpyrifos, and Sett Treatment. Remaining manufacturer gaps are Syngenta, Tata Rallis, and PI Industries. Remaining input gaps are mostly service/activity pseudo-inputs plus additional product-worthy crop protection and organic input rows.

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

## Season and land-unit metadata endpoint

The backend now exposes `GET /api/v1/forms/metadata/season-land-units` so Android can retrieve season definitions, land-unit registry rows, and conversion warnings from the server rather than hardcoding them.

Pre-Android metadata audit checkpoint
`backend/scripts/pre_android_handoff_check.py` now runs metadata, product catalog, season/land-unit, and workflow BBCH/crop-system readiness audits as part of the backend handoff gate.

Global geography model checkpoint
Added `docs/global-geography-model-roadmap.md`. Geography should evolve from India-specific state/district/block/village tables toward a generic country/profile/entity model that supports each country's administrative hierarchy, while preserving stable India APIs for Android MVP.

## Geography hierarchy profile endpoint

The backend now exposes `GET /api/v1/master-data/geography/hierarchy-profile`, making the current India cascade explicit while preserving a path toward a generic global geography model.
