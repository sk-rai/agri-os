# ADR-007: Multi-Actor Conflict Resolution for Workflow Transitions

**Status:** DECIDED  
**Date:** May 21, 2026  
**Resolves:** Pass 1 C2, C7; Pass 3 C3 (competing valid transitions, assisted-digital conflicts)

---

## Context

Multiple actors can make conflicting but individually valid transitions on the same entity while offline. The current conflict resolution matrix handles data conflicts but not workflow transition conflicts.

## Decision

### Actor Priority Hierarchy

When two actors make conflicting transitions on the same entity:

```yaml
actor_priority:
  1_highest: system_automated  # timeout escalations, SLA enforcement
  2: agronomist               # expert authority on crop/disease state
  3: field_agent              # verification authority
  4: dealer                   # operational authority
  5_lowest: farmer            # self-reported (may be overridden by verification)
```

### Conflict Scenarios and Resolution

| Scenario | Actor A | Actor B | Resolution |
|----------|---------|---------|------------|
| Both complete same stage | Farmer | Field Agent | Merge: accept completion, use field_agent metadata (verified) |
| One completes, other fails | Farmer (completed) | Field Agent (failed) | Escalate to manual review — disagreement on outcome |
| One completes, other skips | Farmer (completed) | Agronomist (skipped) | Agronomist wins (higher priority) — notify farmer |
| Both create same farmer | Dealer A | Dealer B | First-sync-wins for creation; merge profiles if duplicate detected |
| Both edit parcel boundary | Dealer | Field Agent | Manual review (parcel geometry is always manual_review) |
| Stage completed offline, server already advanced | Farmer (offline) | Field Agent (online) | Per-transition validation: if farmer's transition is still valid against current server state, accept. If invalid, notify farmer of conflict. |

### Workflow Rebase Strategy

When a device syncs after extended offline period and local transitions conflict with server state:

```yaml
workflow_rebase:

  step_1_validate_each_transition:
    - check each local transition against CURRENT server state
    - not against the state when the device went offline

  step_2_classify_conflicts:
    valid_transitions: accept and apply
    invalid_but_recoverable: rebase to current state, notify user
    invalid_and_irrecoverable: reject, preserve in conflict queue, notify user

  step_3_handle_dependent_data:
    activities_logged_against_invalid_stages:
      - preserve activities (never discard farmer work)
      - re-link to correct stage if possible
      - flag as "stage_context_uncertain" if not

  step_4_notify:
    - always notify the affected user of any rejected transitions
    - provide clear explanation: "Field agent already completed this stage on [date]"
    - offer recovery action: "Your observations have been saved. Tap to review."
```

### Territory-Based Conflict Prevention

To reduce conflicts at the source:

```yaml
territory_rules:
  - each_village_has_primary_dealer (exclusive enrollment rights)
  - field_agents_assigned_to_non_overlapping_blocks
  - enrollment_conflicts_resolved_by_territory_assignment
  - territory_reassignment_triggers_handoff_workflow
```

---

## Consequences

- Farmer work is NEVER silently discarded (preserved even if transition is rejected)
- Higher-authority actors can override lower-authority actors (with audit trail)
- Parcel geometry conflicts ALWAYS go to manual review (never auto-resolved)
- Territory assignment prevents most conflicts at the source
- Users are always notified of conflict resolution outcomes

---

*End of ADR-007*
