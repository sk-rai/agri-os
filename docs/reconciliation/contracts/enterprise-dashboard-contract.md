# Enterprise Dashboard Behavioral Contract
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Enterprise Web Dashboard Specification  
**Depends on:** ADR-008 (Analytics Freshness), Screen Information Architecture, KPI Registry, Security Framework  
**Purpose:** Define widget rendering rules, KPI display contracts, geospatial view behavior, export specifications, and caching strategy for the enterprise web dashboard.

---

## 1. Dashboard Principles

```yaml
dashboard_principles:
  - role_first: widgets rendered based on user role + territory scope
  - workflow_aware: KPIs respect configurable lifecycle templates (never hardcode stages)
  - canonical_kpi: all metrics pulled from KPI Registry v1 (never hardcoded formulas in frontend)
  - confidence_visible: every metric shows confidence_score + freshness_timestamp
  - sync_health_exposed: dashboard shows sync status per territory (synced, pending, conflicted)
  - tenant_isolated: never render data outside user's tenant + territory scope
  - never_block_ui: show cached/stale data with badge rather than loading spinners
```

---

## 2. Widget Resolution Logic

```yaml
widget_resolution:
  input: [user_role, tenant_id, territory_scope, device_type]
  
  process:
    1: load widget_catalog from dashboard_config (tenant-specific if overrides exist)
    2: filter by role_visibility_rules
    3: filter by territory_scope (user only sees their geography)
    4: apply tenant_overrides (custom widgets, disabled widgets)
    5: sort by priority_weight (critical operational widgets first)
  
  output: ordered widget array for rendering
  
  rendering_order:
    - above-fold widgets render first (KPI cards, sync status)
    - below-fold widgets deferred until scroll (lazy loading)
    - skeleton placeholders shown during fetch
```

---

## 3. Role-Based Widget Visibility Matrix

| Widget | Farmer | Dealer | Field Agent | Agronomist | Enterprise Manager | Admin |
|--------|--------|--------|-------------|------------|-------------------|-------|
| Personal sync status | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Active crop cycles | ✅ own | ✅ assigned | ✅ territory | ✅ territory | ✅ regional | ✅ global |
| KPI performance cards | ✅ profitability | ✅ update rate | ✅ visit coverage | ✅ advisory resolution | ✅ yield/cost benchmarks | ✅ system health |
| Geospatial map | ❌ | ✅ assigned parcels | ✅ territory | ✅ territory | ✅ district/region | ✅ all tenants |
| Pending tasks queue | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Disease/advisory feed | ✅ own | ✅ assigned | ✅ territory | ✅ regional | ✅ hotspots only | ✅ system |
| Export/report builder | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Dealer performance | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| System health/monitoring | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 4. KPI Card Display Contract

Every KPI card on the dashboard must include:

```yaml
kpi_card_schema:
  kpi_id: canonical identifier from KPI Registry v1
  display_value: formatted number with unit (e.g., "2,450 kg/ha")
  trend_indicator:
    direction: up | down | flat
    percentage: float (e.g., +12.5%)
    period: 7d | 30d | season
  confidence_score: 0-100% (from ADR-008 analytics freshness model)
  freshness_badge: "Live" | "15m ago" | "Stale (>24h)"
  drilldown_path: link to detailed analytics view with filters preserved

  display_rules:
    if confidence_score < 50%: show warning icon + "Partial Data" label
    if freshness_badge == "Stale": gray background + disable drilldown
    if confidence_score >= 80%: normal display (green confidence indicator)
```

---

## 5. Aggregation & Benchmarking Rules

```yaml
aggregation_rules:

  weighted_averages_mandatory:
    - NEVER use simple average for yield or cost metrics
    - ALWAYS weight by cultivated_area_hectares or active_cycle_count
    - example: regional_yield = SUM(harvest_kg) / SUM(area_hectares)

  benchmark_comparisons:
    allowed_comparisons:
      - district_average
      - same_crop_same_soil_cohort
      - tenant_historical_baseline
    display: percentile ranking (e.g., "Top 20% in District")
    forbidden: NEVER compare across different lifecycle_templates without normalization

  drilldown_cascade:
    path: KPI card → geography filter → crop filter → template filter → parcel list → audit trail
    rule: each step preserves tenant_isolation AND role_visibility
    breadcrumb: always show current filter context
```

---

## 6. Geospatial View Rules

### Layer Hierarchy

```yaml
map_layers:
  base: OpenStreetMap or satellite imagery
  layer_1: territory boundaries (district/village polygons)
  layer_2: parcel polygons (color-coded by crop status)
  layer_3: heatmap overlays (disease, profitability, advisory adoption)
  layer_4: agent routes / field visit markers (optional)
```

### Zoom-Level Rendering

| Zoom Level | Display |
|-----------|---------|
| < 8 (state/district view) | District/village aggregates (counts, averages) |
| 8-12 (district/village view) | Parcel centroids + crop status badges |
| > 12 (village/parcel view) | Full parcel polygons + stage instance markers |

Click interaction: drilldown to parcel detail screen

### Geospatial Performance Rules

```yaml
map_performance:
  vector_tiles: use PostGIS ST_AsMVT for parcel geometry
  tile_caching: Redis with 1-hour TTL
  client_side: load tiles progressively, debounce zoom events
  heatmaps: aggregate at village level for zoom < 10 (never render raw parcels in heatmap mode)
  
  security:
    - ALL map queries include tenant_id + territory_scope filter
    - NEVER return cross-territory or cross-tenant parcels
    - heatmap aggregation prevents individual parcel identification at low zoom
```

---

## 7. Export & Reporting Contract

### Export Workflow

```yaml
export_workflow:
  trigger: user requests PDF/Excel/CSV
  
  validation:
    - row_count <= 50,000 (if exceeded → queue async job)
    - tenant_isolation verified (no cross-tenant data leak)
    - canonical field names used (no internal aliases exposed)
    - PII masking applied per role permissions
  
  processing:
    - generate async job_id
    - push to background worker queue
    - notify user when complete (in-app notification)
  
  delivery:
    - signed download URL (TTL = 24 hours)
    - audit event logged: actor, timestamp, filters applied, format, row count
```

### Format Specifications

| Format | Purpose | Content Rules |
|--------|---------|---------------|
| **PDF** | Executive summaries, program reports | Aggregated KPIs, geospatial snapshots, trend charts. Tenant watermark + export timestamp in footer |
| **Excel** | Analyst deep-dives, data pivots | Tabular data, multiple tabs (KPIs, parcels, cycles), pivot-ready structure. Column headers match Data Dictionary |
| **CSV** | Machine-readable integrations, ETL | Flat file, UTF-8, comma-delimited, ISO-8601 timestamps, tenant_id in every row |

### PII Rules in Exports

```yaml
export_pii_rules:
  mobile_number: masked (last 4 digits only)
  government_id: NEVER exported
  gps_coordinates: rounded to district level UNLESS agronomist role with explicit permission
  farmer_name: included only if role has FARMER_READ access
  
  audit: export scope + actor permissions logged BEFORE generation
```

---

## 8. Dashboard Caching Strategy

```yaml
caching_rules:

  widget_level:
    kpi_cards: cache 5 minutes OR until sync_completed event
    map_tiles: cache 1 hour OR until territory_boundary_change
    export_results: cache 24 hours OR until data freshness drops below threshold
    pending_tasks: cache 1 minute (near real-time)

  invalidation_triggers:
    - sync_completed event → invalidate KPI cards + sync status widgets
    - territory_switch by user → clear ALL widget caches, reload from scratch
    - configuration_change event → invalidate affected widgets
    - manual_refresh by user → force refetch all visible widgets

  stale_tolerance:
    if backend slow OR sync delayed:
      - show cached data WITH "Last updated: X min ago" badge
      - allow user interactions (mark mutations as pending)
      - NEVER block dashboard load for real-time accuracy
```

---

## 9. Widget Lifecycle Events

```yaml
widget_lifecycle:

  on_dashboard_load:
    - fetch role-scoped widgets in parallel
    - apply client-side caching (check TTL)
    - render skeleton loaders until data resolved
    - above-fold widgets prioritized

  on_sync_completed_event:
    - invalidate affected widgets (KPI, sync status, pending tasks)
    - refetch ONLY changed widgets (not full dashboard reload)
    - animate value transitions (old → new) for KPI cards

  on_territory_switch:
    - clear ALL widget caches
    - reload from scratch with new scope
    - show loading state for all widgets simultaneously

  on_filter_change:
    - refetch affected widgets with new filter parameters
    - preserve unaffected widget cache
    - update URL query params for shareable state
```

---

## 10. Mobile Responsiveness Requirements

```yaml
responsive_rules:
  breakpoints:
    desktop: >= 1024px (full widget grid, side-by-side map + data)
    tablet: 768-1023px (stacked widgets, collapsible map)
    mobile: < 768px (single column, KPI cards only, map as separate tab)

  mobile_specific:
    - KPI cards: show top 3 only, "See all" link for rest
    - map: full-screen mode with overlay controls
    - export: simplified (PDF summary only, no Excel pivot)
    - tables: horizontal scroll with sticky first column
```

---

## 11. Dashboard Invariants

```yaml
dashboard_invariants:
  - all_widgets_reference_canonical_kpi_ids (never hardcoded formulas in frontend)
  - all_queries_include_tenant_id_and_territory_scope
  - all_kpi_cards_display_confidence_score_and_freshness
  - all_exports_log_audit_event_before_generation
  - all_map_queries_enforce_spatial_tenant_isolation
  - never_compare_across_lifecycle_templates_without_normalization
  - never_block_dashboard_load_waiting_for_real_time_data
  - never_expose_individual_farmer_PII_to_enterprise_role (aggregates only)
  - role_visibility_matrix_enforced_at_widget_resolution (not just UI hiding)
  - export_pii_masking_applied_server_side (not client-side filtering)
```

---

*End of Enterprise Dashboard Behavioral Contract*
