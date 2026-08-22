# NWDP Boundary Migration Application Checklist

Status date: 2026-08-22

This checklist must be completed before applying:

    backend/alembic/versions/054_add_nwdp_boundary_review_staging.py

## Current boundary

Migration 054 is authored and schema-guarded, but should not be applied casually.

Applying the migration creates staging tables only. It must not import rows, promote candidates, or enable runtime spatial matching.

## Pre-apply requirements

Before running Alembic upgrade locally, confirm:

- latest git branch is `main`;
- working tree has no unrelated staged changes;
- database target is local/dev, not production;
- database backup or disposable dev DB is available;
- migration 054 has been reviewed;
- schema guard is healthy;
- dry-run importer skeleton is healthy;
- candidate dry-run verifier is healthy;
- admin API contract is documented;
- admin UI spec is documented;
- no runtime promotion endpoint is implemented;
- no runtime point-in-polygon feature flag is enabled.

## Required commands before apply

Check git:

    cd ~/projects/farmint
    git status --short --branch
    git log --oneline -6

Run schema guard:

    cd ~/projects/farmint
    python3 backend/scripts/verify_nwdp_boundary_staging_schema_guard.py \
      --output /tmp/nwdp-boundary-staging-schema-guard.json

Run dry-run importer:

    cd ~/projects/farmint
    python3 backend/scripts/import_nwdp_boundary_review_staging.py \
      --input /tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv \
      --output /tmp/nwdp-boundary-guarded-importer-dry-run.json

Expected before migration apply:

- schema guard healthy: true;
- dry-run importer candidate plan healthy: true;
- staging tables available: false;
- database writes attempted: false.

## Apply command

Only after the pre-apply requirements are accepted:

    cd ~/projects/farmint/backend
    ../venv/bin/alembic upgrade 054

If the project normally uses another Python environment, use that environment instead.

## Post-apply verification

After migration apply, run:

    cd ~/projects/farmint
    python3 backend/scripts/import_nwdp_boundary_review_staging.py \
      --input /tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv \
      --output /tmp/nwdp-boundary-guarded-importer-dry-run-post-migration.json

Expected after migration apply:

- staging tables available: true;
- candidate plan healthy: true;
- database writes attempted: false;
- ready for DB write import: false;
- ready for runtime spatial matching: false.

## Forbidden after migration apply

Do not run any importer with `--apply` until the apply path is implemented, reviewed, and separately authorized.

Do not create:

- runtime boundary lookup rows;
- promoted candidate rows;
- active crosswalk mappings;
- Android-facing boundary sync payloads.

Do not alter canonical LGD tables from the NWDP importer.

## Rollback command

If rollback is needed in local/dev:

    cd ~/projects/farmint/backend
    ../venv/bin/alembic downgrade 053

Rollback drops only the NWDP boundary staging tables from migration 054.

## Go/no-go decision

Go only when:

- local/dev DB target is confirmed;
- schema guard passes;
- dry-run importer passes;
- reviewer agrees that creating empty staging tables is acceptable.

No-go if:

- target DB is uncertain;
- production credentials are in use;
- schema guard fails;
- dry-run importer has unsafe counts;
- candidate CSV is missing or has unknown buckets;
- runtime feature flags are mixed into the same change.

## Local/dev migration applied checkpoint

Status date: 2026-08-22

Local/dev command run:

    cd ~/projects/farmint/backend
    ../venv/bin/alembic upgrade 054

Observed result:

- Alembic upgraded `053 -> 054`;
- PostgreSQL transactional DDL was used;
- NWDP boundary staging tables now exist locally.

Post-migration dry-run importer result:

- target table check healthy: true;
- `geography_boundary_import_batches`: present;
- `geography_boundary_source_features`: present;
- `geography_boundary_crosswalk_candidates`: present;
- candidate plan healthy: true;
- database writes attempted by importer: false;
- ready for DB write import: false;
- ready for runtime spatial matching: false;
- rows planned inactive: 29,789;
- rows effective in runtime: 0;
- unsafe counts: none.

Current decision:

The local/dev schema is ready for guarded importer implementation. The importer apply path remains intentionally disabled.

## Local/dev inactive staging import checkpoint

Status date: 2026-08-22

After migration 054, the guarded importer inserted one inactive Karnataka NWDP boundary review batch:

- batch id: `38c31776-9683-5b36-bb79-0438864b9f3f`;
- source features: 29,789;
- crosswalk candidates: 29,789;
- active candidates: 0;
- promoted candidates: 0;
- orphan candidates: 0.

Runtime spatial matching remains disabled.
