# Reconciliation: Governed Implementation Architecture

**Status:** COMPLETE — Ready for Engineering  
**Date:** May 22, 2026  
**Purpose:** Authoritative implementation baseline for Agri-OS

---

## Directory Structure

```
docs/
├── reconciliation/          ← GOVERNANCE (authoritative decisions)
│   ├── adrs/                ← Architecture Decision Records
│   ├── contracts/           ← Behavioral contracts & specifications
│   ├── operations/          ← Operational governance (deploy, test, security)
│   └── README.md            ← This file
│
└── sources/                 ← RAW INPUT (reference material, not authoritative)
    ├── ai-1/               ← Original AI-1 documents (provenance)
    └── reviews/            ← 4-pass architecture review reports
```

---

## ADRs (Architecture Decision Records)

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](adrs/ADR-001-architecture-identity.md) | Modular monolith + in-process events (Kafka deferred) | ACCEPTED |
| [ADR-002](adrs/ADR-002-module-communication.md) | Sync queries via interfaces, async via mediator | ACCEPTED |
| [ADR-003](adrs/ADR-003-workflow-ownership.md) | Workflow validates, Rules decides, Notification delivers | ACCEPTED |
| [ADR-004](adrs/ADR-004-geography-hierarchy.md) | State → District → Block → Village (block included) | ACCEPTED |
| [ADR-005](adrs/ADR-005-mvp-vertical-slice.md) | "Farmer registers, grows crop, gets advisory" | ACCEPTED |
| [ADR-006](adrs/ADR-006-retry-timeout-policy.md) | Exponential backoff, max 10, then dead_letter | ACCEPTED |
| [ADR-007](adrs/ADR-007-multi-actor-conflict-resolution.md) | Actor priority hierarchy + workflow rebase | ACCEPTED |
| [ADR-008](adrs/ADR-008-analytics-freshness.md) | Confidence scoring on all KPIs | ACCEPTED |
| [ADR-009](adrs/ADR-009-temporal-truth-model.md) | 4 time dimensions (valid, observation, transaction, processing) | ACCEPTED |
| [Semantic Registry](adrs/canonical-semantic-registry-v1.md) | FROZEN terminology — entity names, enums, events, units | FROZEN |
| [Farmer Value Ladder](adrs/farmer-value-ladder.md) | 5-level participation model | ACCEPTED |

---

## Contracts (Behavioral Specifications)

| Document | Scope |
|----------|-------|
| [Complete State Machines](contracts/complete-state-machines.md) | 14 workflow state machines |
| [Rules Engine](contracts/rules-engine-specification.md) | 43 named rules, 5 categories |
| [Sync Engine](contracts/sync-engine-contract.md) | Retry, dependency, conflict, UI, post-resolution |
| [MVP API Contract](contracts/mvp-api-contract.md) | OpenAPI endpoints for vertical slice |
| [API Versioning & Webhooks](contracts/api-versioning-webhooks.md) | Versioning, deprecation, webhook delivery |
| [Mobile Offline Schema](contracts/mobile-offline-schema.md) | SQLite tables, sync queue, cache |
| [Master Data Caching](contracts/master-data-caching.md) | TTLs, delta sync, fallback, eviction |
| [Enterprise Dashboard](contracts/enterprise-dashboard-contract.md) | Widgets, KPIs, exports, geospatial |
| [Media Upload Pipeline](contracts/media-upload-pipeline.md) | Compression, dedup, priority, lifecycle |
| [Feature-Phone Interaction](contracts/feature-phone-interaction-design.md) | SMS, IVR, missed-call, dealer relay |
| [Screen Information Architecture](contracts/screen-information-architecture.md) | Mobile screen structure, role visibility |
| [Offline Validation Rules](contracts/offline-validation-rules.md) | Client-side validation, error UX, GPS gates |
| [Master Data Implementation](contracts/master-data-implementation-plan.md) | Tables, sources, acquisition, pilot |

---

## Operations (Deployment, Testing, Security)

| Document | Scope |
|----------|-------|
| [Deployment & Infrastructure](operations/deployment-infrastructure.md) | Environments, containers, DR, monitoring |
| [Testing Strategy](operations/testing-strategy.md) | Pyramid, chaos, rural UX, CI/CD gates |
| [Security & Audit](operations/security-audit-framework.md) | JWT, PII, audit log, pen-test |
| [Configuration Governance](operations/configuration-governance-model.md) | Tenant customization boundaries |
| [Go-Live Playbook](operations/go-live-operations-playbook.md) | Provisioning, SLAs, incident response |

---

## Source Material

| Folder | Content | Purpose |
|--------|---------|---------|
| [sources/ai-1/](../sources/ai-1/) | Original AI-1 implementation documents | Provenance & re-extraction |
| [sources/reviews/](../sources/reviews/) | 4-pass architecture review reports | Finding history |

---

## Key Principle

> **Reconciliation docs are AUTHORITATIVE.**  
> Source docs are REFERENCE ONLY.  
> If there's a conflict, reconciliation wins.
