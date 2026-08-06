# Android persona lifecycle extension tests

This contract extends `docs/android-persona-lifecycle-test.md` with three adjacent Android/backend flows:

1. project picker for a farmer with multiple active project memberships;
2. field-agent reassignment lifecycle;
3. duplicate farmer profile detection and cleanup.

Use the same dedicated tenant as the persona lifecycle base contract.

## Canonical context

Header:

```text
X-Tenant-ID: android-persona-lifecycle-test
```

Projects:

```text
project_1=0f7e0a6b-8472-5d6d-8a14-a9d000000201
project_2=0f7e0a6b-8472-5d6d-8a14-a9d000000202
```

## WSL prepare/reset

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py
```

The extension prepare script also prepares the base persona lifecycle tenant in `base` state.

## Flow A: project picker / multiple active memberships

Fixture:

```text
mobile=+919900001601
user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001601
farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001602
parcel_id=0f7e0a6b-8472-5d6d-8a14-a9d000001603
```

Expected hydration:

```json
{
  "summary": {
    "active_project_enrollment_count": 2,
    "duplicate_farmer_count": 0
  },
  "farmer_context": {
    "mode": "PROJECT_PICKER",
    "active_project_count": 2,
    "project_selection_required": true,
    "active_project_candidate": null
  }
}
```

Expected launch context:

```json
{
  "recommended_navigation": "SHOW_PROJECT_PICKER",
  "active_project_count": 2,
  "active_project_candidate": null,
  "project_selection_required": true,
  "endpoints": {
    "bootstrap": "/api/v1/app-config/bootstrap"
  }
}
```

Android rule:

- show project picker;
- do not silently choose a default project;
- after the user selects a project, call bootstrap with that selected `project_id`.

Curl checks:

```powershell
$tenant = "android-persona-lifecycle-test"
$project1 = "0f7e0a6b-8472-5d6d-8a14-a9d000000201"
$project2 = "0f7e0a6b-8472-5d6d-8a14-a9d000000202"

curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/farmers/by-mobile/+919900001601?include_form_contract=true"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/farmers/0f7e0a6b-8472-5d6d-8a14-a9d000001602/launch-context"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/app-config/bootstrap?project_id=$project1"
curl.exe -sS -H "X-Tenant-ID: $tenant" "http://localhost:8000/api/v1/app-config/bootstrap?project_id=$project2"
```

## Flow B: agent reassignment lifecycle

Fixture:

```text
assisted_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001402
primary_agent_user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001301
second_agent_user_id=0f7e0a6b-8472-5d6d-8a14-a9d000001701
project_id=0f7e0a6b-8472-5d6d-8a14-a9d000000201
```

Initial expected state:

- assisted farmer appears in primary agent assigned worklist;
- assisted farmer does not appear in second agent assigned worklist;
- `farmer_project_enrollments.assigned_user_ids` contains only the primary agent user ID for this assisted farmer/project.

Backend reassignment endpoint:

```http
POST /api/v1/farmers/{assisted_farmer_id}/project-agent-assignment
```

Unassign primary:

```json
{
  "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000201",
  "agent_user_id": "0f7e0a6b-8472-5d6d-8a14-a9d000001301",
  "action": "UNASSIGN",
  "reason": "Android reassignment test unassign primary"
}
```

Assign second:

```json
{
  "project_id": "0f7e0a6b-8472-5d6d-8a14-a9d000000201",
  "agent_user_id": "0f7e0a6b-8472-5d6d-8a14-a9d000001701",
  "action": "ASSIGN",
  "reason": "Android reassignment test assign second"
}
```

Expected after reassignment:

- primary assigned-only worklist no longer includes the assisted farmer;
- second agent assigned-only worklist includes the assisted farmer;
- farmer/project enrollment remains ACTIVE;
- parcel/soil links remain valid;
- reassignment metadata records assignment events;
- no orphan farmer, parcel, soil profile, enrollment, or agent profile rows.

WSL verification with mutation:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --perform-reassignment
```

Reset to initial state after this flow:

```bash
../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
```

## Flow C: duplicate farmer profile detection and cleanup

Fixture:

```text
mobile=+919900001801
primary_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001802
duplicate_farmer_id=0f7e0a6b-8472-5d6d-8a14-a9d000001805
```

The primary profile is the richer profile and has parcel/soil context. The duplicate is intentionally empty.

Expected hydration before cleanup:

```json
{
  "farmer": {
    "id": "0f7e0a6b-8472-5d6d-8a14-a9d000001802"
  },
  "summary": {
    "duplicate_farmer_count": 1
  },
  "duplicates": [
    {
      "id": "0f7e0a6b-8472-5d6d-8a14-a9d000001805",
      "parcel_count": 0,
      "crop_cycle_count": 0
    }
  ]
}
```

Duplicate listing endpoint:

```http
GET /api/v1/farmers/duplicates?mobile_number=+919900001801
```

Expected:

```json
{
  "schema_version": "farmer_duplicates.v1",
  "group_count": 1,
  "groups": [
    {
      "recommended_primary_farmer_id": "0f7e0a6b-8472-5d6d-8a14-a9d000001802",
      "duplicate_count": 1
    }
  ]
}
```

Cleanup endpoint:

```http
POST /api/v1/farmers/{primary_farmer_id}/duplicates/archive
```

Payload:

```json
{
  "duplicate_farmer_ids": [
    "0f7e0a6b-8472-5d6d-8a14-a9d000001805"
  ],
  "reason": "Android duplicate cleanup test"
}
```

Expected after cleanup:

- duplicate farmer status becomes `ARCHIVED`;
- hydration still returns the same primary farmer;
- `duplicate_farmer_count=0`;
- primary farmer parcel/soil/project context is preserved;
- no orphan rows.

WSL verification with archive:

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py --archive-duplicate
```

Reset to pre-cleanup duplicate state after this flow:

```bash
../venv/bin/python scripts/prepare_android_persona_lifecycle_extensions.py --reset --apply
../venv/bin/python scripts/verify_android_persona_lifecycle_extensions.py
```

## Android-visible labels / copy

Suggested stable copy for Maestro/UI checks:

- project picker title: `Choose project`
- agent reassignment empty state: `No assigned farmers`
- duplicate cleanup action: `Use existing profile`

Android should not show raw backend IDs to farmers, but Maestro can use the deterministic IDs above for network assertions/log correlation.

## Backend verifier guarantees

`backend/scripts/verify_android_persona_lifecycle_extensions.py` checks:

- project picker has exactly two active enrollments;
- launch context returns `SHOW_PROJECT_PICKER`;
- unscoped launch context does not select a default project;
- selected `project_id` drives app bootstrap;
- reassignment moves assisted farmer from primary to second agent worklist when mutation mode is enabled;
- duplicate hydration selects richer primary farmer;
- duplicate archive removes the empty duplicate from active hydration;
- no orphan parcel, soil profile, project enrollment, or agent profile links.
