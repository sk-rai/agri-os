# Master Data Management & Caching Strategy
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Master Data Management & Caching Strategy  
**Depends on:** ADR-001 (Monolith), Configuration Governance Model, Offline Validation Rules  
**Purpose:** Define how reference/master data is cached on mobile devices, kept fresh via delta sync, and handles staleness gracefully in offline-first environments.

---

## 1. Core Principles

```yaml
master_data_principles:

  offline_availability:
    - ALL operational dropdowns MUST resolve from local cache
    - NEVER block farmer enrollment or parcel mapping due to missing master data
    - workflows continue with stale data if necessary (warn, don't block)

  canonical_plus_override:
    - master_data = platform_canonical_base + tenant_specific_overrides
    - tenant overrides NEVER mutate canonical definitions
    - tenant overrides are versioned, audited, and reversible

  delta_sync_preferred:
    - if local version == server version → skip download
    - else fetch only deltas + tombstones since last_sync_version
    - full download only on first run OR cache corruption detected

  versioned_immutability:
    - canonical records are append-only (updates create new version)
    - old versions preserved for historical analytics replay
    - deprecated records marked inactive, never deleted
```

---

## 2. Master Data Classification

| Category | Change Frequency | Examples | Cache TTL | Sync Strategy | Mobile Priority |
|----------|-----------------|----------|-----------|---------------|-----------------|
| **Static** | Rarely (<1/year) | soil_types, irrigation_methods, ownership_types, canonical_units | 180 days | Full on first sync, delta on schema change | Highest (required for validation) |
| **Semi-Dynamic** | Monthly/Quarterly | crop_master, crop_varieties, disease_categories, input_types, manufacturers | 30 days | Delta sync with tombstone tracking | High (used in crop workflows) |
| **Dynamic** | Daily/Weekly | village_hierarchy, dealer_assignments, active_campaigns, regional_pricing | 24 hours | Frequent delta sync, event-driven refresh | Medium (territory-scoped) |
| **Tenant-Custom** | Ad-hoc | lifecycle_templates, workflow_stages, notification_templates, KPI_formulas, branding | Until version change | Tenant-scoped delta, explicit sync trigger | Context-dependent |

---

## 3. Cache Architecture

### Tiered Cache Hierarchy

```yaml
cache_tiers:
  L1_runtime_memory:
    purpose: active dropdown state, current filters, recently accessed items
    lifetime: app session (cleared on app close)
    size: ~5MB
    
  L2_local_sqlite:
    purpose: persistent master data cache, survives reboot
    lifetime: until TTL expiry or explicit invalidation
    size: max 50MB per device (with LRU eviction)
    
  L3_server_api:
    purpose: authoritative source, delta sync endpoint
    access: on connectivity, background sync
```

### Local Cache Schema

```yaml
master_data_cache_table:
  entity_type: ENUM (geography, crop, input, disease, template, config)
  canonical_id: UUID
  version: STRING (semver)
  data_json: TEXT (minified JSON payload)
  tenant_id: UUID or 'platform_default'
  last_synced_at: DATETIME (UTC)
  ttl_seconds: INTEGER
  is_active: BOOLEAN (false = deprecated/tombstoned)
  checksum: SHA-256 of data_json

cache_metadata_table:
  entity_type: ENUM
  server_version: STRING
  last_sync_timestamp: DATETIME (UTC)
  sync_mode: ENUM [full, delta, event_driven]
  sync_status: ENUM [ok, stale, corrupted, pending]
```

---

## 4. Delta Sync Protocol

### API Contract

```yaml
endpoint: GET /api/v1/master-data/sync
parameters:
  entity_type: enum (required)
  last_version: string (client's current version)
  tenant_id: uuid (required)

response:
  version: "v1.2.0" (server's current version)
  full_sync_required: boolean (true if client too far behind)
  deltas:
    - id: UUID
      version: "v1.2.0"
      payload: JSON
      action: "create" | "update" | "deprecate"
  tombstones:
    - id: UUID
      deprecated_at: ISO 8601
  sync_metadata:
    timestamp: UTC
    tenant_overrides_count: integer
```

### Delta Application Logic

```yaml
delta_application:
  transaction: atomic (all-or-nothing per sync batch)
  
  for_each_delta:
    if action == "create" or "update":
      INSERT_OR_REPLACE in master_data_cache
    if action == "deprecate":
      SET is_active = FALSE
  
  for_each_tombstone:
    SET is_active = FALSE, is_deleted = TRUE
  
  after_all_applied:
    UPDATE cache_metadata SET server_version = response.version, sync_status = "ok"
```

---

## 5. Cache Invalidation Triggers

```yaml
invalidation_triggers:

  1_ttl_expiry:
    mechanism: background check on app startup and periodic timer
    action: mark stale, trigger background delta sync
    
  2_version_mismatch:
    mechanism: detected during operational sync handshake (server returns newer version)
    action: trigger delta sync for affected entity_type
    
  3_event_driven:
    mechanism: server publishes `master_data_updated.v1` event
    action: mobile wakes sync worker on next connectivity
    
  4_manual_refresh:
    mechanism: dealer/admin taps "Refresh Data" button
    action: force full sync for all entity types
    
  5_tenant_config_change:
    mechanism: workflow/KPI/template updated via Configuration Governance
    action: invalidate related cache partitions for that tenant
```

---

## 6. Freshness Validation

```yaml
freshness_check:
  function: is_cache_fresh(entity_type)
  logic:
    - if no metadata exists → NOT fresh (trigger full sync)
    - if sync_status == "corrupted" → NOT fresh (trigger full sync)
    - if current_time > last_sync_timestamp + ttl_seconds → NOT fresh (trigger delta)
    - else → FRESH (use local cache)
```

---

## 7. Fallback & Degradation Behavior

```yaml
fallback_hierarchy:

  step_1: try L2 SQLite cache (is_active = TRUE, latest version)
  step_2: if cache empty/stale AND network available → fetch from server, cache, return
  step_3: if cache empty/stale AND network unavailable:
    - show "⚠️ Using older reference data" banner to user
    - allow workflow to continue with stale cache
    - log telemetry: master_data_fallback_triggered
  step_4: NEVER throw blocking error for missing master data in field workflows

  validation_fallback:
    if dropdown data missing:
      - allow manual text entry with note "will validate on sync"
      - queue for async validation once connectivity restored
      - show: "📋 Manual entry - will verify later"
```

---

## 8. Storage Budget & Eviction

```yaml
storage_rules:

  max_cache_size: 50MB per device
  
  eviction_policy: LRU (Least Recently Used)
  
  eviction_priority (evict first → last):
    1_evict_first: campaigns, regional_pricing, optional_forms
    2_evict_next: disease_categories, input_types (can re-fetch)
    3_never_evict: geography_villages, crop_master, soil_types, canonical_enums
    4_preserve: tenant_overrides (until explicit sync or logout)

  compression:
    - store JSON minified
    - if payload > 10KB → gzip before SQLite insert
    - decompress on read into memory cache
```

---

## 9. Tenant Isolation in Cache Queries

```yaml
query_pattern:
  
  function: get_master_data(entity_type, filter, tenant_id)
  
  logic:
    SELECT FROM master_data_cache
    WHERE entity_type = X
      AND is_active = TRUE
      AND tenant_id IN (tenant_id, 'platform_default')
    ORDER BY:
      tenant_specific first (priority over platform default)
      latest version first
    DEDUPLICATE BY canonical_id (tenant override wins if exists)

  result: tenant-specific override wins, else platform default
  
  isolation_guarantee:
    - tenant_id is part of composite key
    - cross-tenant query rejected at API layer
    - audit logs all tenant override create/update/delete
```

---

## 10. UI Integration Rules

```yaml
ui_rules:

  dropdown_rendering:
    - render from local cache FIRST (never wait for server)
    - if cache loading → show spinner or cached placeholder
    - if cache stale → show "🟡 Older data" badge (but still functional)
    - NEVER block form submission waiting for master data refresh

  freshness_indicators:
    fresh (synced within TTL): no indicator (normal state)
    stale (past TTL, not yet refreshed): "🟡 Data may be outdated"
    corrupted (checksum mismatch): "⚠️ Refreshing data..." (auto-trigger sync)

  form_validation:
    - validator reads enums from cache
    - if cache missing → fallback to hardcoded schema registry (last resort)
    - on sync complete → re-validate open forms if data changed (non-blocking notification)
```

---

## 11. Master Data Sync Lifecycle

```yaml
sync_lifecycle:

  on_first_app_launch:
    - request full master data for all entity types
    - populate L2 cache
    - set cache_metadata.sync_status = "ok"
    - this is the ONLY time full download occurs

  on_subsequent_app_startup:
    - check each entity_type freshness
    - if stale → trigger background delta sync (non-blocking)
    - if fresh → use local cache immediately

  on_connectivity_restored:
    - check cache_metadata for any stale entity types
    - trigger delta sync for stale types (priority: static > semi-dynamic > dynamic)
    - operational data sync takes priority over master data refresh

  on_tenant_config_change_event:
    - invalidate affected cache partitions
    - trigger delta sync for tenant-custom entity types
    - notify user if active form affected: "📋 Options updated - please review"
```

---

## 12. Invariants

```yaml
master_data_invariants:
  - canonical_master_data_never_mutated_by_tenant
  - all_master_data_queries_include_tenant_isolation_logic
  - offline_workflows_never_fail_due_to_missing_master_data
  - cache_sync_is_delta_based_with_tombstone_support
  - mobile_cache_size_never_exceeds_50MB (LRU eviction enforced)
  - tenant_overrides_are_versioned_and_audited
  - cache_fallback_warns_user_but_never_blocks_operation
  - all_master_data_API_responses_include_semantic_version
  - sync_engine_preserves_cache_across_app_restarts
  - stale_master_data_records_submitted_offline_are_valid_for_sync
```

---

*End of Master Data Management & Caching Strategy*
