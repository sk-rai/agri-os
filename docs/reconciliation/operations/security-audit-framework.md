# Security & Audit Framework
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Security & Audit Framework (Pre-Launch), validated against ADR-009 (Temporal), Semantic Registry  
**Purpose:** Define authentication, authorization, PII handling, audit immutability, media access control, and pre-launch security validation requirements.

---

## 1. Authentication & Token Architecture

### JWT Token Structure

```yaml
jwt_payload:
  sub: user_id (UUID)
  tenant_id: UUID
  role: enum [FARMER, DEALER, FIELD_AGENT, AGRONOMIST, ENTERPRISE_MANAGER, ADMIN]
  territory_scope: [village_ids | block_ids | district_ids | tenant_wide]
  offline_grace_seconds: 604800  # 7 days for field agents, 259200 (3 days) for farmers
  scopes: array of canonical scope enums
  iat: issued_at (UTC)
  exp: expiry (UTC)
  jti: unique token ID (for revocation)
```

### Offline Grace Period (from ADR review Pass 1 H3)

```yaml
offline_grace:
  farmer: 3 days (259200 seconds)
  dealer: 5 days (432000 seconds)
  field_agent: 7 days (604800 seconds)
  agronomist: 7 days (604800 seconds)
  
  behavior_after_grace_expired:
    - read_only access to local data (view but not create/edit)
    - all writes queued but marked "pending_reauth"
    - on next connectivity: force re-authentication before sync
    - user sees: "🔒 Please log in again to sync your data"
  
  behavior_during_grace:
    - full offline operation (create, edit, queue for sync)
    - token validated locally (expiry check against device clock)
    - no server round-trip required
```

### Scope Enumeration (Canonical)

```yaml
canonical_scopes:
  - FARMER_READ_SELF
  - FARMER_WRITE_OWN_DATA
  - DEALER_MANAGE_ASSIGNED_FARMERS
  - DEALER_ENROLL_FARMERS
  - FIELD_AGENT_LOG_ACTIVITIES
  - FIELD_AGENT_VERIFY_STAGES
  - AGRONOMIST_ISSUE_ADVISORIES
  - AGRONOMIST_REVIEW_DISEASE
  - ENTERPRISE_VIEW_ANALYTICS
  - ENTERPRISE_MANAGE_CAMPAIGNS
  - ADMIN_MANAGE_TENANTS
  - ADMIN_MANAGE_USERS
  - SYNC_PUSH_EVENTS
  - MEDIA_UPLOAD_EVIDENCE
  - AUDIT_EXPORT_LOGS
```

---

## 2. Authorization Rules

### Scope Validation (Every Request)

```yaml
authorization_rules:

  rule_1_tenant_match:
    check: request.X-Tenant-ID == jwt.tenant_id
    failure: 403 TENANT_MISMATCH
    note: prevents cross-tenant data access

  rule_2_token_expiry:
    check: jwt.exp >= current_utc_time OR (offline_mode AND within_grace_period)
    failure: 401 TOKEN_EXPIRED or OFFLINE_GRACE_EXPIRED
    
  rule_3_scope_check:
    check: required_scope_for_endpoint IN jwt.scopes
    failure: 403 SCOPE_DENIED
    policy: default_deny (no scope = no access)

  rule_4_territory_bound:
    check: requested_entity.village_id IN jwt.territory_scope
    failure: 403 TERRITORY_BOUND
    exception: FARMER role always scoped to own data only (not territory)

  rule_5_entity_ownership:
    check: if role == FARMER then entity.farmer_id == jwt.sub
    failure: 403 NOT_OWNER
    note: farmers can only access their own records
```

### Role-Based Access Summary

| Endpoint | FARMER | DEALER | FIELD_AGENT | AGRONOMIST | ENTERPRISE |
|----------|--------|--------|-------------|------------|-----------|
| POST /farmers | ❌ | ✅ (assigned territory) | ✅ (assigned territory) | ❌ | ❌ |
| GET /farmers/{id} | ✅ (own only) | ✅ (assigned) | ✅ (territory) | ✅ (territory) | ✅ (aggregated) |
| POST /parcels | ✅ (own) | ✅ (assigned farmers) | ✅ (territory) | ❌ | ❌ |
| PATCH /stages/{id} | ✅ (own) | ✅ (assigned) | ✅ (territory) | ✅ (territory) | ❌ |
| POST /disease-reports | ✅ (own) | ✅ (assigned) | ✅ (territory) | ❌ | ❌ |
| GET /dashboards | ❌ | ❌ | ❌ | ❌ | ✅ |
| POST /sync/events | ✅ | ✅ | ✅ | ✅ | ❌ |
| GET /audit | ❌ | ✅ (own actions) | ✅ (own actions) | ❌ | ✅ (all tenant) |

---

## 3. PII Classification & Handling

### PII Levels

| Level | Fields | Storage Rule | Logging Rule | Analytics Rule |
|-------|--------|-------------|-------------|----------------|
| **DIRECT PII** | mobile_number, government_id, bank_account | Encrypt at rest, hash for indexing | Mask in all logs (show last 4 digits only) | Never in analytics — aggregate only |
| **SENSITIVE** | gps_coordinates, device_id, ip_address, soil_health_data | Restrict cross-tenant, purpose-limited retention | Round GPS to 2 decimals in logs | Aggregate to block/district level |
| **INDIRECT** | village_name, crop_type, irrigation_type | Standard tenant isolation | Log freely | Available for analytics |

### PII Processing Rules

```yaml
pii_rules:

  masking_in_logs:
    mobile_number: "XXXXXXX1234" (last 4 visible)
    government_id: never stored plaintext — use salted hash or encrypted vault
    gps_in_logs: round to 2 decimal places (≈1km precision)

  consent_withdrawal:
    direct_pii: schedule erasure within 30 days (DPDPA requirement)
    sensitive_pii: anonymize or aggregate
    indirect_pii: retain if de-identified (for benchmarking)
    audit_trail: PRESERVED even after PII erasure (legal requirement)
    note: audit entries reference entity_id but PII fields are nullified

  assisted_digital_separation:
    rule: "Actor PII and Subject PII must NEVER merge into single identity"
    actor_fields: dealer_id, agent_id, device_id, actor_gps
    subject_fields: farmer_id, farmer_mobile, farmer_village
    storage: separate columns, never concatenated
```

---

## 4. Audit Log Architecture

### Canonical Audit Entry Schema

```yaml
audit_entry:
  audit_id: UUID (globally unique)
  tenant_id: UUID
  actor_id: UUID
  actor_role: ENUM (from Semantic Registry)
  action_type: ENUM [CREATE, UPDATE, DELETE, SYNC, CONFLICT_RESOLVE, LOGIN, LOGOUT, EXPORT, ESCALATE]
  entity_type: canonical entity name (from Semantic Registry)
  entity_id: UUID
  before_state_hash: SHA-256 of entity state before mutation (null for CREATE)
  after_state_hash: SHA-256 of entity state after mutation
  timestamp_utc: ISO 8601
  valid_at: ISO 8601 (from ADR-009 temporal model)
  gps_coordinates: {lat, lng, accuracy} or null
  device_id: string
  sync_mode: ENUM [ONLINE, OFFLINE_QUEUED, PARTIAL_SYNC]
  correlation_id: UUID (links related audit entries across a workflow)
  ip_address: string or null (server-side only)
  chain_hash: SHA-256(previous_chain_hash + current_entry_hash)
```

### Immutability Rules

```yaml
audit_immutability:

  allowed_operations:
    - INSERT (append only)
  
  forbidden_operations:
    - UPDATE (never modify existing entries)
    - DELETE (never remove entries)
    - TRUNCATE (never clear audit tables)
  
  exception:
    - archival to cold storage after retention period (move, not delete)
    - PII nullification on consent withdrawal (nullify fields, preserve structure)

  tamper_detection:
    mechanism: hash chaining (each entry includes hash of previous entry)
    validation: periodic integrity check (daily batch job)
    alert: if chain_hash mismatch detected → AUDIT_TAMPER_ALERT → lock for forensic review
    
  storage_isolation:
    audit_db: separate schema or read replica (never in transactional query path)
    operational_db: never queries audit tables during normal operations
    analytics_db: consumes only de-identified audit aggregates
```

### Audit Retention Policy

```yaml
audit_retention:
  default: 5 years (configurable per tenant)
  insurance_critical: 7 years (regulatory)
  financial_data: 7 years (tax compliance)
  
  archival:
    hot: 90 days (fast query)
    warm: 90 days → 2 years (indexed but slower)
    cold: 2 years → retention_limit (compressed archive)
```

---

## 5. Media Access Control

### Access Validation Rules

```yaml
media_access_rules:

  farmer_access:
    rule: can only access media they uploaded OR media linked to their entities
    check: media.owner_id == request.user_id OR media.entity.farmer_id == request.user_id

  dealer_access:
    rule: can access media for assigned farmers only
    check: media.farmer_id IN dealer.assigned_farmer_ids

  field_agent_access:
    rule: can access media within territory
    check: media.parcel.village_id IN agent.territory_village_ids

  agronomist_access:
    rule: can access disease report media within territory
    check: media.entity_type == DISEASE_REPORT AND media.parcel.village_id IN agronomist.territory

  enterprise_access:
    rule: can access aggregated media analytics (counts, not individual images)
    check: role == ENTERPRISE_MANAGER AND tenant_id matches
    exception: specific media review workflows (insurance claim investigation)
```

### Signed URL Generation

```yaml
signed_url_policy:
  ttl: 10 minutes (configurable, max 60 minutes)
  scope: GetObject only (no write via signed URL)
  path: /{tenant_id}/{entity_type}/{entity_id}/{media_id}.{ext}
  audit: every URL generation logged (media_id, requester, timestamp, expiry)
  
  offline_caching:
    allowed: thumbnails only (320×240, low-res)
    forbidden: original resolution cached on device
    re_auth: required on reconnect to refresh signed URLs
```

---

## 6. Device Security

```yaml
device_security:

  device_binding:
    rule: JWT includes device_id claim
    behavior: if device_id changes mid-session → force re-authentication
    stolen_device: admin can revoke all tokens for a device_id

  remote_wipe:
    capability: admin can trigger "clear local data" command
    delivery: on next sync attempt, server returns WIPE_REQUIRED response
    behavior: app clears local DB, forces fresh login
    audit: wipe command logged with admin actor_id

  rooted_device_detection:
    mvp: not enforced (future enhancement)
    future: warn user, restrict sensitive operations on rooted devices
```

---

## 7. Pre-Launch Security Validation Checklist

### Authentication & Token Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| JWT forgery (modified tenant_id) | Tamper payload, submit | 403 TENANT_MISMATCH |
| JWT expiry bypass (extended exp) | Modify exp claim | Server clock validation rejects |
| Missing scopes | Remove scope from token | 403 SCOPE_DENIED (default deny) |
| Offline grace abuse | Expired token + offline mode after grace | 401 OFFLINE_GRACE_EXPIRED |
| Device binding bypass | Change device_id after login | Session binding check fails |

### Tenant & Territory Isolation Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Cross-tenant data access | Inject tenant_id=A for tenant_B data | 403, zero data returned |
| Territory bypass | Query farmers without territory filter | Territory clause enforced at DB level |
| Farmer accessing other farmer | Farmer A requests farmer B's data | 403 NOT_OWNER |

### Sync & Offline Attack Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| GPS spoofing | Inject coordinates >100m from actual | Warning flag in audit, not silent accept |
| Replay attack | Re-submit same sync event_id with different payload | Idempotency check rejects (409) |
| Sync queue poisoning | Inject malformed payload into local DB | Server schema validation rejects cleanly |
| Bulk fabrication | Submit 1000 records in 1 minute from single device | Anomaly detection flags (Rule-033) |

### Media & PII Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Unsigned media access | Direct S3 path without signature | 403 Forbidden |
| EXIF metadata leak | Download original image | No camera serial/model in response |
| PII in logs | Trigger audit log query | No plaintext mobile/GPS/government_id |
| Consent withdrawal | Call PII erasure | Data anonymized, audit trail preserved |

### Audit Integrity Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Audit chain break | Manually delete audit row | Hash validation failure triggers alert |
| Audit modification | Attempt UPDATE on audit table | DB permission denies operation |
| Audit reconstruction | Query full entity history | Complete lineage with all actors/timestamps |

---

## 8. Security Invariants (CI/CD Enforceable)

```yaml
security_invariants:
  - tenant_isolation_enforced_at_db_and_api_level
  - jwt_scopes_explicit_no_wildcards_no_default_allow
  - pii_never_logged_in_plaintext
  - audit_log_append_only_with_hash_chaining
  - media_access_via_tenant_scoped_signed_urls_only
  - offline_mode_restricted_to_grace_period
  - assisted_digital_pii_actor_subject_separated
  - sync_events_include_correlation_id_and_device_id
  - all_mutations_include_audit_entry
  - pen_test_must_pass_before_production_promotion
  - consent_withdrawal_completes_within_30_days
  - no_direct_db_access_bypassing_authorization_layer
```

---

*End of Security & Audit Framework*
