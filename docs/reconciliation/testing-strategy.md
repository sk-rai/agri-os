# Testing Strategy & Rural UX Validation Protocol
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Testing Strategy & Rural UX Protocol  
**Purpose:** Define testing pyramid, offline chaos scenarios, rural UX validation protocol, and go/no-go launch criteria.

---

## 1. Testing Philosophy

```yaml
testing_principles:
  - offline_first: ALL mobile workflow tests must execute in online, offline, intermittent, and post-reconnect modes
  - rural_ux_mandatory: NO feature ships without low-literacy validation
  - audit_invariant: EVERY mutation test asserts actor_id, timestamp, GPS, tenant_id, chain_hash
  - semantic_compliance: EVERY test validates canonical terminology (no forbidden aliases)
  - pyramid_enforced: 70% unit, 25% integration/contract, 5% E2E/rural UX
```

---

## 2. Test Pyramid

| Layer | Coverage Target | Focus | Tools (Suggested) |
|-------|----------------|-------|-------------------|
| **Unit** (70%) | ≥80% domain logic | Validators, state machines, rules engine, form validation | pytest, flutter_test |
| **Integration** (25%) | Module boundaries | Sync flow, API contracts, event schemas, conflict resolution | schemathesis, toxiproxy |
| **E2E / Rural UX** (5%) | Full user journeys | Minimal Farmer Crop Lifecycle, real farmer scenarios | Manual + automated screenshots |

---

## 3. Unit Testing Rules

### What Must Be Unit Tested

```yaml
unit_test_coverage:
  
  form_validators:
    - farmer enrollment (mobile format, duplicate check, enum validation)
    - parcel creation (polygon validity, area threshold, GPS accuracy)
    - crop cycle (template existence, date bounds)
    - stage transition (state machine compliance)
    - activity logging (quantity bounds, date range, duplicate detection)
  
  state_machines:
    - all 14 state machines: every valid transition returns success
    - every invalid transition returns specific error code
    - timeout transitions fire at correct thresholds
    - cascade rules execute on parent state changes
  
  rules_engine:
    - each MVP rule (RULE-001 through RULE-043) evaluated with test context
    - conditions met → correct action payload returned
    - conditions not met → null returned (no action)
    - idempotent evaluation (same input → same output)
  
  sync_logic:
    - backoff calculation correctness (exponential + jitter + cap)
    - dependency filtering (parent unsynced → child skipped)
    - max retry terminal (retry 10 → FAILED)
    - idempotency (duplicate enqueue → single queue entry)
    - deduplication (SHA-256 hash match → skip)
```

---

## 4. Integration Testing Rules

### Module Boundary Tests

```yaml
integration_tests:

  farmer_to_parcel_dependency:
    setup: farmer + parcel created offline, farmer sync fails first
    assert: parcel retries after farmer succeeds, no orphan records, audit has correlation_id

  workflow_to_notification:
    setup: crop_stage_completed event published
    assert: rules engine evaluates → notification queued → SMS tracked → dealer dashboard updated

  conflict_resolution_flow:
    setup: same parcel edited on two devices offline, both sync
    assert: server detects conflict → sync response has conflict_type → local marks CONFLICTED → UI routes to resolution

  offline_queue_persistence:
    setup: 10 mutations queued, app killed, restarted, connectivity restored
    assert: all 10 attempted, retry_count incremented for failures, DLQ captures poison events
```

### Contract Tests

```yaml
contract_tests:

  openapi_validation:
    - every MVP endpoint tested against OpenAPI spec
    - response schemas match definitions
    - error responses follow RFC 7807
    - audit fields present in all mutation responses

  semantic_registry_enforcement:
    - scan all API schemas for forbidden aliases (field, plot, khet)
    - scan all event payloads for non-canonical entity types
    - fail build on any violation

  event_schema_compatibility:
    - v1 consumers process v1 events successfully
    - v1 consumers process v2 events (additive changes) successfully
    - breaking changes rejected by schema validation
```

---

## 5. Offline Sync Chaos Testing Protocol

### Scenarios (Must Pass Before Launch)

| Scenario | Setup | Assert |
|----------|-------|--------|
| **48h network partition** | Create farmer + parcel + crop offline, simulate 48h no connectivity, restore | Zero data loss, all records sync, audit trail complete |
| **Concurrent offline edits** | Same parcel edited on Device A and B with different geometries, both sync | Conflict detected, routed to manual review, both versions preserved |
| **Dependency ordering violation** | Force crop_activity sync before crop_cycle | Server rejects DEPENDENCY_MISSING, client re-queues with dependency wait |
| **Retry backoff validation** | 5 events queued, 50% network failure rate | Exponential backoff observed, no duplicate server mutations, DLQ after max retries |
| **Low bandwidth (2G)** | Upload parcel + 3 images on 50kbps | Images ≤500KB each, metadata syncs before media, progress shown, partial upload resumes |
| **App kill during sync** | Kill app mid-sync, restart | Queue intact, no partial server state, resumes cleanly |
| **Sync storm (50 devices)** | 50 dealers sync simultaneously after connectivity restore | Server handles burst, no timeouts, no data loss, all audit entries unique |

---

## 6. Rural UX Validation Protocol

### Participant Recruitment

```yaml
participants:
  total: 15 minimum
  
  segments:
    smartphone_farmers: 5
      criteria: owns Android, uses WhatsApp, can read simple Hindi/English
    
    feature_phone_farmers: 5
      criteria: basic phone (SMS/calls only), low/no literacy, relies on dealer
    
    assisted_digital_dealers: 5
      criteria: manages 10+ farmers, uses smartphone for business, moderate literacy
  
  geography:
    - 2 villages per district (capture regional variation)
    - mix of irrigated + rainfed areas
    - include at least 1 remote/low-connectivity village
```

### Core Test Scenarios

| Scenario | Participants | Task | Success Criteria |
|----------|-------------|------|-----------------|
| **Farmer enrollment (low literacy)** | Feature-phone farmer + dealer | Dealer enrolls farmer via assisted workflow | Farmer confirms enrollment without reading text; dealer completes in <3 min; audit captures actor/subject |
| **Parcel mapping (poor GPS)** | Field agent + farmer | Map parcel with GPS accuracy challenges | Agent understands GPS guidance; polygon validates locally; offline save confirmed with icon |
| **Conflict resolution (plain language)** | Dealer + farmer | Resolve parcel boundary conflict | Zero technical terms exposed; farmer makes choice confidently with dealer help; resolution audited |
| **SMS advisory (feature phone)** | Feature-phone farmer | Receive and reply to fertilizer reminder | SMS ≤160 chars, local language; reply keyword works; acknowledgment tracked without app |
| **Sync status visibility** | Low-literacy farmer | Understand sync indicators | All indicators use icon+color+≤3 words; farmer distinguishes "saved locally" vs "sent to server" |
| **Batch enrollment (dealer)** | Dealer | Enroll 5 farmers in one session offline | Completed in <10 minutes; all queued correctly; no duplicates |

### Success Thresholds

```yaml
rural_ux_pass_criteria:
  task_completion_rate: ≥ 80%
  error_recovery_rate: ≥ 70% (can recover from mistakes without external help)
  terminology_comprehension: 100% (zero forbidden internal terms exposed)
  assisted_workflow_efficacy: ≥ 90% (dealer+farmer pairs succeed)
  icon_recognition_rate: ≥ 85% (icons understood without text labels)
  satisfaction_score: ≥ 4.0/5.0 (post-test survey, translated, icon-assisted)
```

---

## 7. Multi-Role Permission Testing

```yaml
permission_tests:

  tenant_isolation:
    - user_A (tenant_X) queries data → only tenant_X results
    - user_A attempts tenant_Y access → 403 + audit log entry

  territory_scoping:
    - dealer queries assigned villages → correct results
    - dealer attempts unassigned village → 403 + audit log

  assisted_digital_attribution:
    - dealer logs activity for farmer → audit has actor=dealer, subject=farmer
    - analytics by farmer uses subject_id
    - analytics by dealer performance uses actor_id

  role_dashboard_visibility:
    - farmer login → sees personal data only
    - enterprise login → sees aggregated KPIs, never individual PII
```

---

## 8. Geospatial Validation Tests

```yaml
geospatial_tests:

  polygon_validation:
    - valid closed polygon (≥4 points, first=last) → accepted
    - open polygon (<4 points) → rejected with "🗺️ Draw complete boundary"
    - self-intersecting polygon → rejected

  area_calculation_consistency:
    - local calculation vs server PostGIS calculation → difference < 0.01 ha

  overlap_detection:
    - new parcel overlaps existing by >5% → conflict_type = geospatial_overlap
    - overlap <5% + high trust score → auto-merge (configurable)

  spatial_query_isolation:
    - same spatial query by different tenants → only own-tenant parcels returned
```

---

## 9. CI/CD Test Gates

```yaml
ci_cd_gates:

  pre_merge (every PR):
    - semantic_registry_compliance (lint for forbidden aliases)
    - unit_tests: coverage ≥ 80% on domain logic
    - contract_tests: all MVP endpoints validate against OpenAPI
    - workflow_tests: all state machine transitions covered

  pre_deploy_staging:
    - integration_tests: sync flow + conflict resolution
    - chaos_tests: network partition + concurrent edits
    - rural_ux_smoke: automated icon/label screenshot validation
    - audit_tests: chain integrity + PII masking verification

  pre_deploy_production:
    - e2e_tests: full Minimal Farmer Crop Lifecycle flow
    - rural_ux_validation: 15+ participant test report attached
    - performance_tests: low-bandwidth sync throughput validated
    - security_pen_test: pre-launch checklist passed
    - audit_verification: all mutations have complete audit trail

  post_deploy_monitoring:
    - error_rate < 1% for first 24 hours
    - sync_success_rate > 95% for first 1000 syncs
    - zero critical (P0) rural UX issues reported
```

---

## 10. Test Data Management

```yaml
test_data_rules:

  unit_tests:
    source: synthetic canonical data
    rules: use Semantic Registry terms only, no real PII, GPS within valid India bounds

  integration_tests:
    source: anonymized production subset
    rules: PII masked, GPS rounded to district, tenant_id replaced with test tenant

  rural_ux_tests:
    source: real participant data (with explicit consent)
    rules: consent obtained, data deleted post-test unless anonymized, no cross-test reuse

  chaos_tests:
    source: synthetic stress data
    rules: 10x normal volume, simulate edge cases (duplicate mobiles, invalid polygons, stale tokens)
```

---

## 11. Go/No-Go Launch Criteria

```yaml
launch_decision:

  GREEN_LIGHT (proceed to production):
    - all testing coverage targets met
    - rural UX validation passed (≥80% task completion)
    - zero critical security or audit integrity issues
    - offline sync reliability ≥90% in low-bandwidth tests
    - pen-test passed with zero P0 vulnerabilities

  YELLOW_LIGHT (proceed with caution):
    - 1-2 moderate (P2) testing gaps with mitigation plan
    - rural UX completion 70-79% with targeted fixes planned
    - security P1 issues resolved, P2 accepted with monitoring

  RED_LIGHT (do not launch):
    - any critical (P0) testing failure unresolved
    - rural UX completion <70% or P0 usability blocker
    - security P0/P1 vulnerabilities unresolved
    - audit chain integrity or PII protection failed
    - data loss incident in chaos testing
```

---

*End of Testing Strategy & Rural UX Validation Protocol*
