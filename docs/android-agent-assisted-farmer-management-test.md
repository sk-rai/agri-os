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

Additional assigned farmer for multi-worklist coverage:

- mobile: `+919900001901`
- farmer: `0f7e0a6b-8472-5d6d-8a14-a9d000001902`
- parcel: `0f7e0a6b-8472-5d6d-8a14-a9d000001903`

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
  "assigned_agent_can_review_multiple_assigned_farmers": true,
  "multi_assigned_farmer_visible": true,
  "assigned_only_worklist_excludes_independent_farmer": true,
  "unassigned_agent_hidden_from_assisted_farmer": true,
  "unassigned_agent_update_blocked": true,
  "needs_assignment_authorization_hardening": false,
  "ready_for_android_agent_assisted_maestro": true
}
```

## Android/Maestro expectations

Assigned field-agent mode should:

- show at least two assigned farmers in assigned farmers/worklist;
- show the deterministic assisted farmer and additional multi-assigned farmer;
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

## Android evidence

- Backend commit `a03913f` enforced assigned-agent farmer/parcel PATCH authorization.
- Android follow-up verified assigned agent farmer PATCH `200`, assigned agent parcel PATCH `200`, unassigned farmer probe `403`, unassigned parcel probe `403`, primary agent worklist includes assisted farmer, and second agent worklist is empty.
- This fixture now also covers `>1` assigned farmers for the primary/dual agent worklist. Android should avoid silently selecting the first farmer; it should show a selectable/searchable assigned-farmer list when more than one row is returned.

## Android Flow 38 smoke evidence

Android Flow 38 passed against backend commit `5e0e93c test: cover multi-assigned agent worklist`.

Maestro flow: `maestro/38-agent-assisted-farmer-management.yaml`

Evidence summary:

- assigned dual agent `+919900001301` received `MODE_CHOOSER`;
- `My farm` and `Assigned farmers` modes were visible;
- assigned-agent worklist returned `agent_worklist_farmers=2`;
- assisted farmer visible;
- independent farmer absent from assigned worklist;
- assigned farmer PATCH returned `200`;
- assigned parcel PATCH returned `200`;
- unassigned active agent `+919900001701` had assigned worklist count `0`;
- unassigned direct farmer PATCH returned `403` with `FARMER_ASSIGNMENT_REQUIRED`;
- unassigned direct parcel PATCH returned `403` with `FARMER_ASSIGNMENT_REQUIRED`;
- Android showed clean authorization copy: `You are not assigned to manage this farmer.`;
- stale-context, workflow-invalid, and manual-review conflict copy were absent.

Backend verifier: `backend/scripts/verify_android_agent_assisted_farmer_management.py`

Verifier confirmed:

- primary agent `assigned_farmer_count=2`;
- assigned farmer IDs:
  - `0f7e0a6b-8472-5d6d-8a14-a9d000001402`
  - `0f7e0a6b-8472-5d6d-8a14-a9d000001902`
- `multi_assigned_farmer_visible=true`;
- second agent worklist empty;
- assigned PATCHes returned `200`;
- unassigned PATCHes returned `403 FARMER_ASSIGNMENT_REQUIRED`.

Caveat:

- Current Android debug output asserts `agent_worklist_farmers=2`; backend verifier asserts the exact `multi_assigned_farmer_visible=true` field. A future Android smoke hardening can emit/assert the exact second farmer ID if needed.
