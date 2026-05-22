# ADR-004: Geography Hierarchy — Include Block/Taluka Level

**Status:** DECIDED  
**Date:** May 21, 2026

---

## Context

The Data Dictionary includes `block` between district and village. No other document references it. Indian administrative geography uses block/taluka as a real administrative level.

## Decision

**Include block/taluka in the canonical geography hierarchy.**

```yaml
canonical_geography_hierarchy:
  country:
    contains: state
  state:
    contains: district
  district:
    contains: block
  block:
    aliases: [taluka, tehsil, mandal]
    contains: village
  village:
    contains: [farmers, parcels]
```

## Rationale

- Indian government schemes operate at block level
- Agricultural extension services are organized by block
- Weather data is often available at block granularity
- Territory assignment for field agents typically uses block boundaries
- Insurance claim processing references block-level administration

## Consequences

- Entity Relationship Tree: add `block` entity between district and village
- Master Ontology: update geography hierarchy
- Module Dependency Graph: geography_master_module includes block_hierarchy
- Analytics: block becomes a valid aggregation level
- KPI Registry: geographic_aggregation includes block
- Notification targeting: block-level targeting supported

---

*End of ADR-004*
