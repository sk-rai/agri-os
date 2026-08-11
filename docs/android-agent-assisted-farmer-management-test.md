# Android agent-assisted farmer management test contract

This contract covers the field-agent role for farmers with low literacy or no Android phone.

It extends the Android persona lifecycle fixture and verifies that an assigned field agent can review and update an assisted farmer profile and parcel, while an unassigned field agent cannot mutate the same farmer by direct ID.

## Canonical context

Header:

```text
X-Tenant-ID: android-persona-lifecycle-test
```

Project:

```text
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201
```

Actors:

- assigned primary/dual field-agent user: `0f7e0a6b-8472-5d6d-8a14-a9d000001301`
- unassigned second field-agent user: `0f7e0a6b-8472-5d6d-8a14-a9d000001701`

Assisted farmer:

- farmer: `0f7e0a6b-8472-5d6d-8a14-a9d000001402`
- parcel: `0f7e0a6b-8472-5d6d-8a14-a9d000001403`

## WSL prepare and verify

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply \
  > /tmp/persona-ext-prepare.raw

../venv/bin/python scripts/verify_android_agent_assisted_farmer_management.py \
  > /tmp/agent-assisted-management.json

python3 -m json.tool /tmp/agent-assisted-management.json | head -260
```

## Expected backend verifier readiness

```json
{
  "assigned_agent_can_review_assisted_farmer": true,
  "assigned_agent_can_update_assisted_farmer_profile": true,
  "assigned_only_worklist_excludes_independent_farmer": true,
  "unassigned_agent_hidden_from_assisted_farmer": true,
  "unassigned_agent_update_blocked": true,
  "needs_assignment_authorization_hardening": false,
  "ready_for_android_agent_assisted_maestro": true
}
```

## Android/Maestro expectations

Assigned field-agent mode should:

- show the assisted farmer in assigned farmers/worklist;
- allow opening the assisted farmer profile;
- allow updating farmer profile fields on behalf of the farmer;
- allow updating parcel/profile information on behalf of the farmer.

Unassigned field-agent mode should:

- not show the assisted farmer in assigned-only worklist;
- receive a blocked/forbidden result if attempting direct farmer or parcel update by ID.

Backend returns `403` with `FARMER_ASSIGNMENT_REQUIRED` when a known active unassigned field agent attempts the direct update.

## Reset after test

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py
```
