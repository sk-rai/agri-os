# Backend recovery disposable verification — 2026-11-15

## Scope

This note records the operator-observed disposable PostgreSQL verification for
the backend recovery branch ending at `e5fc37d`. It is a sanitized summary, not
a retained raw command transcript. The final source review accepted the source
changes and treated the execution results below as operator-reported evidence.

No production service or database was used. `PRODUCTION_RECOVERY_LIVE_NOT_APPROVED`
remained closed.

## Isolation

- Template database: `agrios_activity_test_template`
- Disposable database prefix: `agrios_activity_loss_`
- Development database preserved: `agrios_dev`
- Preflight found no existing database with the disposable prefix.
- One randomly named disposable clone was created for the run.
- Repository seeders populated only the disposable clone with the synthetic
  reference, crop lifecycle, workflow, and Android test context required by the
  focused regressions.
- Cleanup removed the exact clone created by the run.
- Post-cleanup checks found the template and `agrios_dev` present and no
  remaining database with the disposable prefix.

Database URLs, credentials, tokens, fixture payloads, and raw exception bodies
are intentionally excluded.

## Observed results

| Check | Observed result |
| --- | --- |
| Clean downgrade `070 -> 069` | PASS |
| Upgrade `069 -> 070` | PASS |
| Second clean downgrade `070 -> 069` | PASS |
| Restore upgrade `069 -> 070` | PASS |
| Downgrade with a synthetic orphan | Rejected as expected |
| Revision and orphan after rejected downgrade | Revision remained `070`; orphan remained present |
| Post-orphan-cleanup downgrade `070 -> 069` | PASS |
| Final upgrade `069 -> 070` | PASS |
| Parcel existing-parent dependency regression | PASS |
| Project-enrollment derived parcel regression | PASS |
| Android crop-cycle/activity identity regression | 92 PASS; 0 failures |
| Concurrent same-ID activity reuse | PASS |
| Unrelated integrity-error classification | PASS |
| Disposable clone cleanup | PASS |

The concurrent activity case observed two successful responses retaining one
client activity ID, one stored activity row, exactly one response reporting a
published event, and no change to cycle economics for the zero-cost test input.
The request-level barrier does not prove that both requests reached the insert
before either transaction committed. Nonzero-cost concurrent duplicate charging
remains outside this run's evidence scope.

The integrity-error checks used synthetic PostgreSQL diagnostics to confirm that
only SQLSTATE `23505` with constraint `crop_activities_pkey` is classified for
activity identity recovery. Other unique and foreign-key classifications were
not accepted by the classifier.

## Static verification

Before commit and push:

- The two changed Python files parsed successfully with Python's AST parser.
- `git diff --check` passed.
- The staged patch contained only:
  - `backend/app/modules/workflow/api.py`
  - `backend/scripts/test_android_crop_cycle_activity_logging_flow.py`
- Commit `e5fc37d` was pushed to
  `codex/backend-reviewed-recovery-20261114`.

The final independent source review found no new source blocker in `e5fc37d`.
It did not rerun database tests or migrations and found no retained raw run log;
therefore the database results in this note remain operator-reported.

## Boundaries

This evidence does not establish production deployment behavior, live HTTP
routing, authentication middleware behavior, historical database compatibility,
or production data safety. It does not authorize merge, deployment, migration,
Android execution, production recovery, or live synchronization. Merge and all
later actions require their own approvals.
