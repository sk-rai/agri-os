# Tenant and actor trust-boundary audit — 2026-10-05

## Purpose

Inventory every FastAPI route before tightening authorization. A supplied `X-Tenant-ID` or `X-Actor-ID` is routing context, not proof of identity. Mutations must bind tenant and actor to a verified credential or an explicitly governed worker identity.

## Compatibility-first remediation

Do not add global authorization middleware in one step. Android sync, admin web, worker routes, public auth, and shared reference reads have different contracts. A global switch would cause broad failures without proving the correct rule.

The audit is read-only and does not automatically enforce policy.

## Remediation order

1. **Mutation routes first:** protect admin/backoffice POST, PUT, PATCH, and DELETE routes without a bearer/admin dependency.
2. Bind `X-Tenant-ID` to token/user tenant and reject disagreement.
3. Bind `X-Actor-ID` to token subject for human actions; use governed service principals for workers.
4. Add cross-tenant, cross-actor, inactive-user, expired-token, and missing-token tests per route family.
5. Classify non-reference reads and require VIEW permission for tenant/project data.
6. Keep genuinely shared reference endpoints explicitly allowlisted and read-only.

## Android and admin clients

- Admin web already sends bearer, tenant, and actor headers. Protected routes should use the shared admin dependency.
- Android must send bearer credentials on authenticated operational routes. A fixture using only headers is test debt, not a security contract.
- OTP request/verification and health remain public by design.
- Shared crop, input, form, workflow, and canonical geography reads require a separate exposure decision.

## Test gate per route family

- existing success behavior remains green with valid credentials;
- missing bearer returns 401;
- actor mismatch returns 403;
- token/header tenant mismatch returns 403;
- user/database tenant mismatch returns 403;
- inactive users fail authentication;
- project operations verify membership;
- cleanup and prior behavior suites pass.

## High-risk families to assess first

- broadcast administration;
- field-event and media mutations;
- workflow/crop-cycle/stage/activity mutations;
- tenant and company-discovery administration;
- CSV validate/apply/import surfaces;
- worker/provider execution and refresh routes.

## Implementation checkpoint

The first bounded remediation protects the eight broadcast-admin mutations with the shared admin dependency. Draft/content/audience edits require `EDIT`; publish, delivery generation/retry, expiry, and cancellation require `PUBLISH`. Behavior coverage verifies valid credentials as well as missing bearer, actor mismatch, and token/header tenant mismatch.

The existing farmer delivery read/ack mutations now use the shared authenticated-human dependency rather than admin authorization. Delivery ownership accepts the explicit delivery user, linked farmer user, or an active project assignment; unrelated identities fail closed. The audit classifier recognizes this shared principal as an authentication marker. Broadcast tenant-sensitive reads remain a subsequent authorization tranche.

Static source markers are triage evidence, not a security proof. Each flagged family needs behavior tests.

## Run

```bash
cd backend
../venv/bin/python scripts/test_tenant_actor_trust_boundary_audit_static.py
../venv/bin/python scripts/audit_tenant_actor_trust_boundary.py > /tmp/tenant-actor-trust-boundary-audit.json
```

## Media asset mutation checkpoint

The media asset creation and completion mutations now use the shared
authenticated-human dependency and explicit persona scope.

Tenant and uploader identity come from the verified principal. Personal-farmer,
explicitly assigned-agent, dual-persona, original-uploader, and bounded
web-admin cases have direct behavior coverage. Unassigned users, inactive
assignments, inactive project roles, uploader impersonation, and generic
agronomist-as-admin access fail closed.

Media attachment creation and field-event creation/status changes are
governed by their later, independently tested checkpoints.

## Generic media attachment checkpoint

`POST /api/v1/media/attachments` now uses verified human identity and no longer
trusts a tenant header as authorization.

The route verifies both asset and target scope, rejects cross-farmer and
cross-project linkage, keeps advisory publication web-admin-only, and fails
closed for generic target types without an explicit ownership mapping. Direct
behavior coverage includes farmer, parcel, assigned-agent field-event,
unassigned-agent, cross-farmer, cross-project, unsupported-target, missing
bearer, and tenant-mismatch cases.

`GET /api/v1/media/attachments` now requires verified human identity. Personal
farmers and assigned agents must specify an exact supported target and pass the
same persisted persona-scope authorization used for attachment creation.
Unassigned operational users fail closed, advisory reads and broad tenant
inventory remain web-admin-only, and the joined asset is independently
tenant-bounded. Direct behavior coverage includes farmer, parcel, assigned
field-event, unassigned-agent, advisory, missing-bearer, broad-operational-read,
admin-inventory, and tenant-mismatch cases.

Inline attachments created by query APIs and sync/worker materialisation remain
separate review tranches.

## Field-event mutation checkpoint

The audit scanner now retains the router identity from each decorator and
resolves the corresponding router prefix. This fixes classification for modules
that expose more than one `APIRouter`; field-event routes are now reported under
`/api/v1/field-events` rather than the media-router prefix.

Field-event creation and status mutations use verified human identity, derive
tenant and actor from the principal, enforce operational persona scope, and no
longer appear as unauthenticated mutation findings. Static and behavior
coverage verifies missing bearer, tenant mismatch, initial status, reporter
attribution, transition history, and the deterministic farmer-to-admin advisory
loop.

The field-event list and detail reads now require verified human identity and
apply tenant-bounded persona visibility. They no longer appear as unprotected
non-reference-read findings. Direct behavior coverage proves farmer,
assigned-agent, unassigned-agent, and web-admin visibility boundaries.

## Query-thread mutation checkpoint

The three direct query mutation routes now use verified human identity and no
longer trust tenant or actor headers as authorization. Thread creation,
message creation, workflow audit events, and status history derive their actor
from the authenticated principal.

Personal-farmer and explicitly assigned-agent capabilities are resolved from
persisted tenant-bounded relationships. Sender impersonation, unassigned-agent
access, cross-farmer inline assets, farmer workflow transitions, and
operational assignment changes fail closed. Direct behavior coverage verifies
farmer, assigned-agent, unassigned-agent, web-admin, actor-attribution,
attachment ownership, status-history, missing-bearer, and tenant-mismatch
cases.

The query list and detail routes now require verified human identity and
apply tenant-bounded personal-farmer or assigned-agent visibility. Inaccessible
details fail closed with `404`, unassigned agents receive an empty list, and
explicit web administrators retain tenant-wide visibility. Joined media assets
are independently tenant-bounded. These routes no longer appear as unprotected
non-reference-read findings.

Query sync materialisation remains a separate review tranche.

## Farmer and parcel mutation checkpoint

The five core farmer and parcel mutations now use verified human identity and
derive tenant and actor from the authenticated principal. They no longer appear
as unauthenticated, tenant-unbound, or actor-unbound mutation findings:

- farmer enrollment;
- farmer update;
- parcel creation;
- parcel update;
- parcel geometry update.

Authorization resolves persisted personal-farmer and assigned-agent
capabilities, with an explicit bounded web-admin bypass. Self-enrollment
requires the authenticated user's persisted mobile identity; assisted
enrollment does not impersonate the farmer. Geometry capture and enrollment
metadata record the verified actor.

Static and direct behavior coverage includes missing bearer, token/header
tenant mismatch, personal farmer operations, explicit assignment, unassigned
and unrelated denial, admin access, self-enrollment linkage, assisted
enrollment attribution, Android payload compatibility, DigiPin behavior, and
regression cleanup.

The core farmer and parcel list routes now require verified human identity,
derive tenant scope from the bearer principal, and filter operational results
through the union of personal and explicitly assigned farmer IDs. Unassigned
operational users receive empty collections and explicit web administrators
retain tenant-wide visibility. These two routes no longer appear as
unprotected non-reference-read findings.

## Farmer readiness and field-agent worklist read checkpoint

The profile-readiness and field-agent worklist routes now use verified human
identity and derive tenant scope from the bearer principal. Profile readiness
filters through personal and explicitly assigned farmer IDs, with a bounded
web-admin tenant-wide capability.

The field-agent worklist requires an active persisted agent persona, derives
the actor from the authenticated user, and always filters through explicit
farmer assignments. Its legacy actor query parameter is accepted only when it
matches the authenticated user. Static and behavior coverage verifies missing
bearer, tenant mismatch, actor impersonation, farmer, assigned-agent,
unassigned-agent, and web-admin boundaries. These routes no longer appear as
unprotected non-reference-read findings.
