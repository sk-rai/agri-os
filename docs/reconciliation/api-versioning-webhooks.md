# API Versioning, Compatibility & Webhook Contract
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 API Capability Tree & Versioning Strategy  
**Depends on:** MVP API Contract, Canonical Semantic Registry v1, Security & Audit Framework  
**Purpose:** Define API evolution rules, backward compatibility guarantees, deprecation lifecycle, and webhook delivery contracts for external integrations.

---

## 1. API Capability Tree (Full Endpoint Catalog)

```yaml
api_domains:

  identity_and_access:
    endpoints: [/auth/otp/request, /auth/otp/verify, /auth/refresh, /users/me]
    tenant_isolation: false (auth is pre-tenant)
    offline_safe: false

  master_data:
    endpoints: [/geography/states, /geography/districts, /geography/villages, /master-data/crops, /master-data/inputs, /master-data/soil-types, /master-data/sync]
    tenant_isolation: false (canonical data)
    offline_safe: true (cached on device)

  farmer_management:
    endpoints: [POST /farmers, GET /farmers/{id}, PATCH /farmers/{id}, GET /farmers?territory_id=&status=]
    tenant_isolation: true
    offline_safe: true

  parcel_management:
    endpoints: [POST /parcels, GET /parcels/{id}, PATCH /parcels/{id}/geometry, GET /parcels?farmer_id=]
    tenant_isolation: true
    offline_safe: true

  crop_workflow:
    endpoints: [POST /crop-cycles, GET /crop-cycles/{id}, PATCH /crop-cycles/{id}/stages/{stage_id}, GET /crop-cycles?parcel_id=&status=]
    tenant_isolation: true
    offline_safe: true

  crop_activities:
    endpoints: [POST /crop-activities, GET /crop-activities/{id}, GET /crop-activities?crop_cycle_id=&stage=]
    tenant_isolation: true
    offline_safe: true

  economics:
    endpoints: [POST /economics/yield-records, POST /economics/cost-entries, GET /economics/profitability/{crop_cycle_id}]
    tenant_isolation: true
    offline_safe: true

  disease_and_advisory:
    endpoints: [POST /disease-reports, GET /disease-reports/{id}, POST /disease-reports/{id}/advisories, GET /advisories?farmer_id=&status=]
    tenant_isolation: true
    offline_safe: true

  offline_sync:
    endpoints: [POST /sync/events, GET /sync/status, POST /sync/resolve-conflict, GET /sync/queue/pending]
    tenant_isolation: true
    offline_safe: false (server-only)

  media:
    endpoints: [POST /media/upload, GET /media/{id}/signed-url, DELETE /media/{id}]
    tenant_isolation: true
    offline_safe: false

  notifications:
    endpoints: [GET /notifications?user_id=&status=, POST /notifications/acknowledge, POST /campaigns]
    tenant_isolation: true
    offline_safe: true (read/acknowledge)

  analytics:
    endpoints: [GET /analytics/kpis?scope=&dimensions=, GET /dashboards/territory-overview, GET /benchmarks?crop=&geography=]
    tenant_isolation: true
    offline_safe: false

  content:
    endpoints: [GET /content/articles?crop=&language=, GET /content/videos/{id}/metadata]
    tenant_isolation: false (territory-scoped)
    offline_safe: true (cached)

  webhooks:
    endpoints: [POST /webhooks/subscriptions, GET /webhooks/subscriptions, PATCH /webhooks/subscriptions/{id}, DELETE /webhooks/subscriptions/{id}]
    tenant_isolation: true
    offline_safe: false
```

---

## 2. Versioning Strategy

### Versioning Model

```yaml
versioning_model:
  major_changes: URL versioning (/api/v1/, /api/v2/)
  minor_changes: header negotiation (X-API-Version: 1.1)

  major_version_triggers:
    - field removed or field type changed
    - endpoint method changed (GET → POST)
    - authentication scope changed
    - canonical semantic changed (entity renamed)

  minor_version_triggers:
    - new endpoint added
    - new field added to response (optional)
    - new enum value added
    - new optional query parameter added
```

### Compatibility Requirements

```yaml
compatibility_matrix:
  client_must_support: current_version AND current_version - 1
  server_must_support: current_version AND current_version - 1 simultaneously
  deprecated_version: returns HTTP 410 Gone after sunset period
```

---

## 3. Backward Compatibility Rules

### Additive-Only Evolution

```yaml
additive_only_rules:
  - new response fields MUST be optional or have server defaults
  - new request fields MUST be optional
  - new endpoints MUST NOT alter existing routing logic
  - new enum values MUST NOT break existing consumer switch statements
```

### Immutable Contract Elements

```yaml
immutable_contract:
  - field names CANNOT be renamed (ever)
  - field data types CANNOT change (string → number is breaking)
  - enum values CANNOT be removed (only deprecated with continued support)
  - query parameters CANNOT become required retroactively
  - response structure CANNOT change shape (array → object is breaking)
```

### Consumer Resilience Requirements

```yaml
consumer_resilience:
  - clients MUST ignore unknown response fields (forward compatibility)
  - clients MUST handle unexpected null values gracefully
  - clients MUST NOT rely on field order in JSON arrays
  - pagination MUST use cursor or offset (not assumed continuity)
  - clients MUST handle 410 Gone gracefully (show upgrade prompt)
```

### Server Hardening

```yaml
server_hardening:
  - API gateway strips unknown request fields before processing
  - validation errors return RFC 7807 Problem Details format
  - all mutations preserve audit metadata regardless of API version
  - rate limiting applied per tenant + per device (not just per IP)
```

---

## 4. Deprecation & Sunset Policy

### Lifecycle Stages

```yaml
deprecation_lifecycle:

  stage_1_active:
    description: current production version, full support
    duration: indefinite until successor announced

  stage_2_deprecated:
    description: announced via headers + developer portal
    minimum_duration: 180 days
    signaling:
      http_headers:
        Deprecation: "true"
        Sunset: "2027-06-30T00:00:00Z"
        Link: '</api/v2/farmers>; rel="successor-version"'
      developer_portal:
        - version usage dashboard per tenant
        - automated alerts at 90d, 60d, 30d, 7d before sunset
        - migration guide with side-by-side contract diff

  stage_3_sunset:
    description: endpoint returns 410 Gone
    response: { "error": "DEPRECATED_ENDPOINT", "sunset_date": "...", "migration_url": "..." }
    logging: tenant_id, actor_id, deprecated_endpoint, timestamp
    rule: NEVER allow silent fallback to deprecated logic after sunset

  exception_process:
    - enterprise clients may request 90-day extension
    - requires SLA impact assessment and migration plan
    - extension logged and time-bound (no indefinite extensions)
```

---

## 5. Webhook Contract (External Integration)

### Architecture

```yaml
webhook_architecture:
  purpose: external event delivery for enterprises, insurers, partners
  delivery_model: at-least-once with idempotent consumers
  security: HMAC-SHA256 signature + TLS 1.2+ + optional IP allowlist
```

### Payload Envelope

```yaml
webhook_payload:
  event_id: UUID (globally unique, idempotency key)
  event_type: string (e.g., "crop_stage_completed.v1", "sync_conflict_detected.v1")
  timestamp: ISO 8601 UTC
  tenant_id: UUID
  entity_type: canonical entity name (from Semantic Registry)
  entity_id: UUID
  version: semver (e.g., "v1.0")
  payload: object (entity-specific data)
  metadata:
    correlation_id: UUID
    source_system: "agri_platform"
    retry_count: integer

  signature_header: "X-Webhook-Signature: sha256=<hmac_hex_of_body>"
```

### Delivery Rules

```yaml
webhook_delivery:
  initial_attempt: synchronous POST within 30 seconds of event publication
  retry_policy: exponential backoff (30s → 1m → 2m → 4m → 8m → max 24h)
  max_retries: 10 then DLQ
  success_criteria: HTTP 2xx or 204 response within 30 seconds
  
  failure_handling:
    4xx_client_error: stop retrying, log to audit (consumer's problem)
    5xx_server_error: retry with backoff
    timeout: treat as failure, retry
  
  idempotency: consumer MUST check event_id before processing (duplicates expected)
```

### Subscription Management

```yaml
webhook_subscriptions:
  create: POST /webhooks/subscriptions { url, events[], secret, active: true }
  filter: tenant-scoped AND event-type-scoped
  status: GET /webhooks/subscriptions/{id}/delivery-status (success_rate, last_attempt, failures)
  replay: POST /webhooks/subscriptions/{id}/replay?from_timestamp=&to_timestamp=
  
  consumer_requirements:
    - verify HMAC signature before parsing payload
    - check event_id against processed log (deduplication)
    - acknowledge within 30 seconds OR return 202 Accepted for async processing
    - NEVER block main thread on heavy payload processing
```

### Webhook Event Types (MVP)

| Event Type | Trigger | Typical Consumer |
|-----------|---------|-----------------|
| `farmer_registered.v1` | New farmer enrolled | CRM, enterprise analytics |
| `crop_stage_completed.v1` | Stage transition validated | Enterprise dashboards, advisory systems |
| `disease_reported.v1` | New disease observation | Expert review systems, outbreak monitoring |
| `sync_conflict_detected.v1` | Conflict during sync | Monitoring systems, admin dashboards |
| `advisory_issued.v1` | Expert advisory published | Notification systems, farmer apps |
| `crop_cycle_completed.v1` | Harvest recorded | Profitability analytics, insurance systems |

---

## 6. API Performance Targets

```yaml
performance_targets:
  core_crud_endpoints:
    p50_latency: < 200ms
    p95_latency: < 800ms
    p99_latency: < 2000ms
  
  sync_batch_endpoint:
    p95_latency: < 5000ms (for batch of 50 events)
    throughput: handle 100 concurrent sync requests
  
  analytics_endpoints:
    p95_latency: < 3000ms (complex aggregations)
    caching: results cached 5 minutes (per ADR-008)
  
  webhook_delivery:
    initial_delivery: < 30 seconds from event publication
    success_rate_target: > 95% first-attempt delivery
```

---

## 7. API Invariants (CI/CD Enforceable)

```yaml
api_invariants:
  # Contract stability
  - breaking_changes_require_major_version_bump
  - additive_only_within_same_major_version
  - deprecated_endpoints_signal_via_headers_for_180_days_minimum
  - sunset_endpoints_return_410_never_silent_fallback

  # Security
  - all_endpoints_except_auth_require_X-Tenant-ID_header
  - all_mutations_require_Bearer_JWT
  - all_responses_include_correlation_id
  - webhook_payloads_signed_with_HMAC-SHA256

  # Consistency
  - all_entity_names_match_Canonical_Semantic_Registry_v1
  - all_enums_use_SCREAMING_SNAKE_CASE
  - all_timestamps_UTC_ISO_8601
  - all_errors_RFC_7807_Problem_Details

  # Audit
  - all_mutations_emit_audit_event
  - all_webhook_deliveries_logged
  - deprecated_endpoint_usage_tracked_per_tenant

  # Performance
  - contract_tests_validate_schema_on_every_PR
  - load_tests_validate_p95_latency_before_staging_deploy
  - webhook_retry_logic_tested_in_integration_suite
```

---

*End of API Versioning, Compatibility & Webhook Contract*
