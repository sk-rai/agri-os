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
Attachment creation and field-event mutations remain separate remediation
tranches and are not claimed as secured here.

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

This checkpoint changes only `POST /api/v1/media/attachments`. Attachment
listing, inline field-event attachment creation, and worker/sync materialisation
remain separate authorization tranches.
