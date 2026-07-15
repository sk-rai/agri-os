# Farmer project membership lifecycle

Agri-OS treats the farmer profile as a durable identity and project enrollment as a time-bound relationship.

This is important for two supported acquisition paths:

1. A farmer installs the Android app directly and starts in independent/self-service mode.
2. A company, FPO, insurer, dealer network, or input brand bulk-enrolls farmers into a project.

The same farmer can move between these states without losing their profile, parcels, soil profiles, crop cycles, or local/backend ID linkage.

## Core rule

`farmers` is the identity record. `farmer_project_enrollments` is the project membership record.

Do not create duplicate farmer rows when a known mobile/farmer later joins a project. Create or update a `farmer_project_enrollments` row instead.

Do not send a farmer back to registration merely because a company project ended. When no active project enrollment exists, Android should continue in self-service mode.

## Lifecycle states

| Situation | Enrollment state | Android context |
| --- | --- | --- |
| Direct farmer, never enrolled in a project | no project enrollment | `SELF_SERVICE` |
| Farmer has one active project | one `ACTIVE` enrollment | `PROJECT` |
| Farmer has multiple active projects | multiple `ACTIVE` enrollments | `PROJECT_PICKER` |
| Company project ended for farmer | previous enrollment `COMPLETED` and no active enrollment | `SELF_SERVICE` |
| Farmer is removed from a project | enrollment `CANCELLED` or `ARCHIVED` | `SELF_SERVICE` unless another active project exists |
| Independent farmer later joins company project | create/update enrollment to `ACTIVE` | `PROJECT` or `PROJECT_PICKER` |

## Backend contract

Profile hydration and launch context include `farmer_context`:

```json
{
  "mode": "SELF_SERVICE",
  "reason": "NO_ACTIVE_PROJECT_AFTER_COMPLETED_PROJECT",
  "can_continue_independently": true,
  "active_project_count": 0,
  "completed_project_count": 1,
  "project_selection_required": false,
  "active_project_candidate": null
}
```

Possible `mode` values:

- `SELF_SERVICE`: use generic tenant/default bootstrap; farmer can continue independently.
- `PROJECT`: one active project exists; Android may use `active_project_candidate.project_id` for project-specific bootstrap.
- `PROJECT_PICKER`: multiple active projects exist; Android should ask the user to choose the active project context.

Possible `reason` values currently emitted:

- `NO_PROJECT_ENROLLMENT`
- `ACTIVE_PROJECT_ENROLLMENT`
- `MULTIPLE_ACTIVE_PROJECTS`
- `NO_ACTIVE_PROJECT_AFTER_COMPLETED_PROJECT`

## Android guidance

After login/profile hydration:

1. If no profile exists, continue farmer enrollment.
2. If `farmer_context.mode == "PROJECT"`, use the active project candidate and fetch project-scoped bootstrap.
3. If `farmer_context.mode == "PROJECT_PICKER"`, show project picker and then fetch project-scoped bootstrap.
4. If `farmer_context.mode == "SELF_SERVICE"`, show Home using self-service/default tenant bootstrap.

Android should preserve `farmer_id`, parcel IDs, soil profile IDs, crop cycle IDs, and enrollment IDs when hydrating Room.

## Admin/product guidance

Project closure should complete/cancel project enrollments, not deactivate farmer identity.

Future admin work can add explicit bulk lifecycle actions:

- complete all active enrollments for a project
- cancel selected enrollments with reason
- reactivate/enroll an existing independent farmer into a new project
- report farmers who became self-service after project completion