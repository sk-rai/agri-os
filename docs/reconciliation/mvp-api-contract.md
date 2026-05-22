# MVP API Contract (OpenAPI 3.0)
# Agricultural Operations Intelligence Platform — Vertical Slice

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Sprint 1 Day 2-3 deliverables, validated against our ADRs and Semantic Registry  
**Scope:** Endpoints for the MVP vertical slice (ADR-005)

---

## API Principles

```yaml
api_principles:
  - all_endpoints_tenant_scoped_via: "X-Tenant-ID header (uuid)"
  - all_mutations_require: "Bearer JWT authentication"
  - all_responses_include: "correlation_id for distributed tracing"
  - all_errors_follow: "RFC 7807 Problem Details format"
  - all_timestamps: "UTC ISO 8601"
  - all_geospatial: "GeoJSON (EPSG:4326)"
  - all_entity_names: "Canonical Semantic Registry v1"
  - all_enums: "SCREAMING_SNAKE_CASE"
  - offline_safe_endpoints: "support idempotency via client-generated event_id/local_id"
```

---

## MVP Endpoint Catalog

| Method | Path | Description | Auth | Offline-Safe |
|--------|------|-------------|------|-------------|
| POST | `/auth/otp/request` | Request OTP for login | None | ❌ |
| POST | `/auth/otp/verify` | Verify OTP, issue JWT | None | ❌ |
| POST | `/farmers` | Create farmer profile | Dealer/Agent | ✅ (queue) |
| GET | `/farmers/{id}` | Get farmer details | Any authenticated | ✅ (cache) |
| POST | `/parcels` | Create parcel with geometry | Dealer/Agent/Farmer | ✅ (queue) |
| GET | `/parcels/{id}` | Get parcel details | Any authenticated | ✅ (cache) |
| POST | `/crop-cycles` | Start new crop cycle | Dealer/Agent/Farmer | ✅ (queue) |
| GET | `/crop-cycles/{id}` | Get crop cycle + stages | Any authenticated | ✅ (cache) |
| PATCH | `/crop-cycles/{id}/stages/{stage_id}` | Update stage status | Dealer/Agent/Farmer | ✅ (queue) |
| POST | `/crop-activities` | Log activity (fertilizer) | Dealer/Agent/Farmer | ✅ (queue) |
| POST | `/sync/events` | Batch upload offline mutations | Any authenticated | ❌ (server-only) |
| GET | `/sync/status` | Get sync queue status | Any authenticated | ❌ |
| GET | `/dashboards/operational` | Enterprise operational view | Enterprise Admin | ❌ |

---

## Key Schema Definitions

### AuditMetadata (included in ALL mutation responses)

```yaml
AuditMetadata:
  actor_id: uuid
  actor_role: enum [FARMER, DEALER, FIELD_AGENT]
  timestamp: datetime (UTC ISO 8601)
  gps_lat: number (nullable)
  gps_lng: number (nullable)
```

### FarmerCreateRequest

```yaml
required: [mobile_number, assistance_mode, village_id]
properties:
  mobile_number: string (pattern: ^\+?\d{10,15}$)
  assistance_mode: enum [SELF_MANAGED, DEALER_ASSISTED, FIELD_AGENT_ASSISTED, HYBRID]
  village_id: uuid
  local_id: uuid (client-generated for offline idempotency)
```

### ParcelCreateRequest

```yaml
required: [farmer_id, geometry, ownership_type]
properties:
  farmer_id: uuid
  village_id: uuid
  geometry: GeoJSON Polygon (EPSG:4326, minimum 4 coordinates)
  ownership_type: enum [OWNED, LEASED, SHARED, UNKNOWN]
  irrigation_type: enum [RAINFED, TUBEWELL, CANAL, DRIP, SPRINKLER, FLOOD] (optional)
  local_id: uuid (client-generated)
```

### CropCycleCreateRequest

```yaml
required: [farmer_id, parcel_id, crop_id, lifecycle_template_id, sowing_date]
properties:
  farmer_id: uuid
  parcel_id: uuid
  crop_id: uuid (from crop_master)
  lifecycle_template_id: uuid
  sowing_date: date (ISO 8601)
  expected_harvest_date: date (nullable)
  local_id: uuid (client-generated)
```

### Stage Update (PATCH)

```yaml
required: [new_status]
properties:
  new_status: enum [PENDING, ACTIVE, COMPLETED, SKIPPED]
```

Note: Server validates transition against lifecycle_template state machine. Invalid transitions return 409.

### SyncEvent (batch upload item)

```yaml
required: [event_id, entity_type, local_id, operation, payload, local_timestamp]
properties:
  event_id: uuid (client-generated, idempotency key)
  entity_type: enum [FARMER, PARCEL, CROP_CYCLE, STAGE_INSTANCE, CROP_ACTIVITY]
  local_id: uuid (client-side entity ID)
  operation: enum [CREATE, UPDATE]
  payload: object (matches respective entity schema)
  local_timestamp: datetime (when mutation occurred on device, UTC)
  version: integer (optimistic concurrency)
  dependency_ids: array of uuid (entities this depends on for ordering)
```

### Sync Response

```yaml
properties:
  accepted: array of uuid (event_ids successfully processed)
  conflicts: array of SyncConflict
  failed: array of SyncError

SyncConflict:
  event_id: uuid
  conflict_type: enum [VERSION_MISMATCH, GEOSPATIAL_OVERLAP, WORKFLOW_INVALID]
  server_version: integer
  client_version: integer
  resolution_required: boolean

SyncError:
  event_id: uuid
  error_code: enum [VALIDATION_FAILED, DEPENDENCY_MISSING, TENANT_MISMATCH]
  message: string
  retryable: boolean
```

---

## Validation Against Our ADRs

| ADR | API Compliance |
|-----|---------------|
| ADR-001 (Monolith) | Single API server, no inter-service calls | ✅ |
| ADR-002 (Communication) | All mutations publish events internally | ✅ |
| ADR-004 (Geography) | village_id references geography hierarchy | ✅ |
| ADR-005 (MVP Slice) | Only slice endpoints included | ✅ |
| ADR-006 (Retry) | Sync response includes retryable flag | ✅ |
| ADR-007 (Conflict) | Sync returns conflict_type for resolution routing | ✅ |
| ADR-009 (Temporal) | local_timestamp = observation_time; server adds transaction_time | ✅ |
| Semantic Registry | All entity names, enums match canonical terms | ✅ |

---

## Implementation Notes

- `local_id` on create requests enables offline-first: client generates UUID, server uses it or maps to server ID
- `event_id` on sync events enables idempotency: server deduplicates by event_id
- `dependency_ids` on sync events enables ordering: server processes dependencies first
- `version` on sync events enables conflict detection: server compares with current version
- Area calculation (`area_hectares`) is server-side from geometry — client may estimate locally for display

---

*End of MVP API Contract*
