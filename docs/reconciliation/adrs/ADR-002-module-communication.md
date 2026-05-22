# ADR-002: Module Communication Contract

**Status:** DECIDED  
**Date:** May 21, 2026  
**Depends on:** ADR-001 (Architecture Identity)

---

## Context

The Module Dependency Graph shows upstream/downstream relationships but never defines HOW modules communicate. Without this, developers will use ad-hoc patterns creating inconsistent coupling.

## Decision

All inter-module communication follows exactly two patterns:

### Pattern 1: Synchronous Query (Read)

Used when: Module A needs data owned by Module B.

```
Module A → calls → Module B's Query Interface → returns data
```

Rules:
- Module B exposes a **query interface** (Python abstract class / protocol)
- Module A depends on the interface, NOT the implementation
- Queries are read-only — they never mutate state
- Queries may be cached by the caller
- No direct database access across module boundaries

### Pattern 2: Asynchronous Event (Write/State Change)

Used when: Module A's state change needs to inform other modules.

```
Module A → publishes event → Mediator → delivers to subscribers
```

Rules:
- Events represent facts (past tense: `farmer_registered`, `crop_stage_completed`)
- Publishers don't know subscribers
- Subscribers handle events idempotently
- Events are persisted in outbox before dispatch
- Failed event handling goes to DLQ table

## Ownership Boundaries

| Module | Owns (Authoritative Writer) | Exposes Query Interface For |
|--------|---------------------------|---------------------------|
| Identity & Access | user, role, permission, session | user lookup, role check, territory resolution |
| Tenant Management | tenant, organization, settings | tenant config, branding |
| Geography Master | country, state, district, block, village | hierarchy lookup, village search |
| Farmer Management | farmer, farmer_profile | farmer lookup, segment query |
| Parcel Management | parcel, soil_profile, soil_health_card | parcel lookup, geometry query |
| Crop Master | crop, crop_variety, lifecycle_template | crop catalog, template lookup |
| Workflow Engine | stage_definition, stage_transition, stage_instance | state query, transition validation |
| Dynamic Form | form_schema, form_field, form_submission | schema resolution |
| Crop Activity | crop_cycle, crop_activity, cost_entry | activity history, cost query |
| Notification | notification, campaign, template | delivery status |
| Disease | disease_report, advisory | case status, outbreak query |
| Environmental Event | environmental_event | event history |
| Analytics | kpi_calculation, benchmark, analytics_snapshot | KPI query, benchmark query |
| Media Management | media_evidence | media URL resolution |
| Offline Sync | sync_queue, sync_event, conflict | sync status |
| Audit & Security | audit_event, security_policy | audit query |

## Forbidden Patterns

```yaml
forbidden:
  - direct_sql_across_module_boundaries
  - module_A_writing_to_module_B_tables
  - synchronous_calls_for_state_changes
  - circular_dependencies_between_modules
  - business_logic_in_event_handlers (handlers should delegate to owning module)
```

---

*End of ADR-002*
