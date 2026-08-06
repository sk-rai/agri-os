# Android persona lifecycle test contract

This contract prepares deterministic backend state for Android Maestro coverage of farmer profile management across independent, project-associated, field-agent, dual-capacity, and project membership transition personas.

The fixture is intentionally scoped to a dedicated Android test tenant. Do not globally flip the default tenant.

## Canonical context

Use this header for all requests:

```text
X-Tenant-ID: android-persona-lifecycle-test
```

Project:

```text
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201
```

| Persona | Mobile | User ID | Farmer ID | Parcel ID | Expected context |
| --- | --- | --- | --- | --- | --- |
| Independent farmer | `+919900001101` | `0f7e0a6b-8472-5d6d-8a14-a9d000001101` | `0f7e0a6b-8472-5d6d-8a14-a9d000001102` | `0f7e0a6b-8472-5d6d-8a14-a9d000001103` | Self-service, no project picker |
| Project-associated farmer | `+919900001201` | `0f7e0a6b-8472-5d6d-8a14-a9d000001201` | `0f7e0a6b-8472-5d6d-8a14-a9d000001202` | `0f7e0a6b-8472-5d6d-8a14-a9d000001203` | One active project enrollment |
| Farmer + field-agent dual-capacity | `+919900001301` | `0f7e0a6b-8472-5d6d-8a14-a9d000001301` | `0f7e0a6b-8472-5d6d-8a14-a9d000001302` | `0f7e0a6b-8472-5d6d-8a14-a9d000001303` | Mode chooser with farmer and agent modes |
| Field-agent assisted farmer | `+919900001401` | `0f7e0a6b-8472-5d6d-8a14-a9d000001401` | `0f7e0a6b-8472-5d6d-8a14-a9d000001402` | `0f7e0a6b-8472-5d6d-8a14-a9d000001403` | Appears in dual-agent assigned worklist |
| Transition farmer | `+919900001501` | `0f7e0a6b-8472-5d6d-8a14-a9d000001501` | `0f7e0a6b-8472-5d6d-8a14-a9d000001502` | `0f7e0a6b-8472-5d6d-8a14-a9d000001503` | Used for independent ↔ project membership transition |

## WSL prepare and verify

From WSL:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle.py --state base
```

This creates:

- 5 users;
- 5 farmer profiles;
- 5 parcels;
- 5 soil profiles;
- 3 active project enrollments in base state: associated, dual-agent farmer, assisted farmer;
- 1 active field-agent profile linked to the same user/farmer for the dual-capacity persona;
- no duplicate farmer rows per mobile;
- no orphan parcel, soil, enrollment, or agent links.

## Transition states

Independent → project-associated:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --state transition-associated --apply
../venv/bin/python scripts/verify_android_persona_lifecycle.py --state transition-associated
```

Expected transition farmer behavior:

- same `farmer_id`;
- no duplicate farmer for mobile `+919900001501`;
- `project_enrollments` contains one ACTIVE row;
- `farmer_context.mode=PROJECT`;
- `active_project_count=1`;
- bootstrap accepts `project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201`.

Project-associated → inactive/independent:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --state transition-inactive --apply
../venv/bin/python scripts/verify_android_persona_lifecycle.py --state transition-inactive
```

Expected transition farmer behavior:

- same `farmer_id`;
- no duplicate farmer for mobile `+919900001501`;
- cancelled enrollment remains auditable;
- `active_project_enrollment_count=0`;
- `farmer_context.mode=SELF_SERVICE`;
- launch-context has `active_project_count=0` and no active project candidate.

Restore base state before a full Android run:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle.py --state base --apply
../venv/bin/python scripts/verify_android_persona_lifecycle.py --state base
```

## Android endpoint checks

PowerShell/curl examples from Windows when backend is running on `localhost:8000`:

```powershell
$tenant = "android-persona-lifecycle-test"
$project = "0f7e0a6b-8472-5d6d-8a14-a9d000000201"

curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/farmers/by-mobile/+919900001101?include_form_contract=true"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/farmers/0f7e0a6b-8472-5d6d-8a14-a9d000001102/launch-context"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/auth/mode-bootstrap?user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001101"

curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/farmers/by-mobile/+919900001201?include_form_contract=true&project_id=$project"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/app-config/bootstrap?project_id=$project"

curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/auth/mode-bootstrap?user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001301&project_id=$project"
curl.exe -sS -H "X-Tenant-ID: $tenant" -H "X-Actor-ID: 0f7e0a6b-8472-5d6d-8a14-a9d000001301" "http://localhost:8000/api/v1/field-agent/worklist?project_id=$project&assigned_only=true"
```

## Expected JSON snippets

Independent farmer hydration:

```json
{
  "project_enrollments": [],
  "farmer_context": {
    "mode": "SELF_SERVICE",
    "active_project_count": 0,
    "project_selection_required": false
  },
  "summary": {
    "duplicate_farmer_count": 0
  }
}
```

Project-associated farmer hydration:

```json
{
  "farmer_context": {
    "mode": "PROJECT",
    "active_project_count": 1,
    "project_selection_required": false,
    "active_project_candidate": {
      "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000201",
      "status": "ACTIVE"
    }
  },
  "summary": {
    "active_project_enrollment_count": 1,
    "duplicate_farmer_count": 0
  }
}
```

Dual-capacity mode bootstrap:

```json
{
  "schema_version": "auth_mode_bootstrap.v1",
  "first_screen_hint": "MODE_CHOOSER",
  "modes": {
    "farmer": {
      "available": true,
      "farmer_id": "0f7e0a6b-8472-5d6d-8a14-a9d000001302"
    },
    "agent": {
      "available": true,
      "role_type": "FIELD_AGENT"
    }
  },
  "primary_project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000201"
}
```

Field-agent worklist:

```json
{
  "schema_version": "field_agent_worklist.v1",
  "mode_switch": {
    "assigned_agent_mode": true,
    "personal_farmer_mode_available": true,
    "personal_farmer_id": "0f7e0a6b-8472-5d6d-8a14-a9d000001302"
  },
  "farmers": [
    {
      "farmer": {
        "id": "0f7e0a6b-8472-5d6d-8a14-a9d000001402"
      }
    }
  ]
}
```

## Android-visible labels/copy

Backend verifier documents these stable UI expectations for Maestro selectors/copy checks:

- mode switch title: `Choose how to continue`
- farmer mode label: `My farm`
- agent mode label: `Assigned farmers`
- project picker title: `Choose project`
- independent context label: `Continue independently`

Android may own the exact visual layout, but should keep the semantics:

- show agent mode only when `modes.agent.available=true`;
- show farmer mode when `modes.farmer.available=true`;
- show project picker only when farmer launch/hydration reports `project_selection_required=true`;
- do not create a new farmer profile for an agent user when mode-bootstrap already returns a linked farmer profile.

## Backend orphan-safety verifier

The verifier checks:

- no duplicate active farmer rows for the same mobile/tenant;
- every parcel has a valid `farmer_id`;
- every parcel `project_id`, when present, points to the test project;
- every soil profile has a valid `farmer_id` and `parcel_id`, and the parcel belongs to the same farmer;
- every project enrollment has valid `farmer_id`, `project_id`, and assigned users;
- the active agent profile has a valid user, linked farmer, and project role.

Run it after each Android persona lifecycle test group:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/verify_android_persona_lifecycle.py --state base
```

Use `--state transition-associated` or `--state transition-inactive` when testing those transition-specific flows.
