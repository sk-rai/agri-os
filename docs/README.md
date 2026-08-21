# Agri-OS Documentation

## Structure

```
docs/
├── README.md                ← This file
├── reconciliation/          ← AUTHORITATIVE governance decisions
│   ├── adrs/               ← Architecture Decision Records (9 ADRs + semantic registry)
│   ├── contracts/          ← Behavioral specifications (13 documents)
│   └── operations/         ← Operational governance (5 documents)
│
└── sources/                 ← RAW INPUT MATERIAL (not authoritative)
    ├── ai-1/               ← Original AI-1 documents (15 files expected)
    └── reviews/            ← 4-pass architecture review reports (6 files)
```

## Reading Order (for new team members)

1. `reconciliation/adrs/ADR-001-architecture-identity.md` — What kind of system is this?
2. `reconciliation/adrs/canonical-semantic-registry-v1.md` — What do we call things?
3. `reconciliation/adrs/ADR-005-mvp-vertical-slice.md` — What are we building first?
4. `reconciliation/adrs/farmer-value-ladder.md` — Why would farmers use this?
5. `reconciliation/contracts/mvp-api-contract.md` — What does the API look like?
6. `reconciliation/contracts/complete-state-machines.md` — How do workflows behave?
7. `backend-driven-platform-architecture.md` — How are backend-driven platform modules evolving?
8. `profile-form-contracts.md` — How should farmer/parcel/soil profile forms be rendered?

## Governance Rule

- **reconciliation/** = implementation law (frozen decisions)
- **sources/** = historical reference (how we got here)
- If sources and reconciliation conflict → reconciliation wins
- Changes to reconciliation require explicit decision + version bump

## AgriFabric landing and demo planning

Current landing/demo planning docs:

- `android-mvp-readiness-summary.md` — MVP-ready Android capability summary.
- `landing-page-content-brief.md` — positioning, claims, and boundaries.
- `landing-page-wireframe.md` — section-by-section page blueprint.
- `landing-page-implementation-backlog.md` — implementation and asset status.
- `demo-script-pack.md` — demo narrative scripts.
- `demo-asset-inventory.md` — proof assets and capture inventory.
- `agrifabric-demo-video-capture-matrix.md` — future video capture matrix by landing tab and capture mode.
- `agrifabric-static-demo-capture-runbook.md` — static landing-page capture order, scripts, and claim boundaries.

The current web draft is implemented at `/agrifabric`, smoke-tested by `web/smoke/agrifabric_landing_smoke.mjs`, and screenshot-assisted by `web/smoke/agrifabric_landing_capture_helper.mjs`.

## Geography source readiness

- `nwdp-village-boundary-source-readiness.md` — NWDP/GSI village boundary source-readiness note and claim boundaries.
- `nwdp-village-boundary-manifest-audit-runbook.md` — read-only manifest audit for NWDP/GSI village boundary resources.
- `nwdp-karnataka-village-boundary-pilot-audit-plan.md` — one-state pilot plan to test NWDP/GSI boundary attributes, geometry validity, and LGD crosswalk feasibility.
- `nwdp-karnataka-village-boundary-pilot-audit-runbook.md` — runbook for Karnataka GeoJSON attribute and LGD-crosswalk pilot audit.
- `nwdp-village-boundary-ingestion-crosswalk-plan.md` — conservative NWDP village-boundary ingestion, crosswalk, manual-review, and promotion design.
- `nwdp-karnataka-boundary-crosswalk-candidate-plan.md` — read-only Karnataka NWDP boundary crosswalk candidate counts, buckets, and review policy.
- `nwdp-boundary-manual-review-import-plan.md` — design for inactive/manual-review NWDP village-boundary candidate import and promotion gating.
- `nwdp-boundary-manual-review-import-plan.md` — conservative inactive/manual-review import plan and dry-run verifier for NWDP boundary crosswalk candidates.
- `nwdp-boundary-admin-review-ui-spec.md` — admin UI spec for inactive/manual-review NWDP boundary candidate batches and promotion gating.
