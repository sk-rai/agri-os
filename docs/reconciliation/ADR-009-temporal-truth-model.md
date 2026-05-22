# ADR-009: Temporal & Observational Truth Model

**Status:** DECIDED  
**Date:** May 21, 2026  
**Source:** AI-1 correlation analysis — identified as critical gap  
**Purpose:** Define how the system handles time, observation validity, and retroactive corrections.

---

## Context

The platform operates in an environment where:
- Farmers apply fertilizer on Day 1 (valid_time)
- They record it on their phone on Day 1 at 9am (observation_time)
- The phone syncs on Day 3 (transaction_time)
- Analytics process it on Day 4 (processing_time)

Without tracking all four timestamps, audit reconstruction and analytics correctness are impossible.

## Decision

### All Entities Must Track Four Time Dimensions

```yaml
required_timestamps:

  valid_time:
    field_name: valid_at
    description: "When the fact was true in the real world"
    example: "Farmer applied fertilizer on 2026-05-15"
    source: user_input (date picker in form)
    nullable: false for activities, true for system-generated records

  observation_time:
    field_name: observed_at
    description: "When the data was captured on device"
    example: "Phone recorded at 2026-05-15 09:00 local"
    source: device_clock at time of form submission
    nullable: false

  transaction_time:
    field_name: created_at / updated_at
    description: "When the fact was recorded in the server database"
    example: "Sync completed on 2026-05-17 14:30 UTC"
    source: server_clock at time of database write
    nullable: false

  processing_time:
    field_name: processed_at
    description: "When analytics/aggregation last processed this record"
    example: "KPI calculated on 2026-05-18 02:00 UTC"
    source: analytics_pipeline timestamp
    nullable: true (only for analytics-processed entities)
```

### Schema Impact

Every mutable entity table adds:

```sql
valid_at          TIMESTAMP NOT NULL,  -- when fact was true
observed_at       TIMESTAMP NOT NULL,  -- when captured on device
created_at        TIMESTAMP NOT NULL DEFAULT NOW(),  -- server write time
updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),  -- last server update
```

### Supersession Rules

Corrections never overwrite. They create new versions:

```yaml
supersession:
  rule: "No silent overwrites. All corrections create superseding records."
  
  mechanism:
    - original record preserved with is_superseded: true
    - new record created with supersedes_id: original_id
    - compensating event published: entity_corrected.v1
    - audit trail links both versions

  who_can_supersede:
    - same actor (self-correction within 24 hours)
    - higher-authority actor (agronomist corrects farmer entry)
    - system (automated correction from conflict resolution)

  analytics_impact:
    - superseded records excluded from current calculations
    - superseded records available for historical reconstruction
    - recalculation triggered when supersession occurs
```

### Observation Trust Scoring

```yaml
trust_scoring:

  factors:
    gps_accuracy:
      weight: 0.25
      scoring: "1.0 if <5m, 0.8 if <15m, 0.5 if <50m, 0.2 if >50m"
    
    timestamp_consistency:
      weight: 0.20
      scoring: "1.0 if valid_time == observed_at (same day), 0.5 if within 3 days, 0.2 if >7 days gap"
    
    actor_role:
      weight: 0.25
      scoring: "agronomist=1.0, field_agent=0.9, dealer=0.7, farmer=0.6"
    
    device_trust:
      weight: 0.15
      scoring: "known_device=1.0, new_device=0.7, suspicious_device=0.3"
    
    corroboration:
      weight: 0.15
      scoring: "corroborated_by_other_actor=1.0, single_source=0.5"

  thresholds:
    auto_accept: score >= 0.80
    flag_for_review: 0.50 <= score < 0.80
    require_verification: score < 0.50

  entity_specific_overrides:
    parcel_geometry: gps_accuracy_weight = 0.40 (higher importance)
    disease_report: corroboration_weight = 0.30 (outbreak detection)
    financial_data: timestamp_consistency_weight = 0.30 (fraud detection)
```

## Consequences

- All entities carry temporal context enabling audit reconstruction
- Corrections are traceable (never destructive)
- Trust scoring enables automated conflict resolution for low-risk entities
- Analytics can distinguish "high-confidence" from "low-confidence" data
- Insurance/legal queries can reconstruct "what was known at time T"

## Implementation Note

For MVP, implement:
- All four timestamps on all entities ✅
- Basic supersession (corrections create new versions) ✅
- Trust scoring as metadata (calculated but not yet used for auto-resolution) ✅

Defer to post-MVP:
- Automated trust-based conflict resolution
- Full audit reconstruction API endpoint
- Temporal queries ("show me the state as of date X")

---

*End of ADR-009*
