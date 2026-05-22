# Mobile Offline Schema Contract
# Agricultural Operations Intelligence Platform — Flutter/Drift

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Sprint 1 Day 2-3, validated against ADRs and Semantic Registry  
**Technology:** Flutter + Drift (SQLite)  
**Purpose:** Define the exact mobile database schema that mirrors server entities with sync metadata.

---

## Design Principles

```yaml
mobile_schema_principles:
  - mirrors_server_schema (same entity names, same field names)
  - every_table_has_sync_status (LOCAL_ONLY → QUEUED → SYNCED)
  - every_table_has_audit_fields (actor_id, role, timestamp, gps)
  - sync_queue_survives_app_restarts (persistent SQLite)
  - master_data_cached_locally (crops, villages, templates)
  - client_generates_UUIDs (for offline-first entity creation)
  - optimistic_concurrency_via_version_field
```

---

## Entity Tables

### farmers

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT (UUID) | PRIMARY KEY | Client-generated |
| tenant_id | TEXT (UUID) | NOT NULL | From JWT claims |
| mobile_number | TEXT | NOT NULL | Unique per tenant |
| village_id | TEXT (UUID) | NOT NULL | FK to geography cache |
| assistance_mode | TEXT ENUM | NOT NULL | SELF_MANAGED, DEALER_ASSISTED, FIELD_AGENT_ASSISTED, HYBRID |
| sync_status | TEXT ENUM | DEFAULT 'LOCAL_ONLY' | LOCAL_ONLY, QUEUED_FOR_SYNC, SYNCED, CONFLICTED, FAILED |
| sync_version | INTEGER | DEFAULT 1 | Optimistic concurrency |
| created_at | TEXT (ISO 8601) | NOT NULL | |
| updated_at | TEXT (ISO 8601) | NOT NULL | |
| valid_at | TEXT (ISO 8601) | NOT NULL | When fact was true (ADR-009) |
| observed_at | TEXT (ISO 8601) | NOT NULL | When captured on device (ADR-009) |
| audit_actor_id | TEXT (UUID) | NOT NULL | Who performed action |
| audit_actor_role | TEXT ENUM | NOT NULL | FARMER, DEALER, FIELD_AGENT |
| audit_timestamp | TEXT (ISO 8601) | NOT NULL | |
| audit_gps_lat | REAL | NULLABLE | |
| audit_gps_lng | REAL | NULLABLE | |

**Unique constraint:** (mobile_number, tenant_id)

### parcels

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT (UUID) | PRIMARY KEY | Client-generated |
| tenant_id | TEXT (UUID) | NOT NULL | |
| farmer_id | TEXT (UUID) | NOT NULL, FK farmers(id) | |
| village_id | TEXT (UUID) | NOT NULL | |
| geometry_geojson | TEXT | NOT NULL | GeoJSON Polygon string |
| area_hectares | REAL | NOT NULL | Client estimates, server recalculates |
| ownership_type | TEXT ENUM | NOT NULL | OWNED, LEASED, SHARED, UNKNOWN |
| irrigation_type | TEXT ENUM | NULLABLE | RAINFED, TUBEWELL, CANAL, DRIP, SPRINKLER, FLOOD |
| sync_status | TEXT ENUM | DEFAULT 'LOCAL_ONLY' | |
| sync_version | INTEGER | DEFAULT 1 | |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |
| valid_at | TEXT | NOT NULL | |
| observed_at | TEXT | NOT NULL | |
| audit_actor_id | TEXT | NOT NULL | |
| audit_actor_role | TEXT ENUM | NOT NULL | |
| audit_timestamp | TEXT | NOT NULL | |
| audit_gps_lat | REAL | NULLABLE | |
| audit_gps_lng | REAL | NULLABLE | |

### crop_cycles

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT (UUID) | PRIMARY KEY | |
| tenant_id | TEXT (UUID) | NOT NULL | |
| farmer_id | TEXT (UUID) | NOT NULL, FK farmers(id) | |
| parcel_id | TEXT (UUID) | NOT NULL, FK parcels(id) | |
| crop_id | TEXT (UUID) | NOT NULL | From crop_master cache |
| lifecycle_template_id | TEXT (UUID) | NOT NULL | |
| sowing_date | TEXT (date) | NOT NULL | |
| expected_harvest_date | TEXT (date) | NULLABLE | |
| status | TEXT ENUM | DEFAULT 'PLANNED' | PLANNED, ACTIVE, PARTIALLY_TRACKED, COMPLETED, ABANDONED |
| sync_status | TEXT ENUM | DEFAULT 'LOCAL_ONLY' | |
| sync_version | INTEGER | DEFAULT 1 | |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |
| valid_at | TEXT | NOT NULL | |
| observed_at | TEXT | NOT NULL | |
| audit_* | (same pattern) | | |

### stage_instances

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT (UUID) | PRIMARY KEY | |
| tenant_id | TEXT (UUID) | NOT NULL | |
| crop_cycle_id | TEXT (UUID) | NOT NULL, FK crop_cycles(id) | |
| workflow_stage_id | TEXT (UUID) | NOT NULL | From lifecycle_template |
| stage_order | INTEGER | NOT NULL | Display ordering |
| status | TEXT ENUM | DEFAULT 'PENDING' | PENDING, ACTIVE, COMPLETED, SKIPPED, PARTIALLY_COMPLETED, FAILED |
| started_at | TEXT | NULLABLE | |
| completed_at | TEXT | NULLABLE | |
| sync_status | TEXT ENUM | DEFAULT 'LOCAL_ONLY' | |
| sync_version | INTEGER | DEFAULT 1 | |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |
| valid_at | TEXT | NOT NULL | |
| observed_at | TEXT | NOT NULL | |
| audit_* | (same pattern) | | |

### crop_activities

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT (UUID) | PRIMARY KEY | |
| tenant_id | TEXT (UUID) | NOT NULL | |
| crop_cycle_id | TEXT (UUID) | NOT NULL, FK | |
| stage_instance_id | TEXT (UUID) | NOT NULL, FK | |
| activity_type | TEXT ENUM | NOT NULL | FERTILIZER_APPLICATION (MVP) |
| application_date | TEXT (date) | NOT NULL | valid_time for this activity |
| quantity_kg | REAL | NULLABLE | |
| cost_inr | REAL | NULLABLE | |
| application_method | TEXT | NULLABLE | |
| sync_status | TEXT ENUM | DEFAULT 'LOCAL_ONLY' | |
| sync_version | INTEGER | DEFAULT 1 | |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |
| valid_at | TEXT | NOT NULL | Same as application_date |
| observed_at | TEXT | NOT NULL | |
| audit_* | (same pattern) | | |

---

## Sync Queue Table

```yaml
sync_queue:
  event_id: TEXT PRIMARY KEY  # Client-generated UUID (idempotency key)
  entity_type: TEXT ENUM      # FARMER, PARCEL, CROP_CYCLE, STAGE_INSTANCE, CROP_ACTIVITY
  local_id: TEXT (UUID)       # Local entity ID
  operation: TEXT ENUM        # CREATE, UPDATE
  payload_json: TEXT          # Serialized entity data
  local_timestamp: TEXT       # When mutation occurred (UTC)
  version: INTEGER            # Optimistic concurrency version
  retry_count: INTEGER        # DEFAULT 0
  max_retries: INTEGER        # DEFAULT 10
  next_retry_after: TEXT      # ISO 8601 (null = ready to sync)
  priority: TEXT ENUM         # CRITICAL, HIGH, MEDIUM, LOW
  dependency_ids: TEXT        # Comma-separated local_ids this depends on
  last_error: TEXT            # Last failure reason (nullable)
  created_at: TEXT            # When queued
```

---

## Master Data Cache Tables (Read-Only, Server-Synced)

### crop_master
```
id, canonical_name, regional_aliases (JSON), lifecycle_template_id, version, last_synced_at
```

### geography_villages
```
id, name, block_id, district_id, state_id, version, last_synced_at
```

### lifecycle_templates
```
id, crop_id, name, stages_json (JSON array of stage definitions), version, last_synced_at
```

---

## Indexes

```sql
CREATE INDEX idx_farmers_village ON farmers(village_id);
CREATE INDEX idx_parcels_farmer ON parcels(farmer_id);
CREATE INDEX idx_crop_cycles_parcel ON crop_cycles(parcel_id);
CREATE INDEX idx_crop_cycles_farmer ON crop_cycles(farmer_id);
CREATE INDEX idx_stage_instances_cycle ON stage_instances(crop_cycle_id);
CREATE INDEX idx_activities_stage ON crop_activities(stage_instance_id);
CREATE INDEX idx_sync_queue_priority ON sync_queue(priority, next_retry_after);
CREATE INDEX idx_sync_queue_pending ON sync_queue(retry_count) WHERE retry_count < max_retries;
CREATE INDEX idx_sync_queue_deps ON sync_queue(dependency_ids) WHERE dependency_ids IS NOT NULL;
```

---

## Sync Manager Behavior

```yaml
sync_manager:
  trigger: connectivity_detected OR app_foregrounded OR manual_retry
  
  process:
    1: query sync_queue WHERE retry_count < max_retries ORDER BY priority ASC, created_at ASC
    2: resolve dependencies (skip items whose dependency_ids have unsynced items)
    3: batch items (max 50 per request)
    4: POST /sync/events
    5: process response:
       - accepted: update entity sync_status → SYNCED, remove from queue
       - conflicts: update entity sync_status → CONFLICTED, store conflict metadata
       - failed (retryable): increment retry_count, calculate next_retry_after (exponential backoff)
       - failed (non-retryable): update sync_status → FAILED, preserve in queue for user action

  backoff_formula: "next_retry = min(30s * 2^retry_count + jitter, 24h)"
  
  user_visibility:
    - show pending count badge
    - show failed items with "Retry" button
    - show conflicted items with "Resolve" action
```

---

## Validation Against ADRs

| ADR | Schema Compliance |
|-----|------------------|
| ADR-005 (MVP Slice) | Only slice entities included | ✅ |
| ADR-006 (Retry) | sync_queue has max_retries=10, exponential backoff | ✅ |
| ADR-007 (Conflict) | sync_status includes CONFLICTED state | ✅ |
| ADR-009 (Temporal) | valid_at + observed_at on all entities | ✅ |
| Semantic Registry | All enum values match canonical SCREAMING_SNAKE_CASE | ✅ |

---

*End of Mobile Offline Schema Contract*
