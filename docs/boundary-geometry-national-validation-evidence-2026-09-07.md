# Boundary geometry national validation evidence

Status date: 2026-09-07

## Purpose

This document records the read-only national validation of the persistent
NWDP boundary GeoJSON cache. It distinguishes source-file geometry validation
from database validation metadata.

## Source

- Source cache: `data/raw/nwdp_boundary_all_state/20260824T110250Z`
- State/UT GeoJSON files: 36
- Source CRS: EPSG:7755
- Validation target CRS: EPSG:4326
- Orchestrator: `backend/scripts/run_boundary_geometry_validation_repair_all_states.py`
- Orchestrator commit: `3bd5092`
- Terminology correction commit: `b7e7a60`

## National result

| Measure | Count |
| --- | ---: |
| Selected states/UTs | 36 |
| Completed states/UTs | 36 |
| Failed states/UTs | 0 |
| Source features | 654,285 |
| Valid without repair | 654,093 |
| Confirmed invalid | 192 |
| Repairable with in-memory `make_valid()` | 192 |
| Manual-review blockers | 0 |
| Reimport or CRS-review blockers | 0 |
| Valid after in-memory transformation | 654,285 |
| Inside India bounds after transformation | 654,285 |

All 192 confirmed invalid source geometries were repairable in memory. No
repair was persisted.

## Database metadata distinction

The database contained:

- `VALIDATED`: 10 rows
- `NOT_VALIDATED`: 654,275 rows
- explicit invalid status: 0 rows

Therefore, the historical database-derived `invalid_geometry_count` of
654,275 represented rows outside the valid-status allowlist. It did not prove
that 654,275 source geometries were malformed.

The explicit fields are now:

- `not_validated_geometry_count`
- `confirmed_invalid_geometry_count`

The legacy `invalid_geometry_count` remains temporarily for response
compatibility.

## Evidence checksums

- National JSON:
  `94903964aec85f194434e693529b3565e7934d56063ae11ba6d36b664aa24551`
- State CSV:
  `44ee000b45065fd34d13a2e56c727795aff315daa71e0053fda6cf11772c53fc`

Generated evidence remains under
`data/staged/core_stack/boundary_geometry_validation_repair/20260907_national`
and is intentionally not committed.

## Guardrails

The validation performed no database writes, source-file changes, persisted
geometry repairs, validation-status changes, runtime-eligibility changes,
candidate promotion or activation, runtime-table writes, runtime lookup
enablement, LGD overwrite, or Android behavior change.

## Decision

The evidence is ready for admin national validation review. Broad geometry
repair, selected runtime promotion, runtime lookup, and Android changes remain
disabled.

The next implementation must design a guarded database validation-metadata
workflow. It must not overwrite the original source GeoJSON or canonical LGD
geography.
