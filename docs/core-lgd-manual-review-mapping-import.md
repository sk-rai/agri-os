# CoRE/LGD Manual Review Mapping Import

Status date: 2026-08-07

This document records the guarded import of polygon-derived CoRE/LGD district mapping candidates.

## Source plan

The importer reads:

    data/staged/core_stack/manual_review_import_plan/core_lgd_manual_review_import_plan.csv

That plan contains:

- 2,355 total district/region candidate rows;
- 2,298 eligible `WOULD_WRITE` rows;
- 57 excluded rows because of source-version/LGD/state-code issues.

## Import command

Dry run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/import_core_lgd_manual_review_mappings.py

Apply:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/import_core_lgd_manual_review_mappings.py --apply

The importer is idempotent. Re-running after import reports existing rows instead of creating duplicates.

## Imported row policy

Imported rows use:

| Field | Value |
| --- | --- |
| `confidence` | `POLY_REV` |
| `metadata.confidence_label` | `POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW` |
| `review_status` | `MANUAL_REVIEW` |
| `is_active` | `false` |
| `version` | `clri_v1` |
| `metadata.importer_label` | `core_lgd_manual_review_import.v1` |

Important: imported rows are inactive. They do not affect land-intelligence behavior.

## Latest local import result

Latest successful import:

- inserted polygon-derived candidate rows: 2,298;
- distinct districts covered: 766;
- distinct CoRE region rows referenced: 45;
- active imported polygon rows: 0;
- duplicate candidate keys: 0;
- missing region references: 0.

Existing active fallback rows remained unchanged:

| Confidence | Active count |
| --- | ---: |
| `LOCAL_DEMO_DISTRICT_FALLBACK` | 186 |
| `LOCAL_DEMO_SEED` | 5 |

## Verification

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/verify_core_lgd_manual_review_mappings.py

Expected readiness:

- `poly_rev_count_matches=true`;
- `all_poly_rev_inactive=true`;
- `all_poly_rev_manual_review=true`;
- `no_duplicate_poly_rev_keys=true`;
- `no_missing_region_refs=true`;
- `fallbacks_remain_active=true`;
- `safe_for_land_intelligence_behavior=true`.

## Android / web impact

No Android Maestro flow is required for this import.

The imported rows are inactive/manual-review only, so Android and web land-intelligence behavior remains unchanged.

Testing is needed only after a future promotion step makes selected polygon-derived mappings active/effective.
