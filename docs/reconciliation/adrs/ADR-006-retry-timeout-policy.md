# ADR-006: Unified Retry, Timeout, and Terminal State Policy

**Status:** DECIDED  
**Date:** May 21, 2026  
**Resolves:** Pass 3 findings C1, C4, C5, H2 (dead-end states, infinite loops, missing timeouts)

---

## Context

Multiple state machines have infinite retry loops, dead-end states, and no timeout handling. This ADR standardizes retry/timeout behavior across ALL workflows.

## Decision

### Universal Retry Policy

```yaml
universal_retry_policy:

  strategy: exponential_backoff
  initial_interval: 30_seconds
  max_interval: 24_hours
  multiplier: 2
  max_retries: 10  # configurable per entity type
  jitter: true

  after_max_retries:
    transition_to: DEAD_LETTER
    action: alert_monitoring + user_visibility

  user_visibility:
    after_3_retries: show_warning_to_user
    after_max_retries: show_action_required

  audit:
    log_every_retry: true
    include: [entity_id, retry_count, failure_reason, timestamp]
```

### Universal Timeout Policy

Every non-terminal state MUST have a timeout. No state may remain indefinitely without progression.

```yaml
timeout_defaults:

  disease_workflow:
    under_review: 24_hours → escalated
    expert_assigned: 48_hours → escalated
    monitoring: 14_days → closed

  notification:
    scheduled: campaign_end_date → expired
    retry_pending: 72_hours → expired
    partially_delivered: 24_hours → retry_failed_channels OR expired

  sync:
    queued_for_sync: 7_days → alert_user
    failed: after_max_retries → dead_letter
    conflicted: 48_hours → escalate_to_manual_review

  crop_cycle:
    active: 365_days_without_update → partially_tracked
    partially_tracked: 90_days_without_update → abandoned

  analytics:
    processing: 1_hour → failed
    completed: stale_when_new_source_data_arrives → requeued
```

### Dead-End State Fixes

| State Machine | Dead-End Fixed | New Transition Added |
|---------------|---------------|---------------------|
| Notification | `partially_delivered` | → `sending` (retry) OR → `expired` (timeout) |
| Sync | `failed` infinite loop | → `dead_letter` (after max retries) |
| Crop Stage | `failed` no terminal | → `active` (with approval) OR → `cancelled` (parent abandoned) |

### Cascade Rules on Abandonment

```yaml
crop_cycle_abandoned_cascade:
  stage_instances:
    PENDING: → CANCELLED
    ACTIVE: → ABANDONED
    COMPLETED: unchanged
    SKIPPED: unchanged
  notifications:
    scheduled_for_this_cycle: → CANCELLED
  disease_reports:
    linked_to_this_cycle: unchanged (independent lifecycle)
  analytics:
    exclude_from_yield_averages: true
    include_in_abandonment_rate: true
```

---

## Implementation Constraint

```yaml
implementation_rule:
  - every_state_machine_must_define_timeout_for_every_non_terminal_state
  - every_retry_loop_must_have_max_retries_with_terminal_exit
  - every_terminal_state_must_be_explicitly_marked
  - cascade_behavior_must_be_defined_for_parent_state_changes
```

---

*End of ADR-006*
