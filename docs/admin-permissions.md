# Admin permissions and UI guard map

This document summarizes the current Agri-OS admin permission model used by the FastAPI backend and the Next.js admin UI.

Backend authorization remains the source of truth. UI guards are convenience and safety affordances only: they hide or disable actions for read-only users, but every mutation endpoint must still enforce permissions server-side.

## Permission primitives

Defined in `backend/app/core/admin_auth.py`:

| Permission | Meaning |
| --- | --- |
| `VIEW` | Can open admin/reporting screens and inspect data. |
| `EDIT` | Can mutate master/configuration data such as input catalog, workflow drafts, product catalog, and conflict resolution. |
| `PUBLISH` | Can publish reviewed workflow/input changes to runtime-facing catalogs. |
| `PROJECT_EDIT` | Can mutate project-scoped configuration such as workflow enablements, overrides, product approvals, and project input assignments. |
| `MANAGE_USERS` | Can provision tenant admins, project access, and tenant-level admin records. |

## Role to permission map

| Role | Permissions |
| --- | --- |
| `ENTERPRISE_ADMIN` | `VIEW`, `EDIT`, `PUBLISH`, `PROJECT_EDIT`, `MANAGE_USERS` |
| `MANAGER` | `VIEW`, `EDIT`, `PUBLISH`, `PROJECT_EDIT` |
| `AGRONOMIST` | `VIEW`, `EDIT`, `PROJECT_EDIT` |
| `ADMIN_EDITOR` | `VIEW`, `EDIT` |
| `ADMIN_PUBLISHER` | `VIEW`, `EDIT`, `PUBLISH` |
| `ADMIN_VIEWER` | `VIEW` |
| `VIEWER` | `VIEW` |

Project-scoped backend dependencies may evaluate the user's project role rather than only the tenant role, except `ENTERPRISE_ADMIN`, which bypasses project membership checks.

## Admin identity endpoint

The admin UI should use:

```http
GET /api/v1/admin/me
```

It returns the authenticated admin identity, tenant role permissions, and project access rows with project role permissions. The UI helper is:

```ts
import { useAdminProfile, hasAdminPermission, adminRoleLabel } from "@/lib/admin-permissions";
```

## Screen guard map

| Admin screen | View behavior | Mutation permission(s) |
| --- | --- | --- |
| `/users` | Requires admin profile. Non-`MANAGE_USERS` users see no-access/read-only messaging. | `MANAGE_USERS` for invite, tenant role change, revoke, project access assignment/revoke. |
| `/tenants` | Tenant list visible. | `MANAGE_USERS` for tenant creation. |
| `/projects` | Project list and compliance links visible. | `EDIT` or `PROJECT_EDIT` for project creation. |
| `/workflows` | Workflow list, version history, legacy pin report, and audit visible. | `EDIT` for restore-as-draft and legacy pin backfill. |
| `/workflows/preview/[versionId]` | Workflow preview, validation reports, publish impact, audit, and usage visibility remain available. | `EDIT` for draft clone/stage/recommendation edits; `PUBLISH` for publish; `PROJECT_EDIT` for project overrides. |
| `/project-workflows` | Project workflow assignment list/audit visible. | `PROJECT_EDIT` plus safe-edit lifecycle open state for enable/disable/metadata changes. |
| `/inputs` | Input catalog, usage references, CSV template/export, and audit visible. | `EDIT` for create/update/archive/restore/submit/reject/CSV apply; `PUBLISH` for publish. |
| `/products` | Product/manufacturer/rule browsing visible. | `EDIT` for manufacturer/product/rule edits; `PROJECT_EDIT` for project product approvals. |
| `/crop-climate-suitability` | Climate regions, rules, and tenant/project overrides visible. | `PUBLISH` for suitability overrides; a supplied project must belong to the authenticated tenant. |
| `/project-inputs` | Project input assignment list/stats/audit visible. | `PROJECT_EDIT` for enable/disable/reorder/metadata changes. |
| `/conflicts` | Conflict list/detail visible. | `EDIT` for accepting client/server conflict resolution. |
| Trace/report screens | Reporting and export actions remain visible. | No mutation guard currently needed unless future write actions are added. |

## Viewer/read-only expectation

For roles with only `VIEW`:

- Browse and inspect data.
- Use filters, search, refresh, and export/report actions.
- Open trace/detail/preview screens.
- See clear read-only banners where a screen contains mutation controls.
- Mutation buttons should be hidden or disabled with a helpful tooltip/message.

## Implementation notes

- Add new admin pages to this document when they introduce mutation controls.
- Prefer loading permissions via `useAdminProfile()` once per page/component instead of direct `authApi.me()` calls.
- Do not rely on UI guards for security. Backend endpoints must continue to use `require_admin_permission(...)`.
- When project lifecycle locks apply, UI must combine permission checks with lifecycle checks; having permission does not override safe-edit lifecycle rules.

## Regression checks

Run the lightweight backend permission suite after changing admin roles, permission dependencies, or guarded UI/API contracts:

```bash
cd backend
../venv/bin/python scripts/run_admin_permission_regressions.py
```

The suite currently covers:

- `/api/v1/admin/me` profile permission mapping.
- Tenant user invitation, role changes, project access, audit, and revocation.
- JWT-backed admin role and project-scope enforcement across representative protected endpoints.

## Finance report configuration

`POST /api/v1/crop-cycles/finance/report-config/validate` requires `EDIT`.
It performs validation without persistence but remains an administrative
configuration operation.

`POST /api/v1/crop-cycles/finance/report-config/publish` requires `PUBLISH`.
Publishing and archival attribution use the verified administrator, and any
optional project scope must belong to the authenticated tenant and be active.

## Broadcast administration

Broadcast draft creation, content editing, and audience-rule editing require
`EDIT`. Campaign publication, delivery generation, delivery retry, expiry, and
cancellation require `PUBLISH`.

All administrative broadcast attribution uses the verified principal.
Caller-supplied creator, approver, or lifecycle actor identifiers do not
control persisted campaign or audit identity.

## Product catalog administration

Product CSV application and manufacturer, product, and package maintenance
require `EDIT`. Project product approval requires `PROJECT_EDIT` plus active
membership in the addressed project, except for the tenant enterprise
administrator.

All product-catalog mutation scope and audit attribution derive from the
verified administrator principal. Tenant and actor headers remain compatibility
assertions and cannot select another audit tenant or actor.

## Weather administration

Weather provider configuration, manual refresh recording, adapter execution,
due-provider execution, manual snapshot creation, and refresh-worker execution
require `EDIT`.

Each route derives tenant and actor from the verified administrator. Provider
and snapshot metadata record the verified administrative actor and operation;
caller-supplied metadata cannot override those attribution fields.

## Identity administration

Agent-profile creation and updates, project-access assignment, and project-access revocation require the `MANAGE_USERS` permission.

These mutations derive tenant and actor identity from the verified administrator principal. `X-Tenant-ID` remains a consistency check and must not grant cross-tenant authority. Project-access changes require both the target user and project to belong to the verified tenant.

Each successful mutation writes an immutable tenant user access audit event using the verified administrator as `actor_id`.

## Runtime app configuration

Runtime tenant and project app-configuration mutations require verified
administrative identity.

- `PATCH /api/v1/tenants/{tenant_id}/app-config` requires `MANAGE_USERS` and
  remains restricted to `ENTERPRISE_ADMIN`. The path tenant must equal the
  tenant carried by the verified bearer identity.
- `PATCH /api/v1/projects/{project_id}/app-config` requires `PROJECT_EDIT`
  through project-scoped authorization. The selected project must belong to
  the verified administrator's tenant.
- `X-Tenant-ID` and `X-Actor-ID` are consistency assertions only. They do not
  establish mutation authority.
- Successful mutations preserve immutable before/after state, the applied
  patch, patched sections, reason, verified tenant, and verified administrator.

## Company-discovery CSV administration

Company-discovery CSV processing is an authenticated administrative workflow.

- `POST /api/v1/company-discovery-candidates/csv/validate` requires `EDIT`.
- `POST /api/v1/company-discovery-candidates/csv/import` requires `EDIT`.
- Both operations derive tenant and actor from the verified bearer identity.
- `X-Tenant-ID` and `X-Actor-ID` are consistency assertions only and cannot
  establish mutation authority.
- Validation reports the verified administrator through `validated_by`.
- Successful imports record verified actor provenance on each candidate and
  write an immutable `IMPORT_COMPANY_DISCOVERY_CSV` batch audit event.

## Project geography import preview

`POST /api/v1/projects/{project_id}/geography-scope/import-preview` requires
`PROJECT_EDIT` through project-scoped authorization.

The project is selected within the verified administrator's tenant. The
response reports the verified tenant and administrator through `tenant_id` and
`previewed_by`. Identity headers are consistency assertions only.

The endpoint remains read-only: it validates, normalizes, and resolves village
LGD codes but does not update project scope, configuration, candidate state,
runtime eligibility, or audit tables.

## Workflow project overrides

Creating and archiving project workflow overrides requires a verified
administrator with `PROJECT_EDIT` permission and project-scoped authorization.
The mutation derives tenant and actor identity from the authenticated principal;
`X-Tenant-ID` and `X-Actor-ID` are consistency checks rather than sources of
authority.

Override creation is restricted to published workflow templates owned by the
verified tenant or the shared `default` catalog. Archival tenant-bounds the
project, override, and workflow template before retaining the override as an
inactive record. Both operations write immutable workflow audit events with the
verified administrator, project, template version, reason, and before/after
state.

## Geography review administration

Shared national geography review queues are platform-level resources rather
than tenant-owned business data. Mutations for NWDP boundary candidates, NWDP
demographic profiles, CoRE/LGD mapping candidates, and two-session village
resolution evidence therefore require a verified administrator whose tenant is
the `default` platform tenant. Ordinary tenant administrators are rejected even
when their role includes `EDIT` or `PUBLISH`.

Reviewer identity is derived from the authenticated principal and persisted in
review metadata, reviewer columns, or immutable review events. Identity headers
are consistency checks and are not sources of mutation authority.

The disabled NWDP project-matching apply contract is different: it is
project-scoped, requires `PROJECT_EDIT`, derives tenant and actor from the
verified principal, and tenant-bounds the project lookup. It remains write-free
and returns `501`; no matching, promotion, runtime lookup, or Android behavior is
enabled.

## Soil enrichment operations

The following operational mutations require a verified administrator with `EDIT` permission:

- `POST /api/v1/soil-profiles/enrichments/jobs/audit`
- `POST /api/v1/soil-profiles/enrichments/worker/run-queue`

Both routes derive the effective tenant and actor from the authenticated administrator. Caller-supplied identity headers are consistency checks only and are not mutation authority. Referenced farmers, parcels, and projects are resolved within the verified tenant, and inconsistent farmer/parcel/project combinations are rejected.

Manual audit events record the verified administrator in immutable metadata. Queue-worker responses and created job-audit rows identify the verified requesting administrator. Dry runs remain write-free, and live external provider execution remains governed by the existing provider policy.

## Platform tenant provisioning and final mutation classifications

`POST /api/v1/tenants` is a platform-level provisioning operation. It requires `MANAGE_USERS` and a verified `ENTERPRISE_ADMIN` whose authenticated tenant is `default`. Administrators from ordinary customer tenants cannot create peer tenants. Successful provisioning writes an immutable `CREATE_TENANT` audit event containing the target tenant, verified actor tenant, verified administrator, resulting tenant payload, reason, and timestamp.

The remaining POST routes are classified by behavior rather than treated as ordinary mutations:

- `POST /api/v1/auth/device` is an intentional public authentication exchange. It validates a registered device credential before issuing a JWT.
- `POST /api/v1/master-data/sync` is read-only reference transport. POST carries the client version manifest but performs no database writes.
- Project-village-resolution dry run and workflow-draft CSV validation require verified administrator permissions, derive tenant and actor from the authenticated principal, and remain database write-free.

## Broadcast read authorization

Broadcast administration reads require a verified administrator with `VIEW`.
This includes campaign listing and detail, delivery drilldown, audience preview,
and immutable broadcast-audit history. The tenant is derived from the verified
principal; `X-Tenant-ID` is only consistency context and cannot select another
tenant.

The farmer broadcast feed requires an authenticated human. Access is limited to
the farmer's linked user or an actively assigned user in a tenant-bounded farmer
project enrollment. Unrelated authenticated users receive
`BROADCAST_FARMER_ACCESS_DENIED`, and foreign-tenant farmers remain hidden.

## Weather snapshot reads

Tenant-wide weather snapshot list and latest-snapshot reads require a verified
administrator with `VIEW`. The routes derive both tenant and actor identity from
the authenticated principal; `X-Tenant-ID` and `X-Actor-ID` are consistency
checks, not sources of authority.

The read boundary preserves the existing weather filters while preventing
unauthenticated access, actor impersonation, tenant-header mismatch, and
cross-tenant snapshot disclosure.

## Sync operational reads

Full conflict administration and the operational sync dashboard require a
verified administrator with `VIEW`. These routes derive tenant and actor
identity from the authenticated principal and do not trust identity headers as
authority.

The Android pending-conflict feed uses role-neutral authenticated-human access.
It returns only redacted pending conflicts whose recorded `actor_id` matches the
verified caller, within the caller's verified tenant. Conflict resolution
continues to require administrative `EDIT`.

## Media asset detail reads

Media asset detail requires a verified authenticated human. Asset lookup is
bounded to the verified tenant and never trusts identity headers as authority.

The verified uploader may read the asset. Other callers must satisfy the
existing media persona scope: an authorized web administrator, the linked
farmer owner, or an actively assigned agent. Unrelated farmers and unassigned
agents are denied.

## Public runtime app bootstrap

`GET /api/v1/app-config/bootstrap` intentionally remains available before
authentication so Android and web clients can discover runtime branding,
localization, units, enabled modules, feature flags, form versions, and stable
client contracts.

The exception is restricted to this exact GET path. Administrative app-config
reads and all app-config mutations retain their existing authenticated
permission boundaries.

## Public crop master-data reference reads

The crop category, crop, variety, and lifecycle-template GET endpoints are
intentional unauthenticated reference-data reads. They expose active canonical
catalog records used to populate client selection controls and contain no
tenant, farmer, project-operational, or administrator data.

This exception applies only to database-read-only GET routes under the
master-data `/crops` router. Crop catalog mutations and operational crop data
retain their existing authentication, permission, tenant, and actor
requirements.

## Public geography reference reads

The geography hierarchy profile and canonical state, district, block, village,
LGD-code resolution, PIN-code lookup, and village-search GET endpoints are
intentional unauthenticated reference reads. They expose active government or
postal reference information used for enrollment, offline caching, and
location selection.

These exemptions are exact, GET-only route classifications. They do not apply
to geography imports, reviews, promotions, project matching, resolution
evidence, runtime activation, or other operational geography endpoints.

## Workflow catalog reads

Workflow catalog reads no longer trust caller-supplied tenant or actor headers as authorization.

Runtime catalog and published-preview routes require an authenticated human. They derive the tenant and actor from the verified principal. Tenant-wide catalog access remains available to an authenticated tenant member, while project-scoped catalog and preview requests require an enterprise administrator, a verified project role, or an actively enrolled farmer who owns the authenticated user identity.

Workflow governance reads require administrator `VIEW` permission:

- draft workflow preview;
- draft publish-impact analysis;
- legacy-cycle pin candidates;
- template version history;
- template audit history.

Draft validation requires administrator `EDIT` permission because validation writes an immutable audit event. That audit records the verified administrator rather than a caller-supplied actor.

Regression coverage is provided by `backend/scripts/test_workflow_catalog_read_auth_static.py` and `backend/scripts/test_workflow_catalog_read_auth_behavior.py`. Existing catalog, preview, enablement, draft, publishing, legacy-pin, version-assignment, and CSV-validation regressions use authenticated identities.
