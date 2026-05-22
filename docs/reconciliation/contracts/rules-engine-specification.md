# Rules Engine Specification
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Depends on:** ADR-003 (Workflow Ownership Boundaries)  
**Purpose:** Centralize all decision logic that determines WHAT should happen in response to events.

---

## 1. Purpose & Boundaries

### What the Rules Engine Owns

The Rules Engine is the SINGLE location for business decision logic:

```yaml
rules_engine_owns:
  - notification_trigger_conditions (WHEN to notify)
  - escalation_logic (WHEN to escalate)
  - timeout_enforcement (WHEN to auto-transition)
  - advisory_routing (WHO receives which advisory)
  - campaign_targeting (WHO is in the audience)
  - anomaly_detection_thresholds (WHAT is abnormal)
  - SLA_enforcement (WHEN is a deadline breached)
  - workflow_automation (WHAT happens automatically after an event)
  - conflict_escalation (WHEN does a conflict need human review)
  - farmer_segmentation_rules (HOW to classify farmers)
```

### What the Rules Engine Does NOT Own

```yaml
rules_engine_does_not_own:
  - state_transitions (Workflow Engine validates these)
  - message_delivery (Notification Engine handles this)
  - data_aggregation (Analytics Module handles this)
  - conflict_resolution_strategy (Sync Engine + Conflict Matrix)
  - form_rendering (Dynamic Form Module)
  - authentication (Identity Module)
```

### Key Principle

> The Rules Engine DECIDES. Other modules EXECUTE.  
> The Rules Engine subscribes to events, evaluates conditions, and emits commands.

---

## 2. Architecture

### Event Flow

```
[Any Module] → publishes event → [Event Mediator]
                                       ↓
                              [Rules Engine] evaluates rules
                                       ↓
                              emits command(s):
                                - schedule_notification
                                - escalate_case
                                - trigger_recalculation
                                - flag_anomaly
                                - assign_expert
```

### Rules Engine is a Consumer, Not a Producer of Domain Events

The Rules Engine:
- SUBSCRIBES to domain events (crop_stage_completed, disease_reported, sync_conflict_detected)
- EVALUATES configured rules against event context
- EMITS commands to other modules (not domain events)

Commands are imperative ("send this notification", "escalate this case") — not facts.

---

## 3. Rule Structure

### Canonical Rule Format

```yaml
rule:
  rule_id: "RULE-001"
  name: "Fertilizer Reminder After Sowing"
  version: "1.0"
  tenant_configurable: true
  enabled: true

  trigger:
    event: stage_instance_completed
    conditions:
      - stage_definition.name == "SOWING"
      - crop_cycle.status == "ACTIVE"

  evaluation:
    check: no_input_log_of_type("FERTILIZER") within 10_days
    context_required:
      - farmer_id
      - crop_cycle_id
      - parcel_id

  action:
    type: schedule_notification
    parameters:
      template: "fertilizer_reminder"
      delay: 7_days
      channels: [PUSH, SMS]
      audience: [farmer, linked_dealer]
      priority: MEDIUM

  timeout:
    if_not_resolved_in: 14_days
    then: escalate_to_dealer

  audit:
    log_evaluation: true
    log_action: true
```

---

## 4. Rule Categories

### 4.1 Notification Trigger Rules

```yaml
notification_rules:

  RULE-001:
    name: fertilizer_reminder_after_sowing
    trigger: stage_instance_completed (SOWING)
    condition: no fertilizer log within 10 days
    action: schedule_notification(fertilizer_reminder, delay=7d)

  RULE-002:
    name: irrigation_reminder
    trigger: stage_instance_started (VEGETATIVE_GROWTH)
    condition: irrigation_type != RAINFED
    action: schedule_notification(irrigation_reminder, delay=3d, repeat=7d)

  RULE-003:
    name: harvest_reminder
    trigger: stage_instance_started (MATURITY)
    condition: expected_harvest_date within 7 days
    action: schedule_notification(harvest_approaching, delay=0)

  RULE-004:
    name: inactivity_alert
    trigger: scheduled (daily check)
    condition: farmer has active crop cycle AND no activity in 21 days
    action: notify_dealer(farmer_inactive, priority=HIGH)

  RULE-005:
    name: weather_alert
    trigger: environmental_event_reported (severity >= HIGH)
    condition: active crop cycles in affected village
    action: notify_all_farmers_in_village(weather_alert, priority=CRITICAL)
```

### 4.2 Escalation Rules

```yaml
escalation_rules:

  RULE-010:
    name: disease_review_timeout
    trigger: timer (24 hours after disease_reported)
    condition: disease_report.status == UNDER_REVIEW
    action: escalate(reassign_to_available_expert, notify_supervisor)

  RULE-011:
    name: advisory_response_timeout
    trigger: timer (48 hours after expert_assigned)
    condition: advisory not yet drafted
    action: escalate(notify_supervisor, reassign)

  RULE-012:
    name: sync_conflict_timeout
    trigger: timer (48 hours after conflict_detected)
    condition: conflict.status == CONFLICTED AND entity_type == PARCEL
    action: escalate(notify_admin, create_manual_review_task)

  RULE-013:
    name: farmer_acknowledgment_timeout
    trigger: timer (72 hours after advisory_published)
    condition: farmer has not acknowledged
    action: notify_dealer(follow_up_required, farmer_id, advisory_id)
```

### 4.3 SLA Enforcement Rules

```yaml
sla_rules:

  RULE-020:
    name: disease_advisory_sla
    trigger: disease_reported
    sla: advisory must be published within 24 hours
    breach_action: escalate + notify_enterprise_manager
    metric: advisory_response_time (KPI-008)

  RULE-021:
    name: sync_resolution_sla
    trigger: sync_conflict_detected
    sla: parcel conflicts resolved within 48 hours
    breach_action: escalate_to_admin + flag_in_dashboard

  RULE-022:
    name: field_visit_completion_sla
    trigger: field_visit_assigned
    sla: visit completed within assigned deadline
    breach_action: notify_supervisor + mark_expired
```

### 4.4 Anomaly Detection Rules

```yaml
anomaly_rules:

  RULE-030:
    name: impossible_stage_duration
    trigger: stage_instance_completed
    condition: stage_duration < 1_day OR stage_duration > 3x_average_for_crop
    action: flag_for_review(data_quality_alert)

  RULE-031:
    name: abnormal_cost
    trigger: input_log_confirmed
    condition: cost > 3x regional_average for input_type
    action: flag_for_review(cost_anomaly)

  RULE-032:
    name: duplicate_farmer_signal
    trigger: farmer_registered
    condition: mobile_number exists OR name_similarity > 0.85 in same village
    action: flag_for_review(potential_duplicate)

  RULE-033:
    name: suspicious_bulk_activity
    trigger: sync_completed
    condition: single_actor submitted > 50 records in < 1 hour
    action: flag_for_review(bulk_activity_alert)
```

### 4.5 Workflow Automation Rules

```yaml
automation_rules:

  RULE-040:
    name: auto_activate_farmer
    trigger: timer (14 days after VERIFICATION_PENDING)
    condition: no verification response received
    action: transition_farmer_to(ACTIVE) with flag(unverified)
    tenant_configurable: true

  RULE-041:
    name: auto_close_monitoring
    trigger: timer (14 days after disease_report.status == MONITORING)
    condition: no recurrence reported
    action: transition_disease_to(CLOSED)

  RULE-042:
    name: auto_archive_completed_cycle
    trigger: timer (30 days after crop_cycle.status == COMPLETED)
    action: transition_crop_cycle_to(ARCHIVED)
    tenant_configurable: true

  RULE-043:
    name: auto_correlate_environmental_event
    trigger: environmental_event_validated
    action: link_to_parcels_in_village + link_to_active_crop_cycles
```

---

## 5. Tenant Configuration

### What Tenants Can Customize

```yaml
tenant_configurable:
  - notification_timing (delay values, repeat intervals)
  - escalation_timeouts (hours before escalation)
  - anomaly_thresholds (what constitutes "abnormal")
  - SLA_values (hours/days for deadlines)
  - rule_enabled/disabled (turn rules on/off)
  - audience_targeting (who receives which notifications)
  - automation_timers (days before auto-transitions)
```

### What Tenants CANNOT Customize

```yaml
tenant_non_configurable:
  - rule_structure (IF/THEN logic pattern)
  - event_contracts (what events exist)
  - state_machine_transitions (what transitions are valid)
  - audit_requirements (always logged)
  - security_policies (always enforced)
  - canonical_terminology (always standard)
```

---

## 6. Rule Evaluation Engine

### Processing Model

```yaml
evaluation_model:
  trigger: event_received
  steps:
    1: identify_applicable_rules (by event type + tenant)
    2: load_context (farmer, parcel, crop_cycle, etc.)
    3: evaluate_conditions (all conditions must be true)
    4: execute_actions (in priority order)
    5: log_evaluation (audit trail)
    6: handle_failures (retry or DLQ)

  concurrency: rules for same event evaluated in parallel
  ordering: actions executed in priority order (CRITICAL > HIGH > MEDIUM > LOW)
  idempotency: same event + same rule = same outcome (no duplicate actions)
```

### Timer-Based Rules

```yaml
timer_rules:
  implementation: scheduled job checks timer conditions
  frequency: every 15 minutes (configurable)
  batch_size: 1000 entities per check
  performance: indexed queries on (status, updated_at, tenant_id)
```

---

## 7. Rule Versioning & Governance

```yaml
rule_governance:
  versioning: semantic (1.0, 1.1, 2.0)
  approval_required: true (for tenant-level changes)
  rollback_supported: true (revert to previous version)
  audit_trail: all rule changes logged with actor + timestamp
  testing: rules must pass validation before activation
  
  validation_checks:
    - rule_does_not_create_infinite_loop
    - rule_action_references_valid_template
    - rule_timeout_is_reasonable (>1 hour, <365 days)
    - rule_audience_is_resolvable
```

---

## 8. Integration Points

| Component | Rules Engine Interaction |
|-----------|------------------------|
| Workflow Engine | Rules Engine subscribes to state change events; may request transitions via Workflow Engine API |
| Notification Engine | Rules Engine emits `schedule_notification` commands; Notification Engine executes delivery |
| Analytics Module | Rules Engine emits `flag_anomaly` commands; Analytics excludes flagged data or recalculates |
| Sync Engine | Rules Engine subscribes to `sync_conflict_detected`; emits escalation commands |
| Disease Module | Rules Engine enforces SLA timers; emits reassignment/escalation commands |

---

## 9. MVP Rules (First Vertical Slice)

For the MVP vertical slice (ADR-005), implement ONLY:

```yaml
mvp_rules:
  - RULE-001 (fertilizer reminder)
  - RULE-003 (harvest reminder)
  - RULE-004 (inactivity alert)
  - RULE-005 (weather alert)
  - RULE-010 (disease review timeout)
  - RULE-013 (farmer acknowledgment timeout)
  - RULE-032 (duplicate farmer signal)
  - RULE-041 (auto-close monitoring)
```

All other rules deferred to post-MVP.

---

*End of Rules Engine Specification*
