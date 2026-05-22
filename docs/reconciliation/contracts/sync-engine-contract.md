# Sync Engine Behavioral Contract
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 SyncManager + Conflict Resolver implementation, validated against ADR-006, ADR-007  
**Purpose:** Define the exact behavioral contract for the mobile sync engine — how it queues, batches, retries, resolves conflicts, and handles dependencies.

---

## 1. Sync Engine Responsibilities

```yaml
sync_engine_owns:
  - queue_management (persistent, survives reboots)
  - dependency_ordering (parent entities sync before children)
  - batch_construction (group items for efficient upload)
  - retry_with_backoff (exponential, capped, with jitter)
  - conflict_routing (dispatch to appropriate resolver)
  - terminal_state_management (FAILED after max retries)
  - connectivity_detection (trigger sync on network restore)
  - user_visibility (expose queue status to UI)

sync_engine_does_not_own:
  - workflow_validation (server-side, via Workflow Engine)
  - conflict_resolution_decisions (server decides strategy)
  - notification_dispatch (separate module)
  - analytics_recalculation (separate module)
```

---

## 2. Queue Processing Algorithm

```yaml
process_queue:
  trigger:
    - connectivity_restored
    - app_foregrounded
    - periodic_background_task (every 15 minutes)
    - manual_user_retry

  steps:
    1_fetch_eligible:
      query: "sync_queue WHERE retry_count < max_retries AND next_retry_after <= NOW()"
      order_by: [priority ASC, created_at ASC]
      limit: 20 (batch_size, configurable)

    2_filter_dependencies:
      for_each_item:
        if dependency_ids is empty: eligible
        if all dependencies have sync_status = SYNCED: eligible
        else: skip (reschedule for later)

    3_construct_batch:
      format: array of SyncEvent objects per API contract
      max_items: 20 per request

    4_dispatch:
      endpoint: POST /sync/events
      headers: [X-Tenant-ID, X-Device-ID, Authorization]
      timeout: 30 seconds

    5_process_response:
      accepted: mark SYNCED, remove from active queue
      conflicts: mark CONFLICTED, route to conflict resolver
      failed_retryable: increment retry_count, calculate next_retry
      failed_non_retryable: mark FAILED (terminal)

    6_handle_network_error:
      mark all batch items for retry
      increment retry_count
      calculate next_retry with backoff
```

---

## 3. Retry Policy (Concrete Implementation)

```yaml
retry_policy:
  strategy: exponential_backoff_with_jitter
  
  formula: "next_retry = NOW() + min(30s × 2^retry_count + random(0-5s), 24h)"
  
  examples:
    retry_1: ~30 seconds
    retry_2: ~60 seconds
    retry_3: ~2 minutes
    retry_4: ~4 minutes
    retry_5: ~8 minutes
    retry_6: ~16 minutes
    retry_7: ~32 minutes
    retry_8: ~64 minutes (~1 hour)
    retry_9: ~128 minutes (~2 hours)
    retry_10: FAILED (terminal, moved to dead letter)

  max_retries: 10 (configurable per entity_type)
  max_backoff: 24 hours (cap)
  jitter: 0-5 seconds random (prevents thundering herd)

  terminal_behavior:
    after_max_retries:
      sync_status: FAILED
      user_visibility: show "Sync failed" with action options
      options: [retry_manually, ask_dealer_for_help, delete_record]
```

---

## 4. Dependency Ordering Contract

```yaml
dependency_ordering:
  principle: "Parent entities must sync before children"
  
  dependency_chain:
    level_1: farmer (no dependencies)
    level_2: parcel (depends on farmer)
    level_3: crop_cycle (depends on farmer + parcel)
    level_4: stage_instance (depends on crop_cycle)
    level_5: crop_activity (depends on stage_instance)

  enforcement:
    client_side:
      - each sync_queue item carries dependency_ids
      - queue processor skips items whose dependencies aren't SYNCED
      - skipped items rescheduled (not counted as retry failure)
    
    server_side:
      - server returns DEPENDENCY_MISSING error if referenced entity doesn't exist
      - client treats as retryable (dependency will sync eventually)

  edge_case:
    circular_dependency: impossible by design (hierarchy is acyclic)
    dependency_permanently_failed: child items also marked FAILED after parent exhausts retries
```

---

## 5. Conflict Resolution Routing

```yaml
conflict_routing:
  
  version_mismatch:
    meaning: "Server has newer version than client submitted"
    auto_resolvable: sometimes (if non-overlapping field changes)
    action:
      - fetch server version
      - attempt semantic merge (non-conflicting fields)
      - if merge succeeds: resubmit merged version
      - if merge fails: route to manual review
    user_visibility: "Your update conflicts with a newer version"

  geospatial_overlap:
    meaning: "Parcel geometry overlaps existing parcel by >5%"
    auto_resolvable: never (per ADR-007, parcel geometry always manual review)
    action:
      - mark CONFLICTED
      - store both geometries locally
      - show side-by-side map comparison to user
      - options: keep_mine, keep_server, ask_dealer
    user_visibility: "Your parcel boundary overlaps another parcel"

  workflow_invalid:
    meaning: "Stage transition violates lifecycle template state machine"
    auto_resolvable: never (workflow engine is authoritative)
    action:
      - mark FAILED (not retryable — transition is permanently invalid)
      - preserve local data (never discard farmer work)
      - show explanation: "This stage can't be completed yet because [reason]"
      - offer: "Go back and fix" or "Ask agronomist for help"
    user_visibility: "This crop stage update wasn't accepted"

  unknown_conflict:
    action: route to manual review queue
    user_visibility: "Something needs your attention"
```

---

## 6. Background Execution Contract

```yaml
background_sync:
  technology: flutter_workmanager (Android) / BGTaskScheduler (iOS)
  
  periodic_task:
    frequency: every 15 minutes
    constraint: network_connected
    behavior: call processQueue(batchSize=20)
  
  connectivity_trigger:
    on_wifi_or_mobile_restored: immediate processQueue()
    debounce: 5 seconds (avoid rapid fire on flaky connections)
  
  foreground_trigger:
    on_app_resume: processQueue() if last_sync > 5 minutes ago
    on_manual_retry: processQueue() immediately
  
  battery_awareness:
    low_battery (<15%): defer non-critical syncs
    critical_battery (<5%): sync only CRITICAL priority items
```

---

## 7. Idempotency Guarantees

```yaml
idempotency:
  client_side:
    - event_id generated once per mutation (UUID v4)
    - InsertMode.insertOrIgnore prevents duplicate queue entries
    - same event_id never regenerated (even on retry)
  
  server_side:
    - server deduplicates by event_id
    - duplicate event_id with same payload: return 200 (accepted, no-op)
    - duplicate event_id with different payload: return 409 (conflict)
  
  consequence:
    - processQueue() is safe to call multiple times
    - network timeouts don't cause duplicate server mutations
    - app restarts don't re-enqueue already-queued items
```

---

## 8. User-Facing Sync Status Contract

```yaml
sync_status_display:
  
  LOCAL_ONLY:
    icon: 🟢
    label: "Saved on phone"
    color: green
    action: none (auto-queues on next cycle)
  
  QUEUED_FOR_SYNC:
    icon: 🔄
    label: "Waiting for internet"
    color: blue
    action: none (auto-syncs when online)
  
  SYNCING:
    icon: ⬆️
    label: "Sending..."
    color: blue (animated)
    action: none
  
  SYNCED:
    icon: ✅
    label: "Saved to server"
    color: green
    action: none (success state)
  
  CONFLICTED:
    icon: 🔴
    label: "Needs attention"
    color: red
    action: tap to open conflict resolution UI
    badge: show count on home screen
  
  FAILED:
    icon: ⚠️
    label: "Sync failed"
    color: orange
    action: "Retry" button + "Get help" option
    detail: show last_error in plain language

  aggregate_indicator:
    location: app header / status bar
    shows: "3 pending · 1 conflict" (summary of non-synced items)
```

---

## 9. Validation Against ADRs

| ADR | Sync Engine Compliance |
|-----|----------------------|
| ADR-001 (Monolith) | Single API endpoint for sync, no inter-service calls | ✅ |
| ADR-005 (MVP Slice) | Only slice entities synced | ✅ |
| ADR-006 (Retry) | Exponential backoff, max 10, terminal FAILED state | ✅ |
| ADR-007 (Conflict) | Geospatial → manual review, workflow → reject, version → merge attempt | ✅ |
| ADR-009 (Temporal) | local_timestamp preserved as observation_time | ✅ |
| Semantic Registry | Entity types use canonical SCREAMING_SNAKE_CASE enums | ✅ |

---

## 10. Testing Requirements

```yaml
sync_engine_tests:
  
  unit_tests:
    - backoff_calculation_correctness (verify exponential + jitter + cap)
    - dependency_filtering (parent unsynced → child skipped)
    - max_retry_terminal (retry 10 → FAILED)
    - idempotency (duplicate enqueue → single queue entry)
  
  integration_tests:
    - happy_path (enqueue → processQueue → SYNCED)
    - conflict_routing (server returns conflict → CONFLICTED state)
    - network_failure (timeout → retry with backoff)
    - dependency_chain (farmer → parcel → crop_cycle in order)
  
  chaos_tests:
    - 48h_offline (queue persists, syncs on restore, zero data loss)
    - flaky_network (50% failure rate → eventual sync, no duplicates)
    - concurrent_sync (two processQueue() calls → no race condition)
    - app_kill_during_sync (queue intact on restart)
```

---

## 11. Conflict Resolution UI Contract (Technology-Agnostic)

The conflict resolution screen must follow these behavioral rules regardless of implementation technology:

### Screen Structure

```yaml
conflict_resolution_screen:

  header:
    title: "Resolve Data Difference"
    accent_color: orange/warning
    close_button: always visible (user can dismiss without resolving)

  explanation:
    text: "Two versions exist for this [entity_type]. Choose which to keep."
    subtext: "All choices are saved for audit."
    language: plain, no technical jargon
    literacy_level: understandable without reading (icons supplement text)

  comparison:
    layout: side-by-side cards (or stacked on small screens)
    local_version:
      label: "Your version" or "📱 Your offline version"
      accent: blue
      shows: key fields with values (not raw JSON)
    server_version:
      label: "Server version" or "☁️ Updated version"
      accent: green
      shows: same fields for direct comparison
    highlight_differences: conflicting fields visually marked (bold, color)

  actions:
    primary_options:
      - "Keep my version" (keep_local)
      - "Use server version" (keep_server)
      - "Combine both" (merge_both) — only if semantic merge is possible
    secondary_option:
      - "Ask dealer to decide" (ask_dealer) — escalation path
    
    behavior:
      - single tap to select (no confirmation dialog for simple choices)
      - loading state while resolving (prevent double-tap)
      - success feedback: snackbar/toast "Conflict resolved ✓"
      - return to previous screen after resolution

  audit_on_resolution:
    logged_fields:
      - event_id
      - resolution_action (keep_local | keep_server | merge_both | ask_dealer)
      - resolved_by (actor_id)
      - resolved_at (timestamp UTC)
      - conflict_type
    rule: resolution is logged BEFORE queue status is updated
```

### Entity-Specific Conflict UI

```yaml
conflict_ui_by_entity:

  parcel_geometry:
    comparison: map view showing both boundaries overlaid
    local_boundary: blue outline
    server_boundary: green outline
    overlap_area: highlighted in orange
    options: [keep_mine, keep_server, ask_dealer]
    note: "Combine both" NOT available for geometry (too complex for field users)

  farmer_profile:
    comparison: field-by-field table
    highlight: only differing fields shown (identical fields collapsed)
    options: [keep_mine, keep_server, merge_both, ask_dealer]
    merge_behavior: non-conflicting fields auto-merged, conflicting fields shown for choice

  crop_stage:
    comparison: timeline showing both versions
    explanation: "You marked [stage] as [status], but server shows [different_status]"
    options: [keep_mine, keep_server, ask_dealer]
    note: if workflow_invalid, show explanation of WHY transition was rejected

  fertilizer_log:
    comparison: not applicable (append-only, conflicts are duplicates)
    explanation: "This entry may be a duplicate"
    options: [keep_both, remove_duplicate]
```

### Accessibility Requirements

```yaml
conflict_ui_accessibility:
  - touch_targets: minimum 48x48dp
  - color_not_sole_indicator: icons + labels supplement color coding
  - font_size: minimum 14sp for body, 16sp for labels
  - contrast_ratio: minimum 4.5:1 (WCAG AA)
  - screen_reader: all buttons have descriptive labels
  - one_handed_operation: action buttons reachable with thumb
  - no_time_pressure: conflict screen has no timeout (user resolves at their pace)
```

---

## 12. Post-Resolution Behavior

```yaml
post_resolution:
  
  keep_local:
    action: re-queue sync event with force_override flag
    server_behavior: accept client version, supersede server version
    audit: log supersession with resolution_source = "user_manual_review"

  keep_server:
    action: update local entity with server values, mark SYNCED
    local_behavior: overwrite local fields with server data
    audit: log acceptance with resolution_source = "user_accepted_server"

  merge_both:
    action: construct merged payload (non-conflicting from both, user-chosen for conflicts)
    re_queue: merged version submitted as new sync event
    audit: log merge with field-level choices

  ask_dealer:
    action: create dealer_callback_task with conflict context
    local_state: remains CONFLICTED until dealer resolves
    dealer_sees: conflict details in their task queue
    sla: 24 hours for routine, 4 hours for critical entities
    timeout: if dealer doesn't resolve within SLA → escalate to territory manager
```

---

*End of Sync Engine Behavioral Contract*
