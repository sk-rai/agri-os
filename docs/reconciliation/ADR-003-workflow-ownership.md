# ADR-003: Workflow Ownership Boundaries

**Status:** DECIDED  
**Date:** May 21, 2026  
**Depends on:** ADR-001, ADR-002

---

## Context

"Workflow Engine" is currently a god module affecting 7+ downstream modules. Business logic risks leaking into notification handlers, analytics processors, and sync engines. Clear ownership boundaries are needed.

## Decision

### Component Ownership Matrix

| Component | Owns | Does NOT Own |
|-----------|------|-------------|
| **Workflow Engine** | Valid state transitions, stage ordering, conditional branching, template configuration | Business rules about WHEN to transition, notification content, analytics calculations |
| **Rules Engine** | Decision policies, trigger conditions, escalation logic, SLA enforcement | State transitions, message delivery, data aggregation |
| **Notification Engine** | Message delivery, channel selection, retry, template rendering | When to notify (that's Rules Engine), workflow state |
| **Analytics Module** | Aggregation, KPI calculation, benchmarking, confidence scoring | Workflow transitions, notification delivery, sync operations |
| **Sync Engine** | State convergence, conflict detection, retry, dependency ordering | Workflow validation (delegates to Workflow Engine), notification |
| **Event Bus (Mediator)** | Event propagation, delivery guarantee, DLQ management | Business logic, state decisions, data transformation |

### Interaction Flow Example

```
Farmer completes crop stage (mobile, offline)
  → Sync Engine: queues for sync, manages dependencies
  → Sync Engine: uploads to server
  → Workflow Engine: validates transition (active → completed) ← AUTHORITATIVE
  → Workflow Engine: publishes event "crop_stage_completed"
  → Rules Engine: evaluates rules (is next reminder due? is SLA breached?)
  → Rules Engine: decides "send fertilizer reminder in 7 days"
  → Notification Engine: schedules and delivers notification
  → Analytics Module: updates stage duration metrics, recalculates KPIs
```

### Key Principle: Workflow Engine Validates, Rules Engine Decides, Others Execute

- **Workflow Engine** answers: "Is this transition VALID?"
- **Rules Engine** answers: "What SHOULD happen next?"
- **Notification Engine** answers: "HOW do I deliver this message?"
- **Analytics Module** answers: "What does this MEAN for metrics?"
- **Sync Engine** answers: "HOW do I get this data to the server safely?"

### Rules Engine Specification (New Component)

The Rules Engine is a new component that must be specified. It centralizes:

```yaml
rules_engine_responsibilities:
  - notification_trigger_conditions
  - escalation_timeout_logic
  - SLA_enforcement
  - advisory_routing_rules
  - campaign_targeting_logic
  - anomaly_detection_thresholds
  - workflow_automation_triggers
  - conflict_escalation_rules

rules_engine_does_not_own:
  - state_transitions (workflow engine)
  - message_delivery (notification engine)
  - data_aggregation (analytics)
  - conflict_resolution_strategy (sync engine + conflict matrix)
```

## Consequences

- Workflow Engine becomes smaller and more focused (validate transitions, publish events)
- Business logic centralizes in Rules Engine (easier to configure per tenant)
- Notification Engine becomes a pure delivery mechanism (no business logic)
- Analytics Module becomes a pure consumer (no side effects on other modules)
- Testing becomes modular (each component testable independently)

---

*End of ADR-003*
