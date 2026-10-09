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
