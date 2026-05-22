# Configuration Governance Model
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** Gap identified in AI-1 correlation analysis  
**Purpose:** Define what tenants can customize, inheritance rules, change governance, and platform invariants.

---

## 1. Configuration Hierarchy (Inheritance Model)

```
Platform Defaults (IMMUTABLE — code-level constants)
└─> Tenant Overrides (tenant_admin with approval)
    └─> Project/Program Overrides (program_manager)
        └─> Geography Overrides (territory_manager)
```

**Inheritance rule:** Lower levels inherit from higher. Overrides apply only to the specified scope. Unset values cascade from parent.

---

## 2. Configurability Matrix

| Configuration Area | Platform Default | Tenant Override | Project Override | Geography Override | Validation Rule |
|-------------------|-----------------|----------------|-----------------|-------------------|-----------------|
| lifecycle_template.stages | Canonical crop stages | ✅ Add optional stages, reorder | ✅ Per-project variant | ❌ | Must include all REQUIRED stages |
| notification.thresholds | Fertilizer reminder: 10 days | ✅ 7-14 days | ✅ Per-crop variant | ✅ Per-region | Integer 1-30 |
| notification.channels | PUSH + SMS | ✅ Enable/disable channels | ❌ | ❌ | At least 1 channel active |
| analytics.kpi_formulas | yield_per_hectare = harvest/area | ✅ Add normalization factors ONLY | ❌ | ❌ | Formula structure immutable |
| parcel.validation_rules | Min area: 0.1 ha, Max overlap: 5% | ✅ Adjust thresholds | ❌ | ✅ Regional thresholds | Must preserve geospatial integrity |
| sync.retry_policy | Max retries: 10, Backoff: exponential | ✅ Adjust counts/intervals | ❌ | ❌ | Must include DLQ handling |
| disease.escalation_sla | 24 hours to advisory | ✅ 12-48 hours | ✅ Per-severity | ❌ | Must be > 0 |
| forms.field_visibility | All fields visible | ✅ Hide optional fields | ✅ Per-stage | ✅ Per-region | Cannot hide REQUIRED fields |
| forms.mandatory_fields | Platform-defined required set | ✅ Add mandatory fields | ✅ Per-stage | ❌ | Cannot remove platform-required |
| dashboard.widgets | Standard widget set | ✅ Enable/disable, reorder | ❌ | ❌ | At least 1 widget active |
| branding | Platform default | ✅ Logo, colors, theme | ❌ | ❌ | Must meet contrast ratio |
| assistance_mode.behavior | All modes available | ✅ Restrict available modes | ❌ | ❌ | Must preserve audit attribution |

---

## 3. Platform Invariants (NEVER Overridable)

```yaml
platform_invariants:
  - tenant_isolation_enforced
  - audit_logging_for_critical_mutations
  - actor_attribution_on_all_writes
  - parcel_geometry_is_authoritative
  - workflow_state_machine_validation
  - canonical_entity_names (Semantic Registry v1)
  - canonical_units (hectare, kg, INR)
  - sync_conflict_detection_for_critical_entities
  - DPDPA_consent_requirements
  - max_retry_with_DLQ (no infinite loops)
  - event_immutability
  - offline_operation_support
```

---

## 4. Configuration Change Workflow

```yaml
change_workflow:

  step_1_draft:
    actor: tenant_admin or authorized role
    action: create configuration change request
    validation: schema validation only (syntactically correct)
    status: DRAFT

  step_2_review:
    actor: platform governance (automated + human)
    checks:
      - does_not_violate_platform_invariants
      - does_not_break_backward_compatibility
      - does_not_conflict_with_other_tenant_configs
      - passes_semantic_registry_validation
    status: REVIEW_PENDING

  step_3_approval:
    actor: platform_architect or designated approver
    action: approve or reject with reason
    status: APPROVED or REJECTED

  step_4_activation:
    deployment: immediate for non-breaking, scheduled for breaking
    propagation: server-side immediate, mobile devices on next sync
    monitoring: error_rate tracked for 24 hours post-activation
    rollback: automatic if error_rate > 1% (configurable threshold)

  step_5_audit:
    logged: changed_by, timestamp, before_value, after_value, tenant_id, approval_id
```

---

## 5. Configuration Propagation to Offline Devices

```yaml
offline_propagation:

  mechanism: configuration included in master_data_sync
  versioning: each config has version number
  staleness_handling:
    - device checks config_version on each sync
    - if server_version > device_version: download new config
    - if device has stale config: operations continue with local config
    - stale config never blocks farmer operations

  conflict_handling:
    - config changes are server-authoritative (no device-side config editing)
    - device always accepts server config on sync

  max_acceptable_staleness: 7 days (after which, force config refresh on next connectivity)
```

---

## 6. Tenant Onboarding Configuration

When a new tenant is created:

```yaml
tenant_onboarding:
  step_1: copy platform_defaults as tenant baseline
  step_2: apply tenant-specific overrides (from onboarding questionnaire)
  step_3: validate against platform_invariants
  step_4: activate tenant configuration
  step_5: propagate to all tenant devices on first sync

  minimum_configuration_required:
    - tenant_name
    - primary_crop_types (for lifecycle template selection)
    - geography_scope (which states/districts)
    - notification_channels (which channels enabled)
    - branding (logo, colors)
```

---

## 7. Configuration Versioning

```yaml
versioning:
  strategy: semantic (major.minor.patch)
  major: breaking change (requires device update)
  minor: new optional feature (backward compatible)
  patch: threshold adjustment (no structural change)

  history:
    - all versions preserved indefinitely
    - rollback to any previous version supported
    - analytics can query "what was the config at time T?"

  deprecation:
    - deprecated configs remain active for 90 days
    - warning shown in admin dashboard
    - auto-deactivated after deprecation period
```

---

*End of Configuration Governance Model*
