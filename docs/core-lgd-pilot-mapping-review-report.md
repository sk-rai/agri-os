# CoRE/LGD Pilot Mapping Review Report

Status date: 2026-08-07

This document records the read-only pilot-state mapping review report.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/report_core_lgd_pilot_mapping_review.py

The script is read-only. It does not write database rows.

## Default pilot states

The default report covers:

| State | LGD code |
| --- | --- |
| Maharashtra | 27 |
| Karnataka | 29 |
| Punjab | 3 |

## Purpose

The report compares inactive polygon-derived `POLY_REV` candidate mappings against current active fallback district mappings.

It is intended for admin/manual review before any promotion step.

## Latest local result

Summary:

| Metric | Value |
| --- | ---: |
| Pilot-state rows | 267 |
| Rows with active fallback | 267 |
| Rows without active fallback | 0 |
| Region systems per district | 3 |
| Pilot districts represented | 89 |

By state:

| State | Rows |
| --- | ---: |
| Maharashtra | 105 |
| Karnataka | 93 |
| Punjab | 69 |

By region system:

| Region system | Rows |
| --- | ---: |
| `CORE_STACK_AGRO_CLIMATIC_ZONE` | 89 |
| `CORE_STACK_AGRO_ECOLOGICAL_ZONE` | 89 |
| `CORE_STACK_BIOGEOGRAPHIC_ZONE` | 89 |

## Relationship to promotion planner

The promotion planner classified 236 pilot rows as high-overlap promotion-review candidates.

This report includes all 267 pilot-state polygon rows, including lower-overlap rows. That makes it useful as a complete review surface, but promotion should still respect the planner's decision bucket and overlap policy.

## Important note

The active fallback mappings use starter/demo region systems such as `AGRO_CLIMATIC_ZONE_STARTER`.

The polygon candidates use CoRE systems:

- `CORE_STACK_AGRO_CLIMATIC_ZONE`
- `CORE_STACK_AGRO_ECOLOGICAL_ZONE`
- `CORE_STACK_BIOGEOGRAPHIC_ZONE`

Therefore the report compares fallback availability at district level, not exact region-system equivalence.

## Android / web impact

No Android Maestro flow is required for this report.

Android and web behavior remains unchanged because all `POLY_REV` rows are inactive.
