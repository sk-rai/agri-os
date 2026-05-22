# Screen Information Architecture
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Farmer-Parcel Detail Screens, validated against Farmer Value Ladder and Semantic Registry  
**Purpose:** Define what information appears on key screens, role-based visibility rules, and interaction constraints — technology-agnostic.

---

## 1. Universal Screen Design Rules

```yaml
screen_design_rules:

  canonical_display:
    - internal storage uses canonical names (parcel, farmer, crop_cycle)
    - UI may show localized terms (khet, cultivator) via display alias layer
    - all buttons, APIs, sync payloads use canonical names only

  interaction_efficiency:
    - max_taps_to_critical_action: 3
    - critical_actions: [edit, sync, assign, escalate]
    - from any detail screen, user reaches critical action in ≤3 taps

  sync_status_visibility:
    - every screen header shows real-time sync status
    - sync badge is always visible (not hidden in settings)
    - tap on badge opens sync detail/action

  role_based_masking:
    farmer_sees: only their own data (parcels, cycles, costs)
    dealer_sees: assistance_mode, enrollment_source, territory, assigned farmers
    field_agent_sees: verification status, visit history, disease cases
    enterprise_sees: aggregated KPIs, territory metrics (never individual PII)

  audit_accessibility:
    - history/audit tab available on every entity detail screen
    - shows: actor, role, timestamp, GPS, operation type
    - immutable append-only display (no edit/delete on audit entries)

  offline_first_ux:
    - form saves locally immediately (no network call blocks UI)
    - shows "Saved on phone" confirmation instantly
    - queues for sync in background
    - never shows loading spinner waiting for server response on save
```

---

## 2. Farmer Detail Screen

### Header
- Farmer name (or "Unnamed Farmer" if not yet provided)
- Sync status badge (tappable → sync details)
- Quick actions: Edit, Assign Dealer, Sync Now, Escalate

### Quick Stats Row
- Parcels count
- Active crop cycles count
- Assistance mode badge (color-coded)
- Last sync timestamp (or "Never synced")

### Tab Navigation

| Tab | Content | Role Visibility |
|-----|---------|----------------|
| **Profile** | Mobile, village, language, irrigation type, enrollment metadata (dealer, date, GPS) | All roles |
| **Parcels** | List: name, area (ha), ownership type, sync status. Tap → parcel detail | All roles |
| **Crop Cycles** | List: crop name, current stage, sowing date, status badge. Tap → cycle detail | All roles |
| **Notifications** | System reminders, advisories, delivery status. Acknowledge/dismiss actions | Farmer + Dealer |
| **History** | Chronological audit log. Filter by actor, date, entity type. Export PDF/CSV | Dealer + Enterprise |

---

## 3. Parcel Detail Screen

### Header
- Parcel reference name (or truncated ID)
- Sync status + conflict alert (if geometry under review)
- Map preview thumbnail (tappable → full map)

### Quick Stats Row
- Area: X.XX ha
- Ownership: badge (OWNED / LEASED / SHARED)
- Irrigation: badge (RAINFED / DRIP / etc.)
- Soil type (if available)

### Tab Navigation

| Tab | Content | Role Visibility |
|-----|---------|----------------|
| **Details** | Boundary metadata (points, GPS accuracy, capture method), linked farmer, village, district | All roles |
| **Map View** | Offline-cached polygon overlay. Edit boundary (dealer/agent only). Overlap warnings if >5% | All roles (edit: dealer/agent) |
| **Crop Cycles** | Timeline of all seasons on this parcel. Tap → cycle detail | All roles |
| **Soil & Environment** | Soil health cards (OCR params, dates). Environmental events (rainfall, hail, drought) | All roles |
| **History** | Boundary changes, ownership updates, sync conflicts, resolution notes | Dealer + Enterprise |

---

## 4. Crop Cycle Detail Screen

### Header
- Crop name + variety
- Status badge (ACTIVE / COMPLETED / ABANDONED)
- Sync status

### Quick Stats Row
- Current stage name
- Days since sowing
- Expected harvest date
- Total cost logged (if any)

### Tab Navigation

| Tab | Content | Role Visibility |
|-----|---------|----------------|
| **Timeline** | Visual stage progression (completed ✅, current 🔵, upcoming ⚪). One-tap stage completion | All roles |
| **Activities** | Fertilizer/pesticide/irrigation logs. Tap to add new | All roles |
| **Economics** | Cost summary by category, yield (if harvested), net profit | Farmer + Dealer |
| **Advisories** | Disease reports, expert advisories linked to this cycle | All roles |
| **History** | Stage transitions, activity logs, conflict resolutions | Dealer + Enterprise |

---

## 5. Role-Based Field Visibility Matrix

| Field | Farmer | Dealer | Field Agent | Agronomist | Enterprise |
|-------|--------|--------|-------------|------------|-----------|
| farmer.mobile_number | ✅ Own | ✅ Assigned | ✅ Territory | ❌ | ❌ |
| farmer.government_id | ❌ | ✅ | ✅ | ❌ | ❌ |
| parcel.geometry | ✅ Own | ✅ Assigned | ✅ Territory | ✅ | Aggregated only |
| crop_cycle.cost_entries | ✅ Own | ✅ Assigned | ❌ | ❌ | Aggregated only |
| disease_report.images | ✅ Own | ✅ | ✅ | ✅ | ❌ |
| audit_event.gps | ❌ | ✅ | ✅ | ❌ | ✅ |
| analytics.individual_kpi | ✅ Own | ✅ Assigned | ❌ | ❌ | ❌ |
| analytics.aggregated_kpi | ❌ | Territory | Territory | Territory | ✅ All |

---

## 6. Empty State Design

Every screen must define behavior when no data exists:

```yaml
empty_states:

  farmer_detail.parcels_tab:
    message: "No parcels mapped yet"
    action_button: "Map your first parcel"
    icon: map_outline

  farmer_detail.crop_cycles_tab:
    message: "No crops registered"
    action_button: "Start a crop cycle"
    icon: seedling
    prerequisite_check: if no parcels exist, show "Map a parcel first"

  parcel_detail.crop_cycles_tab:
    message: "No crops on this parcel yet"
    action_button: "Register a crop"
    icon: agriculture

  parcel_detail.soil_tab:
    message: "No soil data available"
    action_button: "Upload soil health card"
    icon: science

  crop_cycle.activities_tab:
    message: "No activities logged"
    action_button: "Log fertilizer application"
    icon: add_circle
```

---

*End of Screen Information Architecture*
