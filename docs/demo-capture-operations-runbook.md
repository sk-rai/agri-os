# AgriFabric demo capture operations runbook

Status date: 2026-08-17

This runbook turns `docs/demo-capture-checklist.md` into executable capture preparation steps. It focuses on local deterministic demo capture, not production deployment.

Use this when recording short videos for the landing page, product walkthroughs, investor conversations, or internal demos.

## Ground rules

- Use local/demo fixtures only.
- Do not show private production data.
- Do not claim live weather/soil provider execution, verified product labels, operational risk scoring, or NDVI analysis.
- Restore or clean up stateful fixtures after each capture when the fixture doc provides a cleanup/restore command.
- Prefer clean short clips over long end-to-end recordings.
- Record Android and web separately when possible, then stitch in editing. Mixed videos can be sequence cuts or split-screen edits.

## Terminal layout

Recommended local terminal layout:

1. Backend server terminal.
2. Frontend server terminal.
3. Fixture/smoke command terminal.
4. Android/Maestro/recording terminal.

## Start backend

Terminal 1:

```bash
cd ~/projects/farmint/backend

../venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

Health check from another terminal:

```bash
curl -sS http://localhost:8000/health
```

Expected:

```json
{"status":"ok","version":"0.1.0","service":"Agri-OS"}
```

## Start frontend

Terminal 2:

```bash
cd ~/projects/farmint/web

NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
npm run dev -- --hostname 0.0.0.0 --port 3000
```

If the installed Next.js version rejects `--hostname`, use:

```bash
cd ~/projects/farmint/web

NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
npm run dev -- --port 3000
```

Frontend URL:

```text
http://localhost:3000
```

## Create web smoke/admin session

Use this for web/admin capture or Playwright smoke setup.

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/create_web_ui_smoke_session.py \
  --tenant-id android-fpo-multi-village-test \
  --user-id 0f7e0a6b-8472-5d6d-8a14-a9d000002099 \
  --role ENTERPRISE_ADMIN \
  --format exports \
  > /tmp/web-smoke-env.sh

cat /tmp/web-smoke-env.sh
```

Load it before web smoke commands:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a
```

## Capture order

Recommended production order:

1. FPO/project operations.
2. Broadcast/advisory lifecycle.
3. Offline sync resilience.
4. Field event to advisory loop.
5. Farmer onboarding and crop activity ledger.
6. Localization and land intelligence.
7. Geography/DigiPin.
8. Relationship graph and field-agent performance concept.
9. Insurance/subsidy integrity concept.

This order gives the landing page strong commercial clips first, then technical depth, then roadmap/storytelling clips.

## Video 1: Farmer onboarding

Mode: Android-only.

Recommended fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --reset --apply \
  > /tmp/demo-persona-lifecycle-prepare.json \
  2>&1

tail -160 /tmp/demo-persona-lifecycle-prepare.json
```

Optional verifier:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/verify_android_persona_lifecycle.py --state base \
  > /tmp/demo-persona-lifecycle-verify.raw \
  2>&1

echo "persona_verify_exit=$?"
tail -160 /tmp/demo-persona-lifecycle-verify.raw
```

Capture focus:

- Android mode/profile context.
- Backend-driven registration/profile form.
- PIN/village and parcel/location fields.
- Readiness or DigiPin/GPS result if available in the selected flow.

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_persona_lifecycle.py --reset --apply
```

## Video 2: FPO/project operations

Mode: mixed, web-first then Android.

Fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/verify_android_fpo_multi_village_workflow.py \
  > /tmp/demo-fpo-multi-village-verify.raw \
  2>&1

echo "fpo_verify_exit=$?"
tail -180 /tmp/demo-fpo-multi-village-verify.raw
```

Web smoke proof/capture:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/fpo_project_enrollment_search_smoke.mjs \
  > /tmp/demo-fpo-project-enrollment-search-web-smoke.json \
  2>&1

cat /tmp/demo-fpo-project-enrollment-search-web-smoke.json
```

Capture focus:

- `/project-enrollments` FPO project list/search.
- Village/crop/mobile search.
- Farmer drill-down.
- `/project-trace/{project_id}` summary.
- Android selected farmer project hydration/crop cycle if available.

Cleanup:

Usually no cleanup required if this is the reusable FPO baseline. Re-run `prepare_android_fpo_multi_village_workflow.py --reset --apply` before next FPO capture.

## Video 3: Crop activity ledger

Mode: Android-only, optional web/admin trace outro.

Fixture options:

Use the crop-cycle fixture for clean crop-cycle creation/activity capture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/seed_android_crop_cycle_test_fixture.py --reset --apply \
  > /tmp/demo-crop-cycle-fixture.json \
  2>&1

tail -160 /tmp/demo-crop-cycle-fixture.json
```

Or use the FPO baseline if the video should show a project-associated farmer:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
```

Capture focus:

- Android crop cycle.
- Stage timeline.
- Activity logging.
- Cost/summary card.
- Optional admin/project trace outro.

Cleanup:

Re-run the chosen fixture reset before another take.

## Video 4: Offline sync resilience

Mode: Android-only public demo; optional technical overlay.

Recommended simple fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_cold_start_activity_persistence.py --apply \
  > /tmp/demo-offline-sync-prepare.json \
  2>&1

tail -180 /tmp/demo-offline-sync-prepare.json
```

Optional conflict fixture variants:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_version_mismatch_conflict.py --reset --apply \
  > /tmp/demo-version-mismatch-prepare.json \
  2>&1

../venv/bin/python scripts/prepare_android_workflow_invalid_conflict.py --reset --apply \
  > /tmp/demo-workflow-invalid-prepare.json \
  2>&1
```

Capture focus:

- pending/offline row;
- app restart/reconnect;
- sync success;
- conflict card if using conflict variant;
- no duplicate / accepted work continues overlay.

Post-capture verifier:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/verify_android_cold_start_activity_persistence.py \
  > /tmp/demo-offline-sync-verify.raw \
  2>&1

echo "offline_sync_verify_exit=$?"
tail -180 /tmp/demo-offline-sync-verify.raw
```

Cleanup:

Most sync fixtures are deterministic and reset at prepare time. Re-run prepare before each capture take.

## Video 5: Broadcast/advisory lifecycle

Mode: mixed, web-first then Android then web.

Fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-prepare-for-broadcast.json \
  2>&1

../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --reset --apply \
  > /tmp/demo-closure-notice-prepare.json \
  2>&1

tail -160 /tmp/demo-closure-notice-prepare.json
```

Create read/ack state for admin analytics:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/verify_android_broadcast_read_ack_lifecycle.py \
  > /tmp/demo-broadcast-read-ack-verify.raw \
  2>&1

echo "broadcast_read_ack_verify_exit=$?"
tail -160 /tmp/demo-broadcast-read-ack-verify.raw
```

Web smoke proof/capture:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/broadcast_admin_delivery_analytics_smoke.mjs \
  > /tmp/demo-broadcast-admin-delivery-analytics.json \
  2>&1

cat /tmp/demo-broadcast-admin-delivery-analytics.json
```

Capture focus:

- web Broadcasts page;
- campaign detail;
- delivery lifecycle counts;
- Android farmer advisory card;
- read/ack;
- web audit history.

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_fpo_project_closure_migration_notice.py --restore
```

## Video 6: Field event to targeted advisory

Mode: mixed, Android-first then web/admin then Android.

Fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/demo-fpo-prepare-for-field-event.json \
  2>&1

../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --reset --apply \
  > /tmp/demo-field-event-advisory-loop.raw \
  2>&1

echo "field_event_advisory_loop_exit=$?"
tail -220 /tmp/demo-field-event-advisory-loop.raw
```

Web smoke proof/capture:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/field_event_advisory_loop_smoke.mjs \
  > /tmp/demo-field-event-advisory-loop-web.json \
  2>&1

cat /tmp/demo-field-event-advisory-loop-web.json
```

Capture focus:

- Android or narrated field-event/photo capture;
- web Field Events detail;
- web Broadcast detail;
- source media reused;
- Android Maize farmer receives advisory;
- Rice farmer excluded if useful.

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --cleanup
```

## Video 7: Localization and land intelligence

Mode: mixed.

Localization fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_localization_override_delivery.py --reset --apply \
  > /tmp/demo-localization-override-prepare.raw \
  2>&1

echo "localization_override_prepare_exit=$?"
tail -180 /tmp/demo-localization-override-prepare.raw
```

Land intelligence fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --reset --apply \
  > /tmp/demo-land-intelligence-override-prepare.raw \
  2>&1

echo "land_intelligence_override_prepare_exit=$?"
tail -180 /tmp/demo-land-intelligence-override-prepare.raw
```

Optional web captures:

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/localization_admin_smoke.mjs \
  > /tmp/demo-localization-admin-web.json \
  2>&1

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/land_intelligence_summary_admin_smoke.mjs \
  > /tmp/demo-land-intelligence-admin-web.json \
  2>&1
```

Capture focus:

- web admin override/configuration;
- Android label or fallback rendering;
- Android land-intelligence card;
- informational-only/do-not-block messaging.

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_localization_override_delivery.py --cleanup
../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --cleanup
```

## Video 8: Geography, DigiPin, and plot resolution

Mode: Android-only plus concept overlay.

Fixture:

Use the same persona/FPO/crop-cycle fixture that produces clear parcel/location screens.

Suggested baseline:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply
```

Optional checks:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/test_digipin_utility.py
../venv/bin/python scripts/test_digipin_farmer_parcel_fields.py
../venv/bin/python scripts/test_sync_digipin_materialization.py
```

Capture focus:

- Android PIN/village field;
- GPS/parcel capture;
- backend-returned DigiPin;
- concept overlay explaining LGD/PIN/GPS/DigiPin/land intelligence layers.

Cleanup:

None beyond fixture reset.

## Video 9: Relationship graph and field-agent performance

Mode: concept/narrated visual with web/admin snippets.

Useful implemented snippets:

- field-agent worklist;
- project enrollment search;
- agent assignment/reassignment;
- advisory analytics;
- field-event/media evidence.

Fixture:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply \
  > /tmp/demo-persona-extensions-prepare.json \
  2>&1

../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --perform-reassignment \
  > /tmp/demo-persona-extensions-verify.raw \
  2>&1

tail -180 /tmp/demo-persona-extensions-verify.raw
```

Capture focus:

- show graph visual;
- show assignment/worklist evidence;
- show FPO/project search evidence;
- show advisory analytics evidence;
- mark scorecards/performance dashboard as roadmap.

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
```

## Video 10: Insurance and subsidy integrity roadmap

Mode: concept/narrated visual with implemented evidence snippets.

Useful snippets:

- farmer/project identity;
- parcel/GPS/DigiPin;
- crop-cycle/activity trail;
- field-event/media;
- advisory read/ack audit;
- sync audit/conflict history;
- relationship graph diagram.

No special fixture required if using already captured snippets from Videos 1-9.

Capture focus:

- evidence bundle concept;
- future risk flags;
- human review boundary;
- NDVI/time-series marked future.

Avoid:

- operational fraud detection claims;
- automated claim denial/approval claims.

## Post-capture checklist

For each video:

- confirm title and filename;
- confirm implemented/roadmap badge is correct;
- confirm no private data is visible;
- confirm no raw logs unless technical variant;
- confirm claim boundaries are respected;
- export short clip and thumbnail;
- record which fixture state was used;
- run cleanup/restore if fixture is stateful.

## Commit guidance

Generated video files should not be committed unless a media-assets policy is created. Keep recordings outside git or in an explicitly approved artifact storage location.

Screenshots under `web/smoke/screenshots/` are generated smoke artifacts and should remain untracked unless intentionally curated.

