# ADR-001: Architecture Identity — Modular Monolith with Internal Event Contracts

**Status:** DECIDED  
**Date:** May 21, 2026  
**Deciders:** Platform Architecture Team  
**Supersedes:** Conflicting guidance in Technical Architecture Blueprint §2.2 and Event Bus Contract Registry §13

---

## Context

The documentation set contains a fundamental contradiction:
- Technical Architecture Blueprint recommends "modular monolith" for simplicity
- Event Bus Contract Registry specifies Kafka/Redpanda/Schema Registry infrastructure

This creates confusion about what developers should actually build.

## Decision

**Phase 1 (MVP): Modular Monolith with In-Process Event Dispatch**

The platform will be built as a single deployable application with:
- Logically separated modules (Python packages with defined interfaces)
- In-process event dispatch (Python mediator pattern, e.g., `pymediator` or custom)
- Same event contracts as defined in Event Bus Contract Registry
- Transactional outbox pattern for events that need durability
- Single PostgreSQL database with schema-level module separation

**Phase 2 (Post-MVP, when needed): Selective Service Extraction**

When specific modules need independent scaling:
- Extract to separate services using the SAME event contracts
- Introduce message broker (RabbitMQ initially, Kafka if volume demands)
- Schema Registry only when multiple teams produce/consume events independently

## Consequences

### What This Means for Development

| Concern | Phase 1 Implementation |
|---------|----------------------|
| Module communication (queries) | Direct function calls via defined interfaces |
| Module communication (commands) | In-process mediator dispatching events |
| Event persistence | Transactional outbox table in PostgreSQL |
| Event delivery guarantee | At-least-once via outbox polling |
| Schema validation | Python dataclass/Pydantic validation at publish time |
| Dead Letter Queue | Database table for failed event processing |
| Consumer registration | Decorator-based subscription in code |

### What This Means for the Event Bus Contract Registry

The Event Bus Contract Registry remains **valid and authoritative** for:
- Event names and semantics
- Payload schemas
- Producer/consumer relationships
- Ordering guarantees (within entity streams)
- Idempotency requirements

The following are **deferred to Phase 2**:
- Kafka/Redpanda infrastructure
- Confluent Schema Registry
- Physical topic partitioning
- Distributed DLQ infrastructure

### Migration Path to Phase 2

Extraction triggers (any ONE of these):
- Single module needs independent scaling (>80% of compute)
- Team size exceeds 8 engineers (coordination overhead)
- Deployment frequency diverges between modules
- Regulatory requirement for service isolation

Extraction process:
1. Module already communicates via events (no code change needed)
2. Replace in-process mediator with broker subscription
3. Outbox polling replaced by broker-native publishing
4. Add Schema Registry for cross-service contract validation

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Full distributed from day 1 | Operational overhead for small team; Kafka cluster management is a full-time job |
| No event contracts at all | Makes future extraction impossible; loses audit/tracing benefits |
| Microservices with HTTP | Synchronous coupling; no event replay; harder to debug |

## Implications for Other Documents

| Document | Required Update |
|----------|----------------|
| Event Bus Contract Registry | Add "Implementation Phase" column (Phase 1: in-process, Phase 2: broker) |
| Technical Architecture Blueprint | Remove ambiguity — state "modular monolith" definitively |
| Module Dependency Graph | Add "communication pattern" to each module (sync query vs async event) |
| Notification Engine Design | Replace RabbitMQ/Celery references with "queue infrastructure (in-process for Phase 1)" |

---

## Implementation Constraints

```yaml
phase_1_constraints:
  - all_modules_in_single_deployable
  - no_external_message_broker
  - events_dispatched_in_process
  - event_contracts_identical_to_registry
  - transactional_outbox_for_durability
  - single_postgresql_instance
  - schema_separation_per_module
  - no_direct_cross_module_table_access
  - interfaces_defined_per_module_boundary
```

---

*End of ADR-001*
