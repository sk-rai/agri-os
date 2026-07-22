# Provider Worker Scheduler Runbook

This runbook describes how to operate backend-owned weather and soil enrichment provider workers before Android starts depending on automated provider refreshes.

## Scope

- Weather refresh worker: backend weather provider configs and WeatherSnapshot rows.
- Soil enrichment worker: parcel enrichment queue, job audit rows, and SoilEnrichmentSnapshot rows.
- Android must not call external weather, SoilGrids, SHC/SLUSI, or other provider APIs directly.

## Primary command

Run from the backend directory:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default --dry-run

Dry-run should always be the first production command. It returns the combined weather and soil worker plan without creating new external-provider snapshots.

## Execute mode

Only run execute mode after dry-run output is reviewed:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default

Current execution mode supports demo/stub provider behavior and records auditable worker output. Live external HTTP provider calls must remain disabled until credentials, rate-limit budgets, and operational escalation paths are configured.

## Suggested cron shape

Example dry-run cron during staging:

    */30 * * * * cd /home/lynksavvy/projects/farmint/backend && ../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default --dry-run >> /var/log/agrios-provider-workers.log 2>&1

Example execute cron after production approval:

    0 */6 * * * cd /home/lynksavvy/projects/farmint/backend && ../venv/bin/python scripts/run_due_provider_workers.py --tenant-id default >> /var/log/agrios-provider-workers.log 2>&1

Use tenant-specific scheduling once multiple production tenants are live.

## Suggested systemd timer shape

Service command:

    WorkingDirectory=/home/lynksavvy/projects/farmint/backend
    ExecStart=/home/lynksavvy/projects/farmint/venv/bin/python scripts/run_due_provider_workers.py --tenant-id default --dry-run

Timer cadence:

    OnCalendar=*:0/30

Switch from dry-run to execute only after approval.

## Operational review checklist

Before enabling execute mode:

- Confirm `DATABASE_URL` points to the intended environment.
- Run `scripts/pre_android_handoff_check.py` successfully.
- Confirm provider configs have expected runtime policy: timeout, retries, backoff, rate limits, and demo_mode/live mode.
- Confirm external provider credentials and source permissions are approved.
- Confirm recovery playbook is available: `docs/backend-recovery-playbook.md`.
- Confirm worker output is archived in logs or job history.

After each run:

- Review `weather.refreshed_count`, `weather.failed_count`, and provider row `runtime_policy`.
- Review `soil_enrichment.created_snapshot_count`, `failed_job_count`, and job row `runtime_policy`.
- For retryable provider failures, leave queue/audit state available for later retry.
- For non-retryable provider failures, review provider credentials/config/source-data assumptions before retrying.

## Failure and recovery

If worker output is unexpected:

1. Stop scheduled execution.
2. Re-run with `--dry-run` only.
3. Inspect weather operations health and soil enrichment operations health in admin web.
4. Review provider runtime policy in worker output.
5. Use `docs/backend-recovery-playbook.md` for database/app rollback guidance.

## Android handoff note

Android can consume backend snapshots/readiness once provider workers are operational, but Android should not be responsible for provider scheduling, provider credentials, rate-limit handling, or external API retries.

## Provider live execution safety policy

Live external provider execution is blocked by default. Provider config must explicitly set `live_execution_enabled=true` before live HTTP calls are allowed. Worker output exposes `live_execution.live_execution_status` so operators can distinguish demo/stub runs from approved live-provider runs.

## Provider HTTP client boundary

External provider HTTP calls must go through `app.modules.media.provider_http_client`. The boundary blocks live execution unless provider config explicitly enables it, and it is the future insertion point for timeout, retry, rate-limit, and response/error normalization. Raw HTTP calls should not be scattered across weather or soil modules.
