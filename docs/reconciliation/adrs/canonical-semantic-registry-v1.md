# Canonical Semantic Registry v1
# Agricultural Operations Intelligence Platform

**Status:** FROZEN (v1.0)  
**Date:** May 21, 2026  
**Authority:** This document is the SINGLE source of truth for all naming decisions.  
**Rule:** No code, API, database schema, event, or document may use terms that contradict this registry.

---

## 1. Entity Names (Canonical)

All entities use `snake_case_singular` in code/schema. Tables use `snake_case_plural`.

| Canonical Name | Definition | Deprecated Aliases (DO NOT USE) |
|---------------|------------|-------------------------------|
| `farmer` | Human agricultural operator | cultivator, grower, producer |
| `parcel` | Geospatially bounded agricultural land unit | field, plot, khet |
| `crop_cycle` | Complete cultivation lifecycle for a crop on a specific parcel | crop_record, cultivation |
| `stage_definition` | Template-level configurable stage within a lifecycle template | crop_stage (ambiguous), workflow_stage (in config context) |
| `stage_instance` | Runtime occurrence of a stage within a crop cycle | active_stage, current_stage |
| `lifecycle_template` | Configurable template defining crop stages and transitions | workflow_template, crop_template |
| `disease_report` | Recorded crop disease/anomaly observation | disease_case (deprecated) |
| `advisory` | Expert recommendation issued to farmers | guidance, recommendation |
| `manufacturer` | Producer of agricultural inputs (seeds, fertilizers, pesticides) | seed_company, input_company |
| `crop_category` | Classification grouping for crops | crop_segment (deprecated) |
| `agricultural_input` | Material applied during cultivation (seed, fertilizer, pesticide) | input (ambiguous), product |
| `environmental_event` | Recorded weather/environmental observation | weather_event, climate_event |
| `campaign` | Targeted communication initiative | broadcast |
| `notification` | Delivery of a message through a channel | alert, message |
| `tenant` | Top-level platform customer (isolation boundary) | client, customer |
| `organization` | Operational unit within a tenant | company, enterprise (in org context) |
| `territory` | Assigned geographic operational area (collection of blocks/villages) | area, zone, region |
| `field_visit` | Structured field operation by agent/agronomist | site_visit, farm_visit |
| `benchmark_group` | Cohort definition for comparative analytics | comparison_group |
| `sync_queue` | Persistent queue of offline operations pending sync | upload_queue |
| `audit_event` | Recorded system action for traceability | audit_log, activity_log |

---

## 2. Workflow/Process Names (Canonical)

| Canonical Name | Type | Deprecated Aliases |
|---------------|------|-------------------|
| `farmer_enrollment` | Business Process | farmer_onboarding, registration |
| `parcel_mapping` | Business Process | farm_mapping, field_mapping |
| `crop_registration` | Business Process | crop_creation |
| `crop_lifecycle` | Business Process | crop_workflow, crop_progression |
| `input_logging` | Business Process | input_application, input_tracking |
| `disease_reporting` | Business Process | disease_escalation |
| `advisory_workflow` | Business Process | expert_review |
| `notification_delivery` | Pipeline | notification_workflow |
| `offline_sync` | Pipeline | synchronization, data_sync |
| `media_processing` | Pipeline | image_processing, upload_pipeline |
| `analytics_processing` | Pipeline | analytics_workflow, KPI_calculation |

---

## 3. State Names (Canonical)

### Crop Cycle States
```
PLANNED → ACTIVE → COMPLETED → ARCHIVED
                 → PARTIALLY_TRACKED → COMPLETED
                 → ABANDONED → ARCHIVED
```

### Stage Instance States
```
PENDING → ACTIVE → COMPLETED
                 → PARTIALLY_COMPLETED → COMPLETED
                 → FAILED → ACTIVE (with approval)
       → SKIPPED
       → CANCELLED (parent abandoned)
```

### All enumerations use SCREAMING_SNAKE_CASE.

---

## 4. Event Names (Canonical)

Convention: `entity_past_tense_verb`

| Event Name | Producer | Meaning |
|-----------|----------|---------|
| `farmer_registered` | farmer_management | New farmer created |
| `farmer_profile_updated` | farmer_management | Farmer details changed |
| `parcel_created` | parcel_management | New parcel mapped |
| `parcel_boundary_updated` | parcel_management | Geometry changed |
| `crop_cycle_started` | workflow_engine | Crop cycle activated |
| `crop_cycle_completed` | workflow_engine | Crop cycle finished |
| `crop_cycle_abandoned` | workflow_engine | Crop cycle discontinued |
| `stage_instance_started` | workflow_engine | Stage activated |
| `stage_instance_completed` | workflow_engine | Stage finished |
| `stage_instance_skipped` | workflow_engine | Stage bypassed |
| `stage_instance_failed` | workflow_engine | Stage failed |
| `disease_reported` | disease_module | New disease observation |
| `advisory_issued` | disease_module | Expert advisory created |
| `notification_queued` | notification_engine | Notification scheduled |
| `notification_delivered` | notification_engine | Notification confirmed |
| `notification_failed` | notification_engine | Delivery failed |
| `sync_completed` | sync_engine | Device sync successful |
| `sync_conflict_detected` | sync_engine | Conflict found during sync |
| `conflict_resolved` | sync_engine | Conflict resolution applied |

---

## 5. Geography Hierarchy (Canonical)

```
country → state → district → block → village → parcel
```

`block` aliases: taluka, tehsil, mandal (display only)

---

## 6. Unit Standards (Canonical)

| Measurement | Canonical Storage Unit | Display Conversions Allowed |
|-------------|----------------------|---------------------------|
| Land area | hectare | acre, bigha, guntha, kanal |
| Weight | kilogram | quintal, metric_ton |
| Currency | INR (paisa precision) | localized formatting |
| Rainfall | millimeter | — |
| Temperature | celsius | — |
| Distance | meter | kilometer |
| Time duration | seconds (stored), displayed as appropriate | hours, days |
| NDVI | dimensionless ratio (-1 to +1) | — |

---

## 7. Enum Standards (Canonical)

All enums: SCREAMING_SNAKE_CASE. Stored as strings, not integers.

### Ownership Types
```
OWNED | LEASED | SHARED | CONTRACT | UNKNOWN
```

### Irrigation Types
```
RAINFED | TUBEWELL | CANAL | DRIP | SPRINKLER | FLOOD | MIXED
```

### Disease Severity
```
LOW | MEDIUM | HIGH | CRITICAL
```

### Environmental Event Types
```
RAINFALL | HAILSTORM | FLOOD | DROUGHT | HIGH_WINDS | HEAT_STRESS | FROST
```

### Assistance Modes
```
SELF_MANAGED | DEALER_ASSISTED | FIELD_AGENT_ASSISTED | HYBRID
```

### Notification Channels
```
PUSH | SMS | IN_APP | EMAIL | WHATSAPP | IVR
```

### Sync States
```
LOCAL_ONLY | QUEUED | SYNCING | SYNCED | PARTIALLY_SYNCED | CONFLICTED | FAILED | DEAD_LETTER
```

---

## 8. API Naming Standards

| Context | Convention | Example |
|---------|-----------|---------|
| Endpoints | kebab-case plural | `/crop-cycles`, `/disease-reports` |
| JSON fields | camelCase | `cropCycleId`, `stageInstanceId` |
| Query params | camelCase | `?farmerId=...&villageId=...` |
| Enums in JSON | SCREAMING_SNAKE_CASE | `"irrigationType": "DRIP"` |
| Event names | snake_case_past_tense | `crop_cycle_completed` |
| Database columns | snake_case | `farmer_id`, `created_at` |
| Database tables | snake_case_plural | `crop_cycles`, `stage_instances` |

---

## 9. KPI Identifiers (Canonical)

| KPI ID | Canonical Name | Unit | Category |
|--------|---------------|------|----------|
| `KPI-001` | yield_per_hectare | kg/hectare | crop_performance |
| `KPI-002` | cost_of_cultivation | INR | financial |
| `KPI-003` | net_profit | INR | financial |
| `KPI-004` | profit_margin | percentage | financial |
| `KPI-005` | fertilizer_usage_intensity | kg/hectare | input_efficiency |
| `KPI-006` | irrigation_frequency | events/day | input_efficiency |
| `KPI-007` | disease_incidence_rate | percentage | crop_health |
| `KPI-008` | advisory_response_time | hours | operational |
| `KPI-009` | notification_delivery_rate | percentage | operational |
| `KPI-010` | sync_success_rate | percentage | reliability |
| `KPI-011` | ndvi_vegetation_consistency | percentage | satellite |
| `KPI-012` | fraud_risk_score | normalized_score | insurance |

All configurable KPIs MUST reference a canonical KPI ID. Tenant customization is limited to normalization factors, NOT formula structure.

---

## 10. Enforcement Rules

```yaml
enforcement:
  - code_reviews_must_validate_canonical_names
  - database_migrations_must_use_canonical_entity_names
  - api_endpoints_must_use_canonical_conventions
  - event_payloads_must_use_canonical_event_names
  - no_synonym_usage_in_code_or_schemas
  - display_aliases_allowed_only_in_UI_localization_layer
  - new_entities_require_registry_addition_before_implementation
  - enum_additions_require_registry_update
```

---

*End of Canonical Semantic Registry v1*
