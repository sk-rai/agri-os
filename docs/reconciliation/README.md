# Reconciliation Layer — Implementation Governance
# Agricultural Operations Intelligence Platform

**Created:** May 21, 2026  
**Purpose:** Resolve contradictions, freeze foundational decisions, define implementation reality.  
**Authority:** These documents supersede conflicting guidance in earlier specification documents.

---

## Document Index

### Architecture Decision Records (ADRs)

| # | Document | Status | Resolves |
|---|----------|--------|----------|
| ADR-001 | [Architecture Identity](ADR-001-architecture-identity.md) | DECIDED | Monolith vs distributed contradiction |
| ADR-002 | [Module Communication](ADR-002-module-communication.md) | DECIDED | Undefined inter-module patterns |
| ADR-003 | [Workflow Ownership](ADR-003-workflow-ownership.md) | DECIDED | God module, business logic leakage |
| ADR-004 | [Geography Hierarchy](ADR-004-geography-hierarchy.md) | DECIDED | Block/taluka inconsistency |
| ADR-005 | [MVP Vertical Slice](ADR-005-mvp-vertical-slice.md) | DECIDED | Scope definition, execution path |
| ADR-006 | [Retry & Timeout Policy](ADR-006-retry-timeout-policy.md) | DECIDED | Dead-ends, infinite loops, missing timeouts |
| ADR-007 | [Multi-Actor Conflict](ADR-007-multi-actor-conflict-resolution.md) | DECIDED | Competing transitions, offline conflicts |
| ADR-008 | [Analytics Freshness](ADR-008-analytics-freshness.md) | DECIDED | Eventual consistency vs accurate analytics |
| ADR-009 | [Temporal Truth Model](ADR-009-temporal-truth-model.md) | DECIDED | Time dimensions, supersession, trust scoring |

### Governance Documents

| Document | Status | Purpose |
|----------|--------|---------|
| [Canonical Semantic Registry v1](canonical-semantic-registry-v1.md) | FROZEN | All naming/terminology — implementation law |
| [Farmer Value Ladder](farmer-value-ladder.md) | DECIDED | Farmer adoption, value exchange model |
| [Complete State Machines](complete-state-machines.md) | DECIDED | All 14 operational workflow state models |
| [Rules Engine Specification](rules-engine-specification.md) | DECIDED | Centralized business decision logic |
| [Feature-Phone Interaction Design](feature-phone-interaction-design.md) | DECIDED | SMS/voice interaction for non-smartphone users |
| [Configuration Governance Model](configuration-governance-model.md) | DECIDED | Tenant customization rules, inheritance, change workflow |
| [MVP API Contract](mvp-api-contract.md) | DECIDED | OpenAPI endpoint definitions for vertical slice |
| [Mobile Offline Schema](mobile-offline-schema.md) | DECIDED | SQLite/Drift tables, sync queue, indexes |
| [Sync Engine Contract](sync-engine-contract.md) | DECIDED | Queue processing, retry, conflict routing, background execution, resolution UI |
| [Offline Validation Rules](offline-validation-rules.md) | DECIDED | Client-side validation before sync, rural UX error messages, duplicate detection |
| [Screen Information Architecture](screen-information-architecture.md) | DECIDED | Detail screen structure, role-based field visibility, empty states |
| [Media Upload Pipeline](media-upload-pipeline.md) | DECIDED | Image compression, metadata, dedup, priority queue, storage lifecycle |
| [Security & Audit Framework](security-audit-framework.md) | DECIDED | JWT scopes, PII handling, audit immutability, media access, pen-test checklist |
| [Testing Strategy](testing-strategy.md) | DECIDED | Test pyramid, chaos scenarios, rural UX protocol, CI/CD gates, go/no-go criteria |
| [Deployment & Infrastructure](deployment-infrastructure.md) | DECIDED | Environments, promotion rules, backup/DR, monitoring, change management |
| [Master Data & Caching](master-data-caching.md) | DECIDED | Offline cache hierarchy, delta sync, TTL, eviction, tenant isolation, fallback |
| [Enterprise Dashboard Contract](enterprise-dashboard-contract.md) | DECIDED | Widget rendering, KPI display, geospatial views, export specs, caching |
| [API Versioning & Webhooks](api-versioning-webhooks.md) | DECIDED | Full endpoint catalog, versioning strategy, backward compat, deprecation, webhooks |
| [Go-Live & Operations Playbook](go-live-operations-playbook.md) | DECIDED | Tenant provisioning, incident response, SLAs, on-call, escalation, launch runbook |

### Analysis Documents

| Document | Purpose |
|----------|---------|
| [AI-1 Additional Insights](ai1-additional-insights.md) | Correlation with second AI review, gap analysis |

---

## What These Documents Mean

### For Developers
- The Canonical Semantic Registry is **law**. Use these names in code, APIs, schemas, events.
- ADR-001 means: build ONE deployable, use in-process events, no Kafka in Phase 1.
- ADR-002 means: never access another module's database tables directly.
- ADR-005 means: build THIS slice first, nothing else until it works end-to-end.

### For Product
- The Farmer Value Ladder defines what farmers get at each level. Design UX accordingly.
- ADR-005 defines MVP scope. Everything not in the slice is deferred.

### For Architecture
- ADR-003 defines who owns what. Workflow Engine validates; Rules Engine decides; others execute.
- ADR-006 means every state machine needs timeouts and terminal exits. No exceptions.
- ADR-007 defines how offline conflicts are resolved. Farmer work is never silently discarded.

---

## Remaining Work (Week 3+)

| Deliverable | Status | Priority |
|-------------|--------|----------|
| Complete state machines for Enrollment, Parcel, Field Visit, OCR | ✅ DONE | P0 |
| Rules Engine Specification | ✅ DONE | P1 |
| Feature-Phone Interaction Design | ✅ DONE | P1 |
| Configuration Governance Model | ✅ DONE | P1 |
| Temporal Truth Model (ADR-009) | ✅ DONE | P1 |
| MVP API Contracts (OpenAPI) | ✅ DONE | P1 |
| Mobile SQLite Schema | ✅ DONE | P1 |
| Consent & Data Rights Design | PARTIAL (consent in feature-phone doc) | P1 |
| Dealer Incentive Model (detailed) | PARTIAL (in farmer value ladder) | P1 |
| CI/CD Semantic Validator Script | TODO — adopt from AI-1 | P2 |
| Chaos Test Strategy | TODO — adopt from AI-1 | P2 |
| Sprint Task Breakdown | TODO — adopt from AI-1 | P2 |
| Sync Storm Throttling Strategy | TODO | P2 |
| Disaster Recovery Procedures | TODO | P2 |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-21 | Modular monolith for Phase 1 | Small team, operational simplicity, retain event contracts for future extraction |
| 2026-05-21 | Include block/taluka in geography | Required for Indian administrative operations, extension services, weather data |
| 2026-05-21 | `disease_report` is canonical (not `disease_case`) | 4 of 5 documents already use it |
| 2026-05-21 | All enums SCREAMING_SNAKE_CASE | Data Dictionary convention, enforced universally |
| 2026-05-21 | GPS polygon is optional for MVP | Single pin + area is sufficient; polygon is Level 3 enhancement |
| 2026-05-21 | Farmer registration in 60 seconds (3 fields) | Value ladder Level 1 requires minimal friction |
| 2026-05-21 | One-tap stage completion for farmers | Detailed forms are agent-facing, not farmer-facing |
| 2026-05-21 | Farmer work never silently discarded | Even invalid transitions are preserved and user is notified |

---

*End of Reconciliation README*
