# Media Upload Pipeline Contract
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Image Compression Pipeline, validated against ADR-006 (Retry) and Sync Engine Contract  
**Purpose:** Define behavioral rules for image capture, compression, queuing, and upload in offline-first environments.

---

## 1. Pipeline Principles

```yaml
media_pipeline_principles:
  - never_block_UX_waiting_for_upload
  - compress_before_queue (reduce bandwidth)
  - preserve_GPS_and_timestamp_metadata (audit requirement)
  - generate_thumbnail_immediately (for offline UI preview)
  - deduplicate_by_content_hash (prevent duplicate uploads)
  - priority_queue_by_entity_type (disease evidence > gallery photos)
  - retry_with_same_policy_as_data_sync (exponential backoff, max 10, DLQ)
```

---

## 2. Bandwidth-Aware Compression Rules

| Network State | JPEG Quality | Max File Size | Rationale |
|---------------|-------------|---------------|-----------|
| WiFi | 75% | 800 KB | Good quality, fast upload |
| 4G | 60% | 500 KB | Balance quality/speed |
| 3G / Slow | 40% | 300 KB | Prioritize deliverability |
| Offline | 40% | 300 KB | Compress immediately for eventual upload |

```yaml
compression_rules:
  format: JPEG (always, even if captured as PNG/HEIC)
  max_dimension: 2048px (longest edge)
  thumbnail: 320×240 JPEG, generated immediately for local UI
  hard_cap: 500 KB per image (configurable per tenant)
```

---

## 3. Metadata Preservation

### Retained (Attached as Sidecar JSON)

```yaml
preserved_metadata:
  - gps_lat (from device at capture time)
  - gps_lng
  - gps_accuracy_meters
  - capture_timestamp (device clock, UTC)
  - actor_id (who captured)
  - actor_role
  - device_id
  - entity_type (parcel, disease_report, crop_activity, field_visit)
  - entity_id (local_id of parent entity)
  - image_purpose (evidence, boundary_photo, disease_photo, soil_card)
```

### Stripped (Privacy/Security)

```yaml
stripped_metadata:
  - camera_model
  - camera_serial_number
  - software_version
  - personal_EXIF_tags
```

---

## 4. Deduplication

```yaml
deduplication:
  method: SHA-256 hash of compressed image bytes + metadata JSON
  check: before queue insertion, query existing hashes in sync_queue
  behavior:
    hash_exists_same_entity: skip (true duplicate)
    hash_exists_different_entity: allow (same photo linked to multiple entities is valid)
```

---

## 5. Priority Queue Routing

| Image Purpose | Priority | Rationale |
|---------------|----------|-----------|
| Disease evidence | CRITICAL | Time-sensitive for advisory response |
| Insurance/parcel boundary evidence | CRITICAL | Required for claim processing |
| Field visit verification photos | HIGH | Needed for visit completion |
| Crop stage documentation | MEDIUM | Useful but not urgent |
| Optional gallery / general photos | LOW | Nice-to-have, defer under bandwidth pressure |

---

## 6. Upload Pipeline Flow

```yaml
pipeline_steps:

  1_capture:
    - user triggers camera
    - validate GPS accuracy (≤15m for parcel/disease, ≤50m for general)
    - save raw image locally with temp_id
    - show capture confirmation immediately (no wait)

  2_compress_and_metadata:
    - detect current network state
    - apply quality scaling per bandwidth rules
    - generate thumbnail (320×240) for immediate UI display
    - attach sidecar metadata JSON
    - compute SHA-256 hash of compressed file

  3_queue_and_dedup:
    - check hash against existing queue entries
    - if duplicate: skip silently
    - if new: insert into media_sync_queue with priority
    - set state: QUEUED_FOR_SYNC
    - UI shows thumbnail with sync status badge

  4_upload:
    - triggered by: connectivity restored OR periodic background task
    - check dependencies (parent entity must be synced first)
    - POST multipart/form-data to /media/upload
    - include: compressed image + metadata JSON + entity references

  5_verify:
    - server returns: server_id + server_checksum
    - client compares server_checksum with local hash
    - if match: mark SYNCED, store server_id for URL resolution
    - if mismatch: retry (corruption during transfer)

  6_failure_handling:
    - network error: increment retry_count, exponential backoff
    - server rejection (413 too large): re-compress at lower quality, retry
    - server rejection (validation): mark FAILED, notify user
    - max retries exceeded: move to DLQ, flag for manual review
```

---

## 7. Storage Lifecycle (Server-Side)

```yaml
storage_lifecycle:
  hot_storage: 90 days (fast access, full resolution)
  warm_storage: 90 days → 2 years (reduced access speed, full resolution)
  cold_storage: 2 years → 5 years (archive, retrieval takes minutes)
  
  exceptions:
    insurance_critical: immutable, never auto-deleted (regulatory requirement)
    audit_critical: retained per tenant audit_retention_policy
  
  tenant_isolation:
    path_prefix: "/{tenant_id}/{entity_type}/{entity_id}/{image_id}"
    access: signed URLs only (no public access)
    expiry: signed URLs expire in 1 hour (configurable)
```

---

## 8. Offline UI Behavior

```yaml
offline_media_ux:
  
  before_upload:
    display: thumbnail from local storage
    badge: sync status indicator (🟢 saved, 🔄 waiting, ✅ uploaded)
    tap_action: view full-resolution local copy
  
  after_upload:
    display: thumbnail (same as before — no visual change needed)
    badge: ✅ synced
    tap_action: load from server via signed URL (or local cache if available)
  
  failed_upload:
    display: thumbnail with ⚠️ badge
    tap_action: "Retry upload" or "This photo couldn't be sent"
    message: "💾 Photo saved on phone. Will upload when internet improves."
```

---

## 9. Validation Against ADRs

| ADR | Media Pipeline Compliance |
|-----|--------------------------|
| ADR-006 (Retry) | Exponential backoff, max 10 retries, DLQ terminal | ✅ |
| ADR-009 (Temporal) | capture_timestamp preserved as observation_time | ✅ |
| Sync Engine Contract | Same retry policy, same priority levels, same dependency ordering | ✅ |
| Offline Validation Rules | GPS accuracy gate (≤15m for parcel/disease photos) | ✅ |

---

*End of Media Upload Pipeline Contract*
