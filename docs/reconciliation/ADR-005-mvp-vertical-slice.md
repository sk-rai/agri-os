# ADR-005: MVP Vertical Slice — Minimal Farmer Crop Lifecycle

**Status:** DECIDED  
**Date:** May 21, 2026  
**Purpose:** Define the first executable vertical slice that proves operational reality.

---

## Context

Architecture-heavy projects fail when they remain beautifully documented but impossible to execute incrementally. The platform needs a thin, fully working path that validates the core assumptions.

## Decision

### The First Vertical Slice: "Farmer Registers, Grows Crop, Gets Advisory"

This slice includes ONLY:

```yaml
mvp_vertical_slice:

  farmer_enrollment:
    - mobile_number_registration (60 seconds)
    - village_selection
    - primary_crop_selection
    - assistance_mode_assignment

  parcel_creation:
    - parcel_name
    - approximate_area (manual entry)
    - irrigation_type
    - GPS_point (single pin, NOT polygon — polygon is optional enhancement)

  crop_lifecycle:
    - crop_selection (from master catalog)
    - variety_selection
    - lifecycle_template_assignment (3-5 stages only for MVP)
    - one_tap_stage_completion
    - basic_activity_logging (type + date + optional cost)

  advisory_flow:
    - disease_photo_upload (photo + crop selection only)
    - agronomist_review (web dashboard)
    - advisory_response (push + SMS)

  notification:
    - stage_reminder (push + SMS)
    - disease_advisory_delivery
    - weather_alert (block-level)

  offline_sync:
    - local_persistence_for_all_above
    - background_sync_on_connectivity
    - conflict_detection (last-write-wins for MVP, manual review for parcels)
    - sync_status_visibility

  enterprise_dashboard:
    - farmer_count_by_territory
    - crop_stage_distribution
    - disease_report_queue
    - basic_map_view (farmer locations)
```

### What Is Explicitly EXCLUDED from First Slice

```yaml
excluded_from_first_slice:
  - GPS_polygon_mapping (single pin is sufficient)
  - full_economics_tracking (basic cost only)
  - benchmarking_analytics
  - profitability_calculations
  - NDVI_satellite
  - AI_disease_detection
  - complex_conditional_branching
  - mergeable_stages
  - campaign_management
  - content_management
  - OCR_soil_card
  - demo_plot_workflows
  - insurance_workflows
  - advanced_geospatial (heatmaps, clustering)
  - multi_tenant_configuration_UI
  - report_generation
```

### Success Criteria for First Slice

```yaml
success_criteria:
  - farmer_can_register_in_60_seconds
  - farmer_can_complete_stage_update_in_one_tap
  - farmer_receives_first_advisory_within_24_hours_of_disease_report
  - dealer_can_enroll_10_farmers_in_30_minutes
  - all_operations_work_offline
  - sync_completes_within_60_seconds_on_3G
  - enterprise_dashboard_shows_real_data_within_5_seconds
  - 10_farmers_can_complete_workflows_without_assistance
```

## Rationale

This slice validates:
1. Offline-first actually works end-to-end
2. Farmers will actually use one-tap stage updates
3. Advisory flow delivers value within 24 hours
4. Dealers can efficiently manage multiple farmers
5. Enterprise dashboard shows meaningful data
6. Sync handles real-world connectivity patterns

If this slice works, everything else is incremental addition. If it doesn't, no amount of additional architecture will save the platform.

---

*End of ADR-005*
