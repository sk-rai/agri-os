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
