# Offline Form Validation Rules
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Offline Form Validation Rules, validated against Semantic Registry and ADR-005  
**Purpose:** Define validation rules enforced CLIENT-SIDE before any record enters the sync queue. These prevent invalid data from consuming sync bandwidth and reduce server-side rejection.

---

## 1. Validation Principle

> **Validate locally, reject early, explain clearly.**  
> Every form submission is validated on-device before entering the sync queue.  
> Invalid records never reach the server. Error messages use ≤5 words + icon.

---

## 2. Validation Rules Matrix

### Farmer Enrollment

| Field | Rule | Offline Enforcement | Error Message |
|-------|------|--------------------|----|
| mobile_number | Required, format `^\+?\d{10,15}$` | Regex check | 📞 Enter 10-digit number |
| mobile_number | Unique per tenant | Local DB query (farmers WHERE mobile_number = X AND tenant_id = Y) | 👤 Already in system |
| village_id | Required, must exist in local geography cache | FK check against geography_villages table | 📍 Select your village |
| assistance_mode | Required, must be valid enum | Enum membership check | 📋 Select from list |

### Parcel Creation

| Field | Rule | Offline Enforcement | Error Message |
|-------|------|--------------------|----|
| farmer_id | Required, must exist locally | FK check against farmers table | 👤 Select farmer first |
| geometry | Required, ≥4 coordinate points | Array length check | 🗺️ Close boundary line |
| geometry | Polygon must be closed (first point = last point) | Coordinate comparison | 🗺️ Close boundary line |
| geometry | No self-intersection | Local geometric check | 🗺️ Boundary lines cross |
| area_hectares | Must be ≥ 0.1 hectare | Numeric bounds | 📏 Area too small (min 0.1 ha) |
| GPS accuracy | Must be ≤ 15 meters at capture time | Device GPS accuracy reading | 📍 Move to open area |
| ownership_type | Required, valid enum | Enum check | 📋 Select ownership type |

### Crop Cycle Creation

| Field | Rule | Offline Enforcement | Error Message |
|-------|------|--------------------|----|
| farmer_id | Required, exists locally | FK check | 👤 Select farmer first |
| parcel_id | Required, exists locally, belongs to farmer | FK + ownership check | 📍 Select parcel first |
| crop_id | Required, exists in crop_master cache | FK check against cache | 🌱 Select crop type |
| lifecycle_template_id | Required, valid for selected crop | Template lookup | 🌱 Select crop workflow |
| sowing_date | Required, not in future by >7 days | Date bounds | 📅 Check sowing date |

### Stage Instance Update

| Field | Rule | Offline Enforcement | Error Message |
|-------|------|--------------------|----|
| new_status | Must be valid transition from current status | Local state machine check against lifecycle_template | 🌱 Invalid stage update |
| crop_cycle.status | Must be ACTIVE or PARTIALLY_TRACKED | Status check | 🌾 Crop cycle not active |

### Crop Activity (Fertilizer Log)

| Field | Rule | Offline Enforcement | Error Message |
|-------|------|--------------------|----|
| stage_instance_id | Required, must be ACTIVE stage | FK + status check | 🌱 Select active stage |
| application_date | Required, within stage active window | Date range check | 📅 Date outside stage period |
| quantity_kg | If provided, must be > 0 and < 10000 | Numeric bounds | 📏 Check quantity |
| cost_inr | If provided, must be > 0 and < 1000000 | Numeric bounds | 💰 Check amount |

---

## 3. Cross-Cutting Validation Rules

| Rule | Applies To | Enforcement | Error Message |
|------|-----------|-------------|---------------|
| Audit actor_id required | ALL mutations | Auto-injected from session (never user-entered) | (system error, not user-facing) |
| Audit timestamp required | ALL mutations | Auto-injected from device clock | (system error) |
| Payload size < 2MB | ALL sync queue items | Size check before enqueue | 💾 Remove extra photos |
| tenant_id present | ALL records | Auto-injected from session | (system error) |
| observed_at captured | ALL records | Auto-injected at form submission time | (system error) |
| valid_at captured | ALL records with date fields | Derived from user-entered date (e.g., application_date) | (system error) |

---

## 4. Rural UX Error Design Rules

```yaml
error_message_rules:
  max_words: 5
  must_include: icon (emoji or system icon)
  language: farmer's preferred language
  tone: helpful, not accusatory
  action_guidance: always tell user WHAT TO DO, not just what's wrong
  
  forbidden:
    - technical terms (UUID, HTTP, JSON, schema, validation)
    - error codes visible to user
    - stack traces or debug info
    - blame language ("you entered wrong...")
  
  pattern: "[icon] [what to do]"
  examples:
    good: "📞 Enter 10-digit number"
    good: "📍 Move to open area"
    good: "🗺️ Close boundary line"
    bad: "Error: Invalid mobile_number format"
    bad: "Validation failed: polygon self-intersection detected"
    bad: "FK constraint violation on farmer_id"
```

---

## 5. Validation Execution Order

```yaml
validation_pipeline:
  step_1: required_field_check (are all mandatory fields filled?)
  step_2: format_validation (do values match expected patterns?)
  step_3: enum_validation (are selections from valid canonical sets?)
  step_4: business_rule_check (area thresholds, date ranges, state machine)
  step_5: duplicate_detection (local DB query for uniqueness)
  step_6: audit_field_injection (auto-fill actor_id, timestamp, GPS, tenant_id)
  step_7: payload_size_check (< 2MB including images)
  
  on_first_failure: stop, show error for FIRST failing rule only
  rationale: showing multiple errors overwhelms low-literacy users
```

---

## 6. Duplicate Detection Rules

```yaml
duplicate_detection:
  
  farmer:
    signal: mobile_number + tenant_id
    check: local DB query before enqueue
    behavior: block creation, show existing farmer details
    message: "👤 Already in system"
    action: offer to view existing farmer record
  
  parcel:
    signal: geometry overlap > 5% with existing parcel for same farmer
    check: local geometric comparison (simplified bounding box check)
    behavior: warn but allow (server does precise PostGIS check)
    message: "🗺️ May overlap existing parcel"
    action: show warning, allow user to proceed or cancel
  
  crop_activity:
    signal: same activity_type + same stage + same date + same actor within 1 hour
    check: local DB query
    behavior: warn, ask confirmation
    message: "📋 Similar entry exists today"
    action: "Add anyway" or "Cancel"
```

---

## 7. GPS Quality Gate

```yaml
gps_quality_gate:
  
  for_parcel_mapping:
    minimum_accuracy: 15 meters
    display: live accuracy meter (green < 5m, yellow 5-15m, red > 15m)
    behavior_when_poor:
      - show "📍 Move to open area" message
      - disable "Save" button until accuracy improves
      - offer "Save without GPS" fallback (manual area entry)
    timeout: if accuracy doesn't improve in 60 seconds, offer fallback
  
  for_activity_logging:
    minimum_accuracy: 50 meters (less strict — just for audit)
    behavior_when_poor: capture anyway, flag as low_accuracy in audit metadata
  
  for_field_visit_checkin:
    minimum_accuracy: 30 meters
    radius_check: must be within 500m of assigned parcel centroid
    behavior_when_outside: warn "📍 You seem far from the farm" but allow override with reason
```

---

## 8. Master Data Staleness Handling

```yaml
master_data_validation:
  
  crop_master:
    max_staleness: 30 days
    behavior_when_stale: show warning "🔄 Crop list may be outdated" but allow selection
    refresh_trigger: on next connectivity, auto-refresh
  
  geography_villages:
    max_staleness: 90 days (geography changes rarely)
    behavior_when_stale: allow selection, no warning
  
  lifecycle_templates:
    max_staleness: 7 days (templates may change with tenant config)
    behavior_when_stale: show warning, suggest sync before creating new crop cycle
  
  validation_against_stale_data:
    rule: "Records created against stale master data are VALID for sync"
    server_behavior: "Server validates against current master data; returns VALIDATION_FAILED if reference no longer exists"
    client_recovery: "Show error, offer to re-select from refreshed data"
```

---

*End of Offline Form Validation Rules*
