# Android Field Event Advisory Loop Smoke

This smoke covers the backend-owned loop from a field-event photo report to a targeted advisory broadcast:

1. create an FPO maize field event with uploaded pest photo media;
2. move the field event through review to `ADVISORY_SENT`;
3. publish an advisory broadcast that reuses the same media asset;
4. generate deliveries only for active Maize farmers;
5. verify Android-visible farmer feeds include the advisory for the targeted farmer and exclude a Rice farmer.

## Backend prepare / verifier

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --reset --apply \
  > /tmp/field-event-advisory-loop-verify.raw \
  2>&1

echo "field_event_advisory_loop_verify_exit=$?"
tail -220 /tmp/field-event-advisory-loop-verify.raw
```

Expected backend readiness:

- `ready_for_android_field_event_advisory_loop_maestro=true`
- `ready_for_field_event_advisory_loop_web_smoke=true`
- field event status is `ADVISORY_SENT`
- advisory broadcast delivery count is `2`
- advisory media asset ID matches the original field-event media asset ID
- included Maize farmer sees the advisory
- excluded Rice farmer does not see the advisory

## Web smoke

Start backend and frontend first. Then:

```bash
cd ~/projects/farmint

if [ ! -f /tmp/web-smoke-env.sh ]; then
  cd ~/projects/farmint/backend
  ../venv/bin/python scripts/create_web_ui_smoke_session.py \
    --tenant-id android-fpo-multi-village-test \
    --user-id 0f7e0a6b-8472-5d6d-8a14-a9d000002099 \
    --role ENTERPRISE_ADMIN \
    --format exports \
    > /tmp/web-smoke-env.sh
  cd ~/projects/farmint
fi

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/field_event_advisory_loop_smoke.mjs \
  > /tmp/field-event-advisory-loop-web-smoke.json \
  2>&1

cat /tmp/field-event-advisory-loop-web-smoke.json
```

Expected web evidence:

- `field_event_advisory_field_event_visible=true`
- `field_event_advisory_status=ADVISORY_SENT`
- `field_event_advisory_source_media_asset_reused=true`
- `field_event_advisory_broadcast_visible=true`
- `field_event_advisory_delivery_count=2`
- `field_event_advisory_included_farmer_visible=true`
- `field_event_advisory_excluded_farmer_visible=false`
- `field_event_advisory_android_contract=field_event_advisory_loop.v1`

## Cleanup

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_field_event_advisory_loop.py --cleanup
```

## Android handoff evidence

Android should verify:

- `field_event_advisory_contract=field_event_advisory_loop.v1`
- `field_event_advisory_event_type=FIELD_EVENT_ADVISORY_CREATED`
- `field_event_advisory_source_event_id=0f7e0a6b-8472-5d6d-8a14-a9d000002994`
- `field_event_advisory_campaign_id=0f7e0a6b-8472-5d6d-8a14-a9d000002996`
- `field_event_advisory_media_asset_reused=true`
- `field_event_advisory_media_type=PHOTO`
- `field_event_advisory_attachment_purpose=ADVISORY_ATTACHMENT`
- `field_event_advisory_included_farmer_visible=true`
- `field_event_advisory_excluded_farmer_visible=false`
- Android does not construct media URLs locally.
