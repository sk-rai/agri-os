# Backend Recovery Playbook

Status date: 2026-07-20

This playbook exists so backend work can continue safely. Use it before risky changes, migrations, provider-worker changes, permission hardening, or Android handoff testing.

## Recovery principle

Application code can usually be rolled back with Git. Database migrations and production data require explicit backup/restore discipline. Never rely on Git alone for database recovery.

## Current stable checkpoint

At the time this playbook was created, the stable checkpoint was:

- branch: `main`
- backend readiness: about 87%
- closeout runner: `backend/scripts/test_android_backend_closeout.py`
- Alembic head: `047`

To see the latest checkpoint:

```bash
cd ~/projects/farmint
git log --oneline -5
git status --short --branch

cd ~/projects/farmint/backend
../venv/bin/alembic current
../venv/bin/alembic heads
```

## Before risky backend work

Run:

```bash
cd ~/projects/farmint
git status --short --branch
git log --oneline -3

cd ~/projects/farmint/backend
../venv/bin/python scripts/check_alembic_revision_chain.py
../venv/bin/python scripts/test_android_backend_closeout.py
```

If either check fails, stop and fix before starting new work.

## Before any migration

Minimum preflight:

```bash
cd ~/projects/farmint/backend
../venv/bin/alembic current
../venv/bin/alembic heads
../venv/bin/python scripts/check_alembic_revision_chain.py
```

For production or shared staging, also take a database backup before `alembic upgrade`.

Example PostgreSQL backup pattern:

```bash
pg_dump "$DATABASE_URL" > backup-before-migration-$(date +%Y%m%d-%H%M%S).sql
```

If `DATABASE_URL` is not compatible with `pg_dump`, use host/user/db flags from the deployment environment.

## Roll back application code

If a pushed commit is bad but database schema does not need rollback, prefer a revert commit:

```bash
cd ~/projects/farmint
git revert <bad_commit_sha>
git push origin main
```

Avoid `git reset --hard` on shared branches unless explicitly coordinated.

## Roll back a local uncommitted patch

If the patch has not been committed:

```bash
cd ~/projects/farmint
git diff --stat
git status --short --branch
```

Then either edit the file back manually or ask Codex for a targeted reverse patch. Do not use destructive reset unless you are certain the changes are disposable.

## Roll back database migrations

Preferred order:

1. Restore from backup when data safety matters.
2. Use Alembic downgrade only if the downgrade has been reviewed and is known safe.
3. Never downgrade production blindly after data has been written to new tables/columns.

Local-only example:

```bash
cd ~/projects/farmint/backend
../venv/bin/alembic current
../venv/bin/alembic downgrade <previous_revision>
```

After rollback, run:

```bash
../venv/bin/alembic current
../venv/bin/python scripts/test_android_backend_closeout.py
```

## Provider worker recovery

Current provider workers are no-network or demo-payload capable. If a worker run creates bad snapshots or audit rows in local/staging:

- inspect tenant id and affected rows first;
- prefer tenant-scoped cleanup scripts;
- do not delete cross-tenant rows;
- keep audit rows where useful for diagnosis.

Useful dry-run command:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default --dry-run
```

## Permission hardening recovery

If an admin page starts failing after permission changes:

1. Confirm the backend endpoint now requires `Authorization: Bearer ...`.
2. Confirm admin test user/header generation in regression scripts.
3. Confirm web API client still sends the stored admin token.
4. Run the focused regression, then closeout runner.

Useful inventory:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/audit_endpoint_permission_inventory.py
```

## Android handoff recovery

Before Android integration starts, freeze a backend checkpoint commit and record:

- Git SHA;
- Alembic current revision;
- closeout runner result;
- web build result;
- sample payload bundle version.

If Android integration exposes a backend regression, first reproduce with backend scripts or curl before changing Android code.

## Known safe validation commands

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/check_alembic_revision_chain.py
../venv/bin/python scripts/test_android_backend_closeout.py
../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default --dry-run

cd ~/projects/farmint/web
npm run build
```

## What is not yet covered

- Automated production database backup orchestration.
- True clean temporary database bootstrap test.
- Deployment-level cron/scheduler rollback.
- Real external provider API rollback/rate-limit handling.

These remain backend readiness gaps before final Android handoff.

Pre-Android backend handoff check:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/pre_android_handoff_check.py
```

This read-only checker runs Git status/log, Alembic current/head, static Alembic chain validation, and the Android backend closeout runner. Web build remains a manual follow-up.

For permission hardening recovery and review context, see `docs/backend-permission-inventory-review.md`.
