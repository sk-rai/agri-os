# Deployment & Infrastructure Governance
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 Deployment & Infrastructure Runbook  
**Depends on:** ADR-001 (Modular Monolith), Security & Audit Framework  
**Purpose:** Define environment topology, promotion rules, backup/DR, monitoring thresholds, and operational governance.

---

## 1. Deployment Principles

```yaml
deployment_principles:
  - modular_monolith_for_MVP (single deployable, per ADR-001)
  - tenant_isolation_at_all_layers (DB, storage, cache)
  - offline_first_infrastructure (async queues, eventual consistency tolerance)
  - audit_all_deployment_changes (actor, timestamp, change description, rollback plan)
  - rural_connectivity_aware_monitoring (don't alert on expected offline patterns)
```

---

## 2. Environment Topology

| Environment | Purpose | Data | Access | Deploy Trigger |
|-------------|---------|------|--------|----------------|
| **Development** | Feature dev + unit testing | Synthetic only | Engineering team | Auto on merge to develop |
| **Staging** | Integration + rural UX + pen-test | Anonymized production subset | Engineering + QA + rural testers | Auto on tag v*.*.*-staging |
| **Production** | Live farmer operations | Real data (PII encrypted) | Role-based RBAC + audit | MANUAL approval required |

### Promotion Gates

```yaml
promotion_rules:

  dev_to_staging:
    automated_if:
      - all CI stages pass
      - semantic registry validation passes
      - no CRITICAL security vulnerabilities
    
  staging_to_production:
    requires:
      - staging stable for 24 hours
      - error_rate < 1% in staging
      - sync_success_rate > 95% in staging
      - rural_ux_completion_rate >= 80%
      - pen_test_critical_issues = 0
      - rollback_plan_documented_and_tested
    manual_approval_chain:
      1: engineering_lead (technical readiness)
      2: product_lead (rural UX validation)
      3: security_lead (pen-test clearance)
      4: ops_lead (rollback plan tested)
```

---

## 3. Container Architecture (MVP)

```yaml
mvp_containers:

  primary_app:
    purpose: API server + workflow engine + rules engine
    resources: 512Mi-1Gi RAM, 250m-1000m CPU
    health_check: /health (30s interval, 10s timeout)
    readiness: /health/ready (10s interval)
    security: nonroot user, read-only filesystem where possible

  background_worker:
    purpose: async tasks, sync queue processing, notification dispatch
    resources: 256Mi-512Mi RAM, 100m-500m CPU
    concurrency: 4 workers (tune based on load)
    graceful_shutdown: 30s (finish current task then exit)
    dependencies: primary_app ready + redis + postgres

  redis:
    purpose: async queue, cache, sync coordination
    resources: 512MB maxmemory, AOF persistence enabled
    security: requirepass, protected_mode, internal network only

  postgres_postgis:
    purpose: transactional DB + geospatial
    resources: 1Gi-4Gi RAM, 500m-2000m CPU, 50-200Gi SSD storage
    extensions: postgis, pg_stat_statements, pgcrypto
    config: max_connections=100, shared_buffers=256MB
```

---

## 4. Tenant Isolation at Infrastructure Level

```yaml
tenant_isolation:
  database: row_level_security (tenant_id on every table, enforced at query layer)
  object_storage: path prefix s3://bucket/{tenant_id}/{entity_type}/{media_id}
  cache: tenant_id prefix in all Redis keys
  events: tenant_id in every event envelope (per Event Bus Contract)
  
  forbidden:
    - cross_tenant_query_without_explicit_permission
    - shared_cache_keys_across_tenants
    - tenant_A_accessing_tenant_B_storage_path
```

---

## 5. Backup & Disaster Recovery

### Database Backup

```yaml
postgres_backup:
  full_backup: daily at 02:00 UTC, pg_dump with compression
  incremental: hourly via WAL archiving
  point_in_time_recovery: supported via WAL replay
  retention: 30 days hot, 1 year cold archive
  encryption: AES-256 with managed keys
  verification: weekly restore test to isolated environment
  tenant_isolation: backup metadata includes tenant scope
  access_control: ops team only, restore requires dual approval
```

### Object Storage Backup

```yaml
object_storage_backup:
  replication: cross-region for production
  integrity: checksum validation on upload + periodic scan
  lifecycle: hot (90d) → cold (2y) → archive (5y) → delete (unless insurer-critical)
  corruption_handling: automated quarantine of corrupt objects
```

### Disaster Recovery Scenarios

| Scenario | Detection | Response | RTO Target |
|----------|-----------|----------|------------|
| **Database corruption** | Health check fails, query errors | Promote read replica OR restore from backup + WAL | 1 hour |
| **Complete server failure** | Availability alert | Provision new instance from latest backup | 2 hours |
| **Object storage corruption** | Checksum mismatch | Restore from cross-region replica | 4 hours |
| **Device data loss** (phone stolen/broken) | User reports | Re-sync from server on new device (all data server-side after sync) | Immediate (next login) |
| **Sync queue poisoning** | Schema validation failures spike | Isolate poison events in DLQ, process valid events normally | 30 minutes |

### Recovery Validation

```yaml
dr_validation:
  frequency: quarterly
  procedure:
    1: restore database from backup to isolated environment
    2: apply WAL archives to point-in-time
    3: run data integrity checks (FK, geospatial index, audit chain hash)
    4: run synthetic transactions (enrollment, parcel, crop cycle)
    5: document results and remediate gaps
```

---

## 6. Monitoring & Alerting

### Application Health Metrics

| Metric | Threshold | Alert If |
|--------|-----------|----------|
| Uptime | ≥ 99.5% monthly | < 99.0% for 5 minutes |
| P95 latency | < 2000ms | > 5000ms for 10 minutes |
| Error rate (5xx) | < 1.0% | > 5.0% for 5 minutes |
| Sync success rate | ≥ 95% | < 90% for 15 minutes |
| Offline queue depth | < 1000 per device | > 5000 for any device (sync stall) |

### Rural Connectivity-Aware Alerting

```yaml
rural_alerting_rules:
  
  do_not_alert:
    - device offline < 4 hours (expected rural operation)
    - sync retry count < 3 (normal backoff behavior)
    - single device sync failure (individual connectivity issue)
  
  alert_medium:
    - device offline > 4 hours WITH pending critical sync items
    - message: "Device {id} offline >4h with {count} critical items"
  
  alert_high:
    - sync failure rate for geography > 20% for 1 hour (regional issue)
    - SMS delivery failure > 10% for 30 minutes (provider issue)
    - message: "Regional sync degradation in {district}: {rate}%"
  
  alert_critical:
    - production unavailable
    - data corruption detected (audit chain break)
    - PII exposure confirmed
    - response: page on-call immediately
```

### Business Metric Monitoring

| Metric | Threshold | Alert If |
|--------|-----------|----------|
| Daily active farmers | Baseline per program | Drops >30% week-over-week |
| Crop stage update rate | ≥70% of active cycles updated weekly | <50% (adoption/usability issue) |
| Advisory acknowledgment | ≥60% acknowledged | <40% (irrelevant/mistimed content) |
| Dealer update frequency | ≥1 update per assisted farmer per week | >20 farmers with zero updates in 2 weeks |
| Incomplete workflows | <15% of cycles missing critical stages | >30% (form complexity/training gap) |

---

## 7. Alert Escalation Matrix

| Priority | Conditions | Notification | Resolution SLA |
|----------|-----------|--------------|----------------|
| **P0 Critical** | Production down, data corruption, security breach, PII exposure | Page on-call + security team + enterprise client comms within 15 min | 1 hour |
| **P1 High** | Sync rate <90% for 30min, notification failure >10%, rural UX critical issue | Slack engineering channel + email product lead | 4 hours |
| **P2 Medium** | Latency >2x baseline for 1h, dealer metrics declining, config issue | Slack team channel + ticket created | 24 hours |
| **P3 Low** | Non-critical feature flag issue, minor UI inconsistency, docs update | Weekly digest + backlog item | Next sprint |

---

## 8. Feature Flag Governance

```yaml
feature_flags:
  scoping:
    - tenant_scoped (enable for tenant_X only)
    - geography_scoped (enable for district_Y only)
    - percentage_rollout (enable for 10% of users)
    - role_scoped (enable for DEALER role only)
  
  rollback: instant disable without redeploy
  audit: flag change logged with actor_id + timestamp + reason
  cleanup: flags older than 90 days without activity → review for removal
```

---

## 9. Production Change Management

```yaml
change_management:

  configuration_changes:
    approval: product_lead + engineering_lead
    window: 02:00-06:00 local time (low farmer activity)
    strategy: feature flag → 10% canary → monitor 30 min → full rollout
    rollback: instant flag disable if error_rate > 0.5%

  code_deployments:
    versioning: semantic (major.minor.patch)
    changelog: required, includes farmer impact assessment
    prerequisite: successful staging validation
    strategy: canary 10% → monitor 15 min → full rollout
    rollback: maintain 1 previous version, auto-rollback if metrics degrade

  emergency_changes:
    bypass: normal approval bypassed for P0 incidents
    requirement: post-incident review within 24 hours
    documentation: justification + lessons learned
```

---

## 10. Canary Deployment Strategy

```yaml
canary_deployment:
  initial_rollout: 10% of production nodes
  monitoring_period: 15 minutes
  
  success_criteria:
    - error_rate < 0.5%
    - latency_p95 < 2x baseline
    - sync_queue_depth stable (not growing)
  
  on_success: rollout to 100%
  on_failure: auto-rollback to previous version + alert engineering
  
  post_deployment:
    - synthetic transaction monitoring (enrollment, parcel, sync)
    - real user monitoring alerts enabled
    - audit log verification (deployment event logged)
```

---

## 11. Pre-Launch Infrastructure Checklist

```yaml
infrastructure_go_no_go:

  must_pass:
    - staging stable for 72 hours
    - production infrastructure provisioned and tested
    - backup restore procedure validated with drill
    - monitoring alerts tested end-to-end
    - rollback procedure tested and documented
    - security pen-test critical issues = 0
    - rural UX validation completion ≥ 80%
    - offline sync reliability ≥ 95% in staging
    - semantic registry enforced in CI
    - audit logging verified for all critical mutations

  must_document:
    - incident response runbook
    - disaster recovery procedure
    - enterprise client communication template
    - on-call rotation schedule
    - escalation contact list
```

---

## 12. Post-Launch Operational Cadence

```yaml
operational_cadence:

  weekly:
    - analyze error logs for recurring patterns
    - review rural UX feedback for usability gaps
    - assess sync failure root causes
    - update monitoring thresholds based on real data

  monthly:
    - evaluate deployment success rate
    - assess incident response effectiveness
    - review security audit findings
    - plan infrastructure improvements

  quarterly:
    - evaluate monolith vs microservice extraction need (per ADR-001 triggers)
    - assess scaling patterns and bottlenecks
    - review cost optimization opportunities
    - plan next phase intelligence layers (NDVI/AI)
    - DR drill (restore from backup, validate integrity)
```

---

*End of Deployment & Infrastructure Governance*
