# ADR-008: Analytics Freshness and Confidence Model

**Status:** DECIDED  
**Date:** May 21, 2026  
**Resolves:** Pass 1 C3; Pass 3 H5 (analytics consistency under eventual consistency)

---

## Context

The platform guarantees only eventual consistency, but enterprise dashboards need trustworthy analytics. Late-arriving sync data can invalidate previously calculated KPIs.

## Decision

### Every KPI Carries a Confidence Score

All analytics outputs include:

```yaml
kpi_output:
  value: 2450  # kg/hectare
  unit: kg_per_hectare
  confidence_score: 0.73  # 0.0 to 1.0
  data_completeness: 0.68  # percentage of expected data received
  freshness: 2_hours_ago  # last recalculation time
  pending_syncs: 12  # known devices with pending data for this scope
  staleness_flag: false  # true if new data arrived since last calculation
```

### Confidence Calculation

```yaml
confidence_model:
  data_completeness_weight: 0.40
  sync_freshness_weight: 0.30
  workflow_completion_weight: 0.30

  data_completeness:
    formula: received_records / expected_records_for_scope
    expected_records: based on enrolled farmers × active crop cycles

  sync_freshness:
    formula: 1.0 - (hours_since_oldest_pending_sync / max_acceptable_delay)
    max_acceptable_delay: 72_hours

  workflow_completion:
    formula: completed_stages / expected_stages_for_scope
```

### Dashboard Display Rules

| Confidence Score | Display Behavior |
|-----------------|-----------------|
| ≥ 0.90 | Show normally (green indicator) |
| 0.70 – 0.89 | Show with "partial data" warning (yellow indicator) |
| 0.50 – 0.69 | Show with "low confidence" warning (orange indicator) |
| < 0.50 | Hide from default view, available in "raw data" mode only |

### Recalculation Triggers

```yaml
recalculation_triggers:
  - sync_batch_completed (any device syncs data for this scope)
  - conflict_resolved (resolution may change underlying data)
  - manual_trigger (admin requests recalculation)
  - scheduled (daily batch for all KPIs)
  - staleness_threshold_exceeded (>24 hours since last calc + new data exists)
```

### Analytics Processing Modes

| Mode | Latency | Use Case | Trigger |
|------|---------|----------|---------|
| Real-time | <5 seconds | Active user counts, sync status | Event-driven |
| Near-real-time | <5 minutes | Stage distribution, disease counts | Buffered events |
| Batch | <24 hours | Profitability, yield, benchmarking | Scheduled + sync triggers |

---

## Consequences

- Enterprise users always know how trustworthy a metric is
- Late-arriving data triggers automatic recalculation
- Dashboards never show stale data without indication
- Regions with poor connectivity show lower confidence (honest, not hidden)
- Batch analytics run after sync storms complete (not during)

---

*End of ADR-008*
