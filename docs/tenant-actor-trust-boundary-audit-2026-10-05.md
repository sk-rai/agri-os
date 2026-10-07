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

This checkpoint does not include media attachment creation or field-event
creation/status changes. Those remain independently reviewable mutation
families.

## Generic media attachment checkpoint

`POST /api/v1/media/attachments` now uses verified human identity and no longer
trusts a tenant header as authorization.

The route verifies both asset and target scope, rejects cross-farmer and
cross-project linkage, keeps advisory publication web-admin-only, and fails
closed for generic target types without an explicit ownership mapping. Direct
behavior coverage includes farmer, parcel, assigned-agent field-event,
unassigned-agent, cross-farmer, cross-project, unsupported-target, missing
bearer, and tenant-mismatch cases.

`GET /api/v1/media/attachments`, inline attachments created by field-event and
query APIs, and sync/worker materialisation remain separate review tranches.
