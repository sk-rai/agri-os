# Android broadcast terminal visibility test

Purpose: prove Android dismisses a previously visible farmer broadcast/advisory after the backend transitions the campaign to a terminal status. Android should not keep a stale broadcast card, show fatal copy, or retry the hidden campaign forever.

## Fixture

- Tenant: `android-fpo-multi-village-test`
- Project: `0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- Selected farmer: `0f7e0a6b-8472-5d6d-8a14-a9d000002106` / `+919900002106`
- Campaign: `0f7e0a6b-8472-5d6d-8a14-a9d000002980`

The fixture creates a one-farmer `PUBLISHED` broadcast with:

- `campaign.metadata.android_contract=broadcast_terminal_visibility.v1`
- `campaign.metadata.event_type=TERMINAL_VISIBILITY_ADVISORY`
- `campaign.metadata.terminal_transition_backend_owned=true`
- title `Broadcast ending soon`

## Backend commands

Prepare visible state for Android:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/prepare_android_broadcast_terminal_visibility.py --reset --apply \
  > /tmp/broadcast-terminal-visibility-prepare.raw \
  2>&1

echo "terminal_visibility_prepare_exit=$?"
tail -160 /tmp/broadcast-terminal-visibility-prepare.raw
```

While Android is open and has rendered the card, transition it from backend:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_broadcast_terminal_visibility.py --transition expire --ack-before-transition \
  > /tmp/broadcast-terminal-visibility-transition.raw \
  2>&1

echo "terminal_visibility_transition_exit=$?"
tail -180 /tmp/broadcast-terminal-visibility-transition.raw
```

Alternative terminal transition:

```bash
../venv/bin/python scripts/prepare_android_broadcast_terminal_visibility.py --transition cancel --ack-before-transition
```

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_broadcast_terminal_visibility.py --cleanup
```

## Android endpoint

```http
GET /api/v1/broadcasts/farmers/0f7e0a6b-8472-5d6d-8a14-a9d000002106/broadcasts?language_code=en&include_read=true
X-Tenant-ID: android-fpo-multi-village-test
```

## Android expected evidence

Before backend terminal transition:

```text
broadcast_terminal_visible_before=true
broadcast_terminal_contract=broadcast_terminal_visibility.v1
broadcast_terminal_event_type=TERMINAL_VISIBILITY_ADVISORY
broadcast_terminal_title=Broadcast ending soon
broadcast_terminal_initial_status=PENDING
```

After backend terminal transition and Android refresh:

```text
broadcast_terminal_visible_after_refresh=false
broadcast_terminal_feed_count_after_refresh=0
broadcast_terminal_dismissed_after_backend_transition=true
broadcast_terminal_fatal_error_visible=false
broadcast_terminal_retry_loop=false
broadcast_terminal_transition_backend_owned=true
```

If the test uses `--ack-before-transition`, also assert admin/backend evidence preserves read/ack delivery history even though farmer feed hides the campaign.

## Product note

This complements the admin/web terminal lifecycle smoke. The web smoke proved terminal campaigns remain auditable to admins; this Android smoke proves farmer UI removes terminal campaigns after refresh and does not leave stale advisory cards behind.