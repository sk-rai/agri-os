# Authenticated-human boundary — 2026-10-05

## Purpose

Operational Android and field-agent mutations require verified human identity
without incorrectly requiring an admin role.

`AuthenticatedPrincipal` is derived from a verified JWT and an active persisted
user. `X-Tenant-ID` and `X-Actor-ID` remain routing context and must agree with
the verified token and persisted user.

## Verified invariants

- a bearer JWT is required;
- the JWT subject must resolve to an active user;
- `X-Actor-ID`, when supplied, must match the JWT subject;
- token, header, and persisted-user tenants must agree;
- the JWT device identity is retained for later device-sensitive policies;
- FARMER and FIELD_AGENT identities are valid human principals;
- authentication alone does not grant admin permissions.

## Compatibility boundary

This checkpoint introduces and tests the shared dependency but does not attach
it to existing operational routes. Existing behavior therefore remains
unchanged while the authentication primitive is validated.

Route integration will proceed in bounded families. Each family must update its
fixtures to send real bearer credentials and must prove:

- successful existing behavior with a valid identity;
- missing bearer rejection;
- actor and tenant mismatch rejection;
- inactive-user rejection;
- tenant and assignment isolation;
- database cleanup;
- adjacent regression suites remain green.

Admin permissions remain governed by `require_admin_permission`. Worker and
provider execution require a separate governed service-principal boundary.
Public OTP/login and explicitly approved shared reference reads remain outside
this human-mutation dependency.

## Admin reuse checkpoint

Admin authentication now reuses the shared JWT-subject, active-user, and actor
verification resolver. Admin-specific tenant errors, role permissions, project
membership, error codes, and response payloads remain governed by
`require_admin_permission`.

This refactor changes no route exposure and does not attach authenticated-human
enforcement to Android or field-agent endpoints.

## Broadcast delivery consumption checkpoint

The existing Android broadcast delivery read and acknowledge routes now require
the shared authenticated-human dependency. Their paths and response schemas are
unchanged.

Access is allowed only when the authenticated user is:

- the delivery's explicit user;
- the user linked to the delivery's farmer; or
- an actively assigned project user for that farmer.

Tenant identity is derived from the verified principal. Unrelated authenticated
users fail closed. Audit events identify the authenticated user and role rather
than treating the farmer record itself as the actor.

Backend Android fixtures now use a farmer bearer for delivery consumption.
Campaign creation, publication, generation, and terminal lifecycle operations
continue to use enterprise-admin authorization. This is a backend contract
hardening change and requires no Android UI or API-path modification.

## Media asset mutation checkpoint

Media asset creation and upload completion now require the shared authenticated
human boundary.

The server derives the tenant and uploader identity from the verified bearer
principal. A caller cannot impersonate another uploader. Operational access is
limited to:

- a farmer acting on their own linked farmer profile;
- an active agent or agronomist with an active agent profile, active project
  role, and explicit active farmer-project assignment;
- the original uploader completing their own asset;
- an explicitly administrative web role performing project administration.

An `AGRONOMIST` or `FIELD_AGENT` identity is not treated as a web administrator
merely because a generic permission map includes edit-like capabilities. The
same authenticated user can act through farmer and agent personas without a
second phone number, but each operation is checked against the selected
farmer/project context.

This checkpoint covers only media asset creation and upload completion.
Attachment creation and field-event mutations are governed by their later,
separately tested checkpoints.

Existing deterministic Android/backend fixtures now send real bearer identities
when they create or complete media assets. Endpoint paths and response schemas
remain unchanged.

## Generic media attachment mutation checkpoint

Generic media attachment creation now requires the shared authenticated-human
boundary. Tenant identity is derived from the verified principal, and access is
checked independently for both the media asset and its target.

The generic route currently authorises these persisted targets:

- `FARMER`, through personal-farmer or explicit assigned-agent scope;
- `PARCEL`, through its farmer and project;
- `FIELD_EVENT`, through its farmer and project;
- `ADVISORY`, meaning persisted broadcast content belonging to an active
  campaign, restricted to explicit web-admin roles.

Where both sides provide farmer or project context, the asset and target must
match. Cross-farmer and cross-project attachment attempts fail closed. The
attachment metadata records the verified actor as `created_by_user_id`; any
caller-supplied value for that key is overwritten by the server.

Other declared attachment entity types remain available to their owning APIs or
governed sync materialisers, but the generic endpoint rejects them with
`MEDIA_ATTACHMENT_TARGET_UNSUPPORTED` until an explicit ownership mapping is
implemented.

`GET /api/v1/media/attachments` now uses the same authenticated-human
boundary. Operational callers must provide an exact supported entity type and
entity ID; the target is authorised through personal-farmer or assigned-agent
scope before any attachments are returned. Broad tenant inventory and advisory
attachment listing remain restricted to explicit web-admin roles. Both the
attachment and joined asset are tenant-bounded by the verified principal.

Inline field-event attachment creation and worker/sync materialisation remain
separate authorization tranches.

## Field-event mutation checkpoint

`POST /api/v1/field-events` and
`PATCH /api/v1/field-events/{event_id}/status` now require the shared
authenticated-human boundary. Tenant and actor identity come from the verified
principal.

New events must start in `REPORTED`. The server derives the source from the
authenticated operational persona:

- a linked personal farmer becomes `FARMER_ANDROID`;
- an active, assigned organisation agent becomes `FIELD_AGENT_ANDROID`;
- an explicitly administrative web identity becomes `ADMIN_WEB`.

The human route clears external-provider identity fields rather than accepting
caller claims. Inline evidence assets must remain compatible with the event's
farmer and project. Reporter identity and later status actors are recorded from
the verified principal.

Status changes follow an explicit transition matrix. Operational status changes
require an active agent persona and explicit active farmer assignment, while
web administrators retain the bounded review capability. Only an authorised
web administrator may mark an event `ADVISORY_SENT`.

The deterministic advisory-loop fixture now uses the reporting farmer's bearer
for media upload and event creation, then a distinct enterprise-admin bearer
for review, advisory publication, delivery generation, and the final
`ADVISORY_SENT` transition. Endpoint paths and response schemas remain stable.

Field-event list and detail reads now use the same verified human identity.
Web administrators may read tenant events. Operational users are restricted to
events belonging to their linked personal farmers or explicitly assigned
farmers. Inaccessible detail records return `404` to avoid disclosing their
existence.

## Query-thread mutation checkpoint

`POST /api/v1/query-threads`,
`POST /api/v1/query-threads/{thread_id}/messages`, and
`PATCH /api/v1/query-threads/{thread_id}/status` now require the shared
authenticated-human boundary. Tenant and actor identity are derived from the
verified principal.

Personal farmers may create and message queries for their linked farmer
profile. Organisation agents require an active agent profile, active project
role, and explicit active farmer assignment. Unassigned agents fail closed.
Message sender type and user ID are server-derived, and caller attempts to
impersonate another sender are rejected.

Inline message assets must match the query thread's farmer and project.
Farmers cannot perform workflow transitions. Assigned agents may update query
workflow status, while assignment changes remain restricted to explicit
web-admin roles. Audit events and status history record the verified user and
resolved operational persona.

Query-thread list and detail reads now use the same authenticated-human
boundary. Personal farmers see only their linked farmer threads; assigned
agents see only explicitly assigned farmers; unassigned operational users
receive an empty list. Inaccessible detail records return `404`, while explicit
web administrators retain tenant-wide visibility. Joined attachment assets are
independently tenant-bounded.

Query sync materialisation remains a separate authorization tranche.

## Farmer and parcel mutation checkpoint

Core farmer and parcel mutations now require the shared authenticated-human
boundary:

- `POST /api/v1/farmers`;
- `PATCH /api/v1/farmers/{farmer_id}`;
- `POST /api/v1/parcels`;
- `PATCH /api/v1/parcels/{parcel_id}`;
- `PATCH /api/v1/parcels/{parcel_id}/geometry`.

Tenant and actor identity are derived from the verified bearer principal rather
than trusted request headers. Personal farmers may manage their linked farmer
profile and parcels. Organisation agents require an active agent profile,
active project access, and explicit active farmer assignment. Explicit
web-administrator roles retain tenant-bounded administration capability.

Farmer self-enrollment binds the new farmer profile to the authenticated user
only when the submitted mobile identity matches the persisted user. An
authorised project agent may enroll an assisted farmer without binding that
farmer to the agent's user identity. Enrollment metadata and geometry capture
record the authenticated actor.

Missing bearer, sender or actor impersonation, unrelated-farmer access,
unassigned-agent access, and token/header tenant mismatch fail closed. Existing
endpoint paths and response schemas remain stable.

`GET /api/v1/farmers` and `GET /api/v1/parcels` now use the same
authenticated-human and persona boundary. Personal farmers see only their
linked farmer profile and parcels. Assigned organisation agents see only
explicitly assigned farmers and their parcels. Unassigned operational users
receive empty lists, while explicit web administrators retain tenant-wide
visibility. Optional farmer, village, PIN-code, status, and pagination filters
operate only within that authorised scope.

## Farmer readiness and field-agent worklist checkpoint

`GET /api/v1/farmers/profile-readiness` and
`GET /api/v1/field-agent/worklist` now require the shared
authenticated-human boundary. Tenant and actor context are derived from the
verified bearer principal rather than trusted request headers or query
parameters.

Profile-readiness results use the same personal-farmer and explicitly assigned
farmer visibility as the core farmer and parcel reads. Unassigned operational
users receive an empty readiness collection, while explicit web administrators
retain tenant-wide visibility.

The field-agent worklist requires an active persisted agent persona and is
always restricted to explicitly assigned farmers, including when the legacy
`assigned_only` parameter is false. A supplied compatibility `actor_id` must
match the authenticated user. Missing bearer, actor impersonation, tenant
mismatch, unrelated-farmer discovery, and unassigned-farmer discovery fail
closed.

## Farmer enrollment and launch-context read checkpoint

`GET /api/v1/farmers/{farmer_id}/project-enrollments` and
`GET /api/v1/farmers/{farmer_id}/launch-context` now require the shared
authenticated-human boundary. Tenant scope is derived from the verified bearer
principal rather than a trusted request header.

Personal farmers may read only their linked farmer context. Organisation agents
may read only explicitly assigned farmers with active project access.
Unassigned agents and unrelated farmers receive `404` so the target farmer's
existence is not disclosed. Explicit web administrators retain tenant-wide
visibility. Enrollment payload project joins are independently tenant-bounded.

The enrollment-creation POST remains a separate mutation authorization
checkpoint.

## Farmer self-profile read checkpoint

`GET /api/v1/farmers/me` and `GET /api/v1/farmers/me/profile` now require the
shared authenticated-human boundary. Tenant and user identity come from the
verified bearer principal rather than trusted tenant or actor headers.

Self-profile resolution first uses the explicit tenant-bounded
`Farmer.user_id` relationship. For pre-existing profiles that have not yet
been linked, compatibility lookup uses only the persisted authenticated
user's mobile number; no caller-supplied mobile or actor identity is trusted.
Missing bearer and token/header tenant mismatch fail closed, while endpoint
paths and response schemas remain stable.

## Farmer by-mobile hydration checkpoint

`GET /api/v1/farmers/by-mobile/{mobile_number}` now requires the shared
authenticated-human boundary and derives tenant scope from the verified bearer
principal. The mobile path value is a lookup key, not authorization evidence.

Personal farmers may hydrate an explicitly linked profile, assigned agents may
hydrate explicitly assigned farmers, and explicit web administrators retain
tenant-wide lookup. A persisted-user mobile fallback supports legacy unlinked
farmer profiles only while the authenticated user has no explicit farmer
linkage. Missing bearer, unrelated or unassigned access, and tenant mismatch
fail closed without disclosing whether the requested mobile exists.

## Duplicate farmer administration checkpoint

`GET /api/v1/farmers/duplicates` now requires explicit admin `VIEW`
permission, and `POST /api/v1/farmers/{primary_farmer_id}/duplicates/archive`
requires admin `EDIT` permission. These are administrative data-quality
operations rather than farmer or field-agent capabilities.

Tenant and archival actor identity are derived from the verified admin
principal. Farmer personas cannot enumerate duplicate mobile identities or
archive profiles, and missing bearer, insufficient role, actor mismatch, and
tenant mismatch fail closed.

## Farmer project-enrollment creation checkpoint

`POST /api/v1/farmers/{farmer_id}/project-enrollments` now requires a
verified administrator with project-edit permission and an explicit web-admin
role. Tenant selection and enrollment attribution come from the authenticated
principal rather than request identity headers.

The target farmer, project, and attached parcels are independently
tenant-bounded. Missing bearer credentials and actor impersonation fail closed.
Operational agents continue to use the assisted farmer-enrollment workflow;
direct project-membership attachment remains an administrative operation.

## Project agent-assignment checkpoint

`POST /api/v1/farmers/{farmer_id}/project-agent-assignment` now requires a
verified administrator with project-edit permission and the explicit web-admin
capability. Tenant and assignment-event actor identity come from the verified
principal rather than request identity headers.

The target farmer, project, user, active agent profile, and active project role
are independently validated. An agent or agronomist cannot self-assign an
otherwise inaccessible project farmer.

This route remains project staffing administration. It does not implement the
future farmer-consented freelance specialist workflow documented in
`docs/freelance-agricultural-services-roadmap.md`.

## Farmer project-enrollment lifecycle status checkpoint

`PATCH /api/v1/farmer-project-enrollments/{enrollment_id}/status` now derives
tenant context exclusively from the verified administrator. It requires
project-edit permission plus the explicit web-admin capability.

The enrollment and its joined project are independently tenant-bounded.
Lifecycle metadata and immutable audit events record the authenticated
administrator. Missing bearer credentials, view-only access, actor
impersonation, and token/header tenant mismatch fail closed.

## Bulk project-enrollment lifecycle checkpoint

Project lifecycle preview now requires a verified, project-scoped web-admin
viewer. Bulk lifecycle apply requires verified project-edit permission and the
explicit web-admin edit capability. Both routes derive tenant context from the
authenticated principal and tenant-bound the project and enrollment rows.

Apply events record the verified administrator. Missing bearer credentials,
actor impersonation, tenant mismatch, and view-only apply attempts fail closed.
These project controls remain separate from future farmer-consented freelance
specialist engagements.

## Soil-profile mutation checkpoint

`POST /api/v1/soil-profiles` and `PATCH /api/v1/soil-profiles/{profile_id}`
now require a verified human principal. Tenant selection comes from the bearer
identity rather than caller-supplied tenant or actor headers.

Personal farmers may manage their own soil profiles, assigned project agents
may manage profiles for explicitly assigned farmers, and explicit web
administrators retain tenant-wide edit capability. Parcel/farmer linkage and
existing profiles are tenant-bounded. Missing bearer, unrelated or unassigned
personas, actor impersonation, and tenant mismatch fail closed.

## Trusted soil-enrichment ingestion checkpoint

The SoilGrids fetch, SHC/SLUSI manual capture, SHC/SLUSI point capture,
and direct soil-enrichment ingestion routes now require a verified
administrator with edit permission. An explicit web-administrator boundary
prevents farmer and field-agent personas from writing trusted provider
snapshots.

Tenant selection and ingestion attribution come from the verified principal.
Parcel lookup is independently tenant-bounded, and each stored snapshot records
the authenticated administrator in its provenance metadata. Missing bearer
tokens, actor impersonation, tenant mismatch, and non-administrator ingestion
fail closed.

These routes represent trusted data ingestion. They do not grant agronomists
or field agents access to independent farmers. Future freelance agricultural
services remain a separate, farmer-consented and revocable engagement model.

## Crop-cycle mutation checkpoint

Crop-cycle creation, crop-stage transition, explicit crop-cycle completion,
and crop-activity logging now require the shared authenticated-human boundary.
Tenant and actor identity come from the verified bearer principal rather than
caller-supplied tenant or actor headers.

Creation resolves the target farmer exclusively through the tenant-bounded
parcel relationship. A supplied farmer identifier must match that persisted
relationship. The former persisted-mobile and arbitrary first-farmer tenant
fallbacks have been removed.

Personal farmers may operate their own crop cycles, explicitly assigned
project agents may operate their assigned farmers' cycles, and explicit web
administrators retain tenant-wide edit capability. Missing bearer, actor
impersonation, tenant mismatch, unrelated or unassigned personas, and
farmer/parcel mismatch fail closed. Stage, activity, completion, and audit
attribution use the authenticated actor.

## Offline operational sync checkpoint

`POST /api/v1/sync/events` now requires the shared authenticated-human
boundary. Tenant and actor identity are derived exclusively from the verified
bearer principal; caller-supplied tenant and actor headers are compatibility
assertions and must match that identity.

Each event is authorized independently. Personal farmers may sync their own
profiles and related operational records, explicitly assigned project agents
may sync assigned farmers, and edit-capable web administrators retain
tenant-wide operational scope. An independent farmer may create their own
profile only when the submitted mobile matches the persisted authenticated
user; the resulting farmer is linked to that user. An active project agent may
create a farmer only through a project they can access, and the authenticated
agent is persisted as the assignment and enrollment actor.

Authorization preserves partial-batch behavior: permitted events can commit
while denied events return `SYNC_SCOPE_DENIED` in `failed[]`. Denied events are
not materialized or recorded as successfully processed. Dependency,
idempotency, conflict, and audit behavior remain per event, with audit actor
attribution derived from the verified principal.

Persistent Android verification fixtures now require
`ANDROID_SYNC_BEARER_TOKEN` and `ANDROID_SYNC_ACTOR_ID`; they do not create
users implicitly. Self-contained regressions create temporary authenticated
administrators and remove their tenant, sync, conflict, and audit rows.

This project-assignment authority does not establish a freelance-service
relationship. Future independent agronomist access remains subject to the
separate farmer-consented, purpose-limited, time-bounded, and revocable
engagement model.

## Sync conflict-resolution checkpoint

`PATCH /api/v1/sync/conflicts/{conflict_id}` now requires a verified
administrator with `EDIT` permission. Tenant and resolver identity are derived
from the authenticated admin principal; `X-Tenant-ID` and `X-Actor-ID` remain
compatibility assertions and cannot select another tenant or actor.

The selected pending conflict and all duplicate pending rows for the same sync
event are tenant-bounded before resolution. Each updated conflict records the
authenticated administrator in `resolved_by`, and the immutable
`CONFLICT_RESOLVED` audit entry uses the same verified actor.

Missing bearer credentials, view-only administrators, actor impersonation,
tenant mismatch, and repeated resolution fail closed. Conflict strategy,
duplicate-row resolution, dashboard counts, audit-chain integrity, and
regression cleanup remain covered.

## Crop-climate suitability publishing checkpoint

`POST /api/v1/crop-catalog/suitability-overrides` now requires a verified
administrator with `PUBLISH` permission. Tenant and publisher identity are
derived from the authenticated principal; caller-supplied tenant and actor
headers cannot select the stored tenant or `published_by` value.

When an override names a project, the project must be active and belong to the
authenticated tenant. Crop and climate-region reference validation remains in
place. Missing bearer credentials, insufficient publishing permission, actor
impersonation, tenant mismatch, malformed project identifiers, and
foreign-tenant projects fail closed.

## Finance report configuration checkpoint

Finance report configuration validation and publishing now use verified
administrator identity. Validation requires edit permission, while publishing
requires the narrower publish permission. Tenant and actor identity come from
the authenticated principal rather than caller-supplied identity headers.

An optional project scope must resolve to an active project in the verified
tenant. Cross-tenant or inactive project scopes fail closed. Published and
archived configuration versions record the authenticated publisher, while the
profit-and-loss formula remains fixed and non-executable.

## Broadcast administration checkpoint

Broadcast campaign creation, content editing, audience-rule editing,
publication, delivery generation, delivery retry, expiry, and cancellation now
derive tenant and actor identity from the verified administrator principal.

Draft editing requires edit permission. Publication and all delivery or
terminal lifecycle operations require publish permission. Caller-supplied
creator, approver, and lifecycle actor identifiers are retained only for
request compatibility and do not control stored attribution. Optional campaign
project scope must identify an active project in the authenticated tenant.

## Product catalog administration checkpoint

Seven product-catalog mutations now derive tenant and actor identity from the
verified administrator: CSV application, manufacturer creation and update,
product creation and update, package addition, and project product approval.

Global catalog maintenance retains `EDIT`; project approval retains
project-scoped `PROJECT_EDIT`. Every resulting product-catalog audit event
records the authenticated administrator. Missing bearer credentials,
insufficient permission, actor impersonation, tenant mismatch, and unassigned
project access fail closed.

## Weather administration checkpoint

Six backend weather mutations now derive tenant and actor identity from the
verified administrator: provider configuration, due-adapter execution, manual
refresh recording, single-adapter execution, manual snapshot creation, and
refresh-worker execution.

All retain edit permission. Provider and snapshot writes carry backend-owned
administrative attribution metadata. Missing bearer credentials, insufficient
permission, actor impersonation, tenant mismatch, and cross-tenant provider
selection fail closed.

## Identity administration checkpoint

The agent-profile and project-access mutation routes require an authenticated administrator with `MANAGE_USERS`.

The routes derive `tenant_id` and `actor_id` from the verified principal, reject actor impersonation and tenant mismatch, tenant-bound target users, profiles, and projects, and persist verified administrator attribution in `tenant_user_access_audit_events`.

## Runtime app configuration checkpoint

Tenant and project runtime app-configuration mutations now resolve tenant and
actor exclusively from the authenticated administrator. Missing bearer
credentials, actor impersonation, token/header tenant mismatch, foreign-tenant
resources, and insufficient permissions are rejected before configuration is
changed.

Tenant changes write `tenant_app_config_audit_events`; project changes write
`project_app_config_audit_events`. Both records preserve the verified actor,
scope, reason, patch, affected sections, and immutable before/after
configuration snapshots.

## Company-discovery CSV checkpoint

Company-discovery CSV validation and import now require an authenticated
administrator with `EDIT`. Tenant and actor identity come exclusively from the
verified principal. Missing bearer credentials, view-only roles, actor
impersonation, and token/header tenant mismatch are rejected before processing
or persistence.

Validation responses identify the verified validator. Imported candidate
metadata preserves importer, import timestamp, source filename, CSV line, and
schema version. A batch-level immutable audit records the verified
administrator, candidate IDs, filename, and imported count.

## Project geography import-preview checkpoint

Project geography import preview now derives tenant and actor from the verified
administrator and requires project-scoped `PROJECT_EDIT`. Missing bearer
credentials, view-only roles, unassigned project administrators, actor
impersonation, tenant mismatch, and foreign-tenant project access are rejected.

Successful previews report verified attribution while preserving the
read-only contract. Regression coverage confirms that project geography,
project configuration, and immutable audit-event counts remain unchanged.

## Workflow project override checkpoint

Project workflow override creation and archival now cross the authenticated
human boundary through `PROJECT_EDIT` with project-scoped authorization. Both
routes derive tenant and actor identity from the verified administrator,
tenant-bound the project and selected workflow records, and reject tenant or
actor impersonation.

Successful creation records
`CREATE_PROJECT_WORKFLOW_OVERRIDE`; archival records
`ARCHIVE_PROJECT_WORKFLOW_OVERRIDE`. The immutable events preserve the verified
administrator and the applicable override state.

## Geography review mutation checkpoint

Five shared geography evidence-review mutations now require the authenticated
administrator to belong to the `default` platform tenant. This prevents
administrators from an ordinary tenant from changing national NWDP, CoRE/LGD,
or village-resolution evidence queues. Each mutation derives both tenant and
actor identity from the verified principal and preserves verified reviewer
attribution.

The disabled NWDP project-matching apply endpoint now uses project-scoped
`PROJECT_EDIT`, tenant-bounds the selected project, reports the verified actor,
and remains a no-write `501` contract.

## Soil enrichment operations checkpoint

Soil-enrichment job-audit creation and queue-worker execution now cross the authenticated-human boundary through verified administrator principals. Both mutations require `EDIT`, derive tenant and actor identity from the verified principal, reject actor impersonation and tenant mismatch, and tenant-bound every supplied farmer, parcel, and project reference.

Worker dry runs remain write-free. Non-dry worker audit rows and manual job-audit rows preserve verified administrator attribution. This checkpoint does not enable live provider execution or grant Android clients direct provider access.

## Final mutation-boundary closure

Tenant provisioning now requires a verified platform administrator: `MANAGE_USERS`, role `ENTERPRISE_ADMIN`, and authenticated tenant `default`. Caller identity headers are consistency checks only. The successful operation preserves immutable target-tenant and administrator attribution.

Device login remains intentionally unauthenticated because it is itself a credential-verification boundary. It issues a bearer token only after matching the registered device key and device identifier.

Master-data sync is explicitly classified as read-only reference transport despite using POST for its client version manifest. Project-village-resolution dry run and workflow CSV draft validation derive tenant and actor from verified administrators and do not write application state.

## Broadcast read authorization checkpoint

The six non-reference broadcast GET routes now cross a verified human boundary.
Five administration reads require `VIEW`; the farmer feed requires a persisted
authenticated human and explicit farmer ownership or active assignment. Tenant
and actor context are derived from the verified principal, actor impersonation
and tenant-header mismatch are rejected, and foreign resources are not exposed.

## Weather snapshot read checkpoint

The weather snapshot list and latest-snapshot endpoints now require authenticated
administrative `VIEW` access. Both routes use the verified principal for tenant
and actor identity and no longer trust identity headers directly.

Regression coverage verifies missing-bearer rejection, actor and tenant mismatch
handling, authorized reads, existing snapshot behavior, and tenant isolation.

## Sync operational read checkpoint

Conflict list/detail and operational dashboard reads now require administrative
`VIEW`. The mobile pending-conflict feed requires an authenticated human and is
restricted to conflicts created by that verified actor's own sync submissions.

Regression coverage verifies missing-bearer rejection, actor impersonation and
tenant mismatch rejection, administrator read access, submitter visibility,
non-submitter isolation, conflict resolution, and immutable audit attribution.

## Media asset detail read checkpoint

`GET /api/v1/media/assets/{asset_id}` now requires role-neutral authenticated
human access and derives tenant and actor identity from the verified principal.

The route permits the verified uploader and otherwise reuses the established
farmer/agent/admin media scope. Regression coverage verifies missing-bearer,
actor-impersonation, tenant-mismatch, farmer ownership, active assignment,
administrator access, and unrelated-persona denial.

## Public app-bootstrap classification checkpoint

The runtime app-bootstrap endpoint is an intentional pre-login read rather than
an authenticated-human endpoint. It returns a fixed client configuration
contract and remains database read-only.

The trust-boundary auditor classifies only the exact
`GET /api/v1/app-config/bootstrap` path as public. The classification is
method-constrained and does not extend to app-config mutations or administrative
configuration reads.

## Crop master-data reference classification checkpoint

The tenant/actor audit explicitly classifies the four active crop master-data
GET routes as reference transport: crop categories, crops, crop varieties, and
crop lifecycle templates. These routes remain available before authentication
because they return global canonical lookup data required by client forms and
bootstrap flows.

The classification is GET-constrained and does not exempt crop mutations or
tenant/project operational reads. Static regression coverage verifies the
routes remain active-only and database read-only.

## Geography reference classification checkpoint

Eight geography GET routes are explicitly classified as reference transport:
the static hierarchy profile plus active state, district, block, village,
LGD-code, PIN-code, and village-search lookups. The routes expose no tenant,
project, farmer, or administrator records and perform no database writes.

The auditor uses exact route matches instead of a broad `/geography` prefix,
ensuring operational geography routes continue to require their established
authentication, permission, tenant, and actor boundaries.

## Workflow catalog read checkpoint

The workflow catalog read boundary now separates runtime human access from administrative governance access.

`GET /api/v1/workflow-catalog/enabled-crop-workflows` and the published workflow-preview route require an authenticated human and derive the tenant and actor from the verified principal. Optional project scope is tenant-bounded and permits only an enterprise administrator, an assigned project persona, or a farmer with an active project enrollment linked to the authenticated user.

Draft preview, publish-impact analysis, legacy pin reporting, template version history, and template audit history require administrator `VIEW`. Draft validation requires administrator `EDIT` because it creates an immutable validation audit event.

Missing bearer credentials, actor impersonation, tenant mismatch, unrelated project access, and insufficient administrator permissions are covered by behavior regression tests. Internal draft mutation handlers render their response through the internal preview renderer rather than calling the protected HTTP route function directly.
