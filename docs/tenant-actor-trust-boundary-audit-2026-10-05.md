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

## Farmer enrollment and launch-context read checkpoint

The farmer project-enrollment list and launch-context routes now require
verified human identity and derive tenant scope from the bearer principal.
Both apply personal-farmer or explicitly assigned-agent visibility and return
`404` for inaccessible farmers to avoid existence disclosure.

Explicit web administrators retain tenant-wide visibility, and joined project
records are independently tenant-bounded. Static and behavior coverage verifies
missing bearer, tenant mismatch, personal farmer, assigned agent, unassigned
agent, unrelated farmer, web administrator, and post-completion launch
behavior. These GET routes no longer appear as unprotected non-reference-read
findings. The POST route sharing the project-enrollment path remains a separate
mutation finding.

## Farmer self-profile read checkpoint

The farmer self-profile and self-hydration GET routes now require verified
human identity and derive tenant and user scope from the bearer principal.
Both routes resolve an explicit tenant-bounded farmer/user relationship first,
with a persisted-user mobile fallback for legacy unlinked profiles.

Static and direct behavior coverage verifies missing bearer, tenant mismatch,
explicit linked-farmer precedence, persisted-mobile compatibility, and
regression cleanup. These routes no longer appear as unprotected
non-reference-read findings.

## Farmer by-mobile hydration checkpoint

The by-mobile farmer hydration route now requires verified human identity,
derives tenant scope from the bearer principal, and authorizes the selected
farmer through personal linkage, active assignment, or bounded web-admin
scope. Legacy compatibility uses only the persisted authenticated user's
mobile and is disabled after explicit farmer linkage exists.

Static and behavior coverage verifies missing bearer, personal farmer,
assigned agent, unassigned agent, unrelated farmer, web administrator,
persisted-mobile compatibility, tenant mismatch, and non-disclosing `404`
responses. The route no longer appears as an unprotected non-reference-read
finding.

## Duplicate farmer administration checkpoint

The duplicate-farmer inventory and archive routes now use verified admin
authorization. Listing requires `VIEW`; archival requires `EDIT`. Tenant scope
and archive attribution come from the authenticated principal rather than
trusted tenant or actor headers.

Behavior coverage verifies missing bearer, farmer-role denial, authorised
inventory, authorised archival, and verified actor attribution. Neither route
remains in the unauthenticated read or mutation findings.

## Farmer project-enrollment creation checkpoint

The farmer project-enrollment creation route now requires a verified
administrator with project-edit permission and the explicit web-admin
capability. Tenant context and enrollment actor attribution are derived from
the authenticated principal.

Farmer, project, and parcel lookups are tenant-bounded. Static and behavior
coverage verifies missing bearer rejection, actor-impersonation rejection,
verified administrator attribution, idempotent enrollment updates, and
regression cleanup. This POST route no longer appears as an unauthenticated
mutation finding.

## Project agent-assignment checkpoint

The project-agent assignment mutation now requires verified project-edit
permission plus the explicit web-admin boundary. Tenant context and assignment
actor attribution derive from the authenticated administrator.

Farmer, project, target user, active agent profile, and active project role are
validated before assignment. Static and behavior coverage verifies missing
bearer rejection, agent self-assignment denial, administrator impersonation
denial, verified actor attribution, worklist visibility after assignment, and
cleanup.

Future freelance specialist services for independent farmers remain a separate
farmer-consented relationship and are not represented by this route.

## Farmer project-enrollment lifecycle status checkpoint

The single-enrollment lifecycle status mutation now requires verified
project-edit permission and the explicit web-admin boundary. Tenant identity
comes from the authenticated principal rather than the request header.

The enrollment and joined project are tenant-bounded, and lifecycle metadata
plus audit events record the verified administrator. Regression coverage
verifies missing bearer, view-only denial, actor impersonation denial, tenant
mismatch denial, successful completion, audit attribution, Android hydration
fallback to self-service, and cleanup.

## Bulk project-enrollment lifecycle checkpoint

The lifecycle preview and apply routes now derive tenant context from verified
project-scoped admin principals. Preview requires view permission plus the
explicit web-admin boundary; apply requires project-edit permission plus the
web-admin edit boundary.

Project and enrollment queries are tenant-bounded, and bulk apply audit events
record the verified administrator. Regression coverage verifies missing bearer,
actor impersonation, tenant mismatch, view-only preview, view-only apply denial,
successful lifecycle changes, audit attribution, hydration fallback, and
cleanup. Neither route remains in the unauthenticated or header-trust findings.

## Soil-profile mutation checkpoint

The core soil-profile create and update routes now require the shared verified
human principal, derive tenant context from that principal, and apply persisted
personal-farmer or assigned-agent scope with an explicit web-admin boundary.

Create validates tenant-bounded parcel/farmer linkage; update tenant-bounds the
profile before authorization. Static and direct behavior coverage verifies
missing bearer, personal farmer access, assigned-agent access, unrelated and
unassigned denial, administrator access, tenant mismatch, Android payload
compatibility, and cleanup. These two routes no longer appear as unauthenticated
mutation findings.

## Soil-enrichment mutation checkpoint

Four soil-enrichment mutations now use verified administrative identity:
SoilGrids baseline fetch, SHC/SLUSI manual capture, SHC/SLUSI point capture,
and direct enrichment snapshot ingestion. Each requires edit permission plus
the explicit web-administrator boundary.

The routes derive tenant and actor from the verified principal, tenant-bound
the parcel lookup, and record the authenticated administrator in provenance
metadata. Static and behavior coverage verifies missing bearer, farmer-persona
denial, actor impersonation, tenant mismatch, successful ingestion, and actor
attribution. These routes no longer appear as unauthenticated mutation,
tenant-trust, or actor-trust findings.

Freelance specialist engagements remain outside this administrative boundary
and require a future farmer-consent grant model.

## Crop-cycle mutation checkpoint

Four crop-cycle mutations now use verified human identity: cycle creation,
stage transition, explicit cycle completion, and activity logging. Each derives
tenant and actor from the bearer principal and applies personal-farmer,
explicitly assigned-agent, or bounded web-administrator authorization.

Cycle creation tenant-bounds both parcel and farmer and requires any supplied
farmer identifier to match the parcel's persisted farmer. The legacy
mobile-number inference and arbitrary first-farmer tenant fallback have been
removed. Existing cycles and stage instances are tenant-bounded before
mutation, and audit records use the verified actor.

Static and direct behavior coverage verifies missing bearer, actor
impersonation, tenant mismatch, personal-farmer access, assigned-agent access,
unassigned and unrelated denial, administrator access, farmer/parcel mismatch,
verified lifecycle attribution, and regression cleanup. These routes no longer
appear as unauthenticated mutation findings.

## Offline sync mutation checkpoint

`POST /api/v1/sync/events` previously claimed JWT protection while accepting
`X-Tenant-ID` and `X-Actor-ID` as authoritative values. Because the endpoint
materializes farmers, parcels, geometry, soil profiles, project enrollments,
query records, field reports, crop cycles, stages, and activities, this was a
high-impact tenant and actor trust boundary.

The route now requires `AuthenticatedPrincipal`, derives tenant and actor from
the verified bearer, and partitions each batch through a dedicated sync
persona-authorizer before conflict detection or materialization. Existing
farmer ownership, active project assignment, bounded agent project access, and
explicit edit-capable web-administrator authority determine event access.

Independent self-enrollment binds the farmer to the authenticated user's
persisted mobile identity. Agent enrollment records the authenticated agent
and persists the assignment. Unauthorized events return
`SYNC_SCOPE_DENIED`; authorized events in the same batch continue through
dependency, conflict, idempotency, materialization, and audit processing.

Static and behavior coverage verifies missing bearer, actor impersonation,
tenant mismatch, personal and assigned access, unassigned and unrelated
denial, administrator access, self- and agent-enrollment attribution,
mixed-batch isolation, dependency behavior, conflict behavior, idempotency,
and regression cleanup. All in-repository `/sync/events` callers now either
use authenticated test identities or require explicit persisted-fixture bearer
credentials.

## Sync conflict-resolution mutation checkpoint

The sync conflict-resolution mutation previously trusted caller-supplied
`X-Tenant-ID` and `X-Actor-ID` values when selecting pending conflicts,
updating duplicate rows, writing `resolved_by`, and appending the immutable
audit event.

The route now requires `AdminPermission.EDIT`, derives tenant and actor from
the verified `AdminPrincipal`, tenant-bounds both the selected conflict and
duplicate pending conflicts, and records the verified administrator in the
conflict rows and `CONFLICT_RESOLVED` audit entry.

Static and lifecycle coverage verifies missing bearer, insufficient
permission, actor impersonation, tenant mismatch, successful resolution,
verified attribution, duplicate-resolution denial, audit-chain integrity, and
fixture cleanup. The route no longer appears as an unauthenticated mutation
finding.

## Crop-climate suitability override checkpoint

The suitability-override publishing route previously accepted unauthenticated
requests and trusted `X-Tenant-ID` and `X-Actor-ID` when writing runtime
agronomic guidance.

The route now requires `AdminPermission.PUBLISH`, derives tenant and publisher
from the verified `AdminPrincipal`, validates any supplied project inside that
tenant, and stores the authenticated administrator in `published_by`.

Static and behavior coverage verifies missing bearer, insufficient permission,
actor impersonation, tenant mismatch, foreign-project denial, successful
publishing, verified attribution, and cleanup. The route no longer appears as
an unauthenticated mutation finding.

## Finance report configuration checkpoint

The finance report configuration validation and publishing mutations now use
the shared administrator authorization boundary. Validation requires edit
permission; publishing requires publish permission.

Both routes derive tenant scope from the verified administrator. Publishing
also derives version attribution from that administrator for both publication
and archival. Optional project identifiers are checked against an active
project in the authenticated tenant, and caller-supplied tenant or actor
headers are not trusted by the route implementation.

Static and behavior coverage verifies missing bearer, insufficient permission,
actor impersonation, tenant mismatch, cross-tenant project denial, successful
validation and publishing, version archival, verified attribution, and fixture
cleanup.

## Broadcast administration checkpoint

Eight broadcast administration mutations now use typed verified administrator
principals: campaign creation, content addition, audience-rule addition,
publication, delivery generation, delivery retry, expiry, and cancellation.

The routes derive tenant and actor identity from the authenticated principal.
Creation tenant-bounds optional project scope. Persisted creator and approver
fields and every administrative broadcast audit event use the verified
administrator rather than request-body attribution fields.

Static and behavior coverage verifies missing bearer, actor impersonation,
tenant mismatch, insufficient farmer permission, invalid project scope,
verified creation and publication attribution, all eight administrative audit
actions, and regression cleanup.

## Product catalog mutation checkpoint

Seven product-catalog mutation routes previously passed a typed administrator
to a shared audit helper but did not expose their verified actor derivation at
the route boundary. They also continued to pass the asserted tenant header
into mutation audit and approval persistence.

The routes now bind tenant and actor from `AdminPrincipal`, pass those explicit
values to the audit helper, and tenant-bound import-batch and project-approval
writes with the verified tenant. Project product approval retains
project-scoped authorization.

Static and behavior coverage verifies permissions, missing bearer credentials,
actor impersonation, tenant mismatch, unassigned project denial, successful
catalog operations, verified audit attribution, and regression cleanup.

## Weather administration mutation checkpoint

Six weather mutations previously used authenticated admin dependencies but
continued to select and persist weather state using the asserted tenant header,
without explicit verified actor attribution at the route boundary.

The routes now derive tenant and actor from `AdminPrincipal`, tenant-bound all
provider and snapshot operations with that verified tenant, and persist
backend-owned administrative actor/action metadata for provider configuration,
refreshes, adapter runs, worker runs, and manual snapshots.

Static and behavior coverage verifies edit permission, missing bearer
credentials, insufficient permission, actor impersonation, tenant mismatch,
verified attribution across all six operations, tenant isolation, existing
adapter behavior, and fixture cleanup.

## Identity administration mutation checkpoint

The following identity-administration mutations now satisfy the authenticated tenant-and-actor boundary:

- `POST /api/v1/admin/agent-profiles`
- `PATCH /api/v1/admin/agent-profiles/{profile_id}`
- `PUT /api/v1/admin/users/{user_id}/projects/{project_id}`
- `DELETE /api/v1/admin/users/{user_id}/projects/{project_id}`

All four require `MANAGE_USERS`, derive tenant and actor from `AdminPrincipal`, tenant-bound selected records, reject unverified identity headers, and write audit events attributed to the verified administrator.

## Runtime app configuration mutation checkpoint

The tenant and project app-configuration PATCH routes now satisfy the verified
tenant/actor boundary:

- bearer authentication and explicit administrative permission are required;
- tenant identity and actor identity come from the verified principal;
- project lookup is tenant bounded and project authorization is scoped;
- caller-supplied identity headers cannot become mutation authority;
- successful writes persist immutable verified-administrator attribution.

The trust-boundary audit reports no mutation findings for
`update_tenant_app_config` or `update_project_app_config`.

## Company-discovery CSV mutation checkpoint

The company-discovery CSV validation and import routes now satisfy the verified
tenant/actor boundary:

- both routes require bearer authentication and `EDIT`;
- tenant and actor derive from the verified administrator;
- imported candidates are persisted only in the verified tenant;
- identity headers cannot become mutation authority;
- validation reports verified attribution;
- import writes candidate provenance and one immutable batch audit.

The trust-boundary audit reports no findings for
`validate_company_discovery_csv` or `import_company_discovery_csv`.

## Project geography import-preview checkpoint

The project geography import-preview POST route now satisfies the verified
tenant/actor boundary:

- bearer authentication and project-scoped `PROJECT_EDIT` are required;
- project lookup is bounded by the verified tenant;
- actor identity derives from the verified principal;
- caller-supplied identity headers cannot become authority;
- the response reports verified tenant and previewing administrator;
- the route performs no database writes.

The trust-boundary audit reports no finding for
`preview_project_geography_scope_import`.

## Workflow project override mutation checkpoint

The two project workflow override mutations now expose authenticated tenant and
actor markers:

- `POST /api/v1/workflow-catalog/projects/{project_id}/workflow-overrides`
- `DELETE /api/v1/workflow-catalog/projects/{project_id}/workflow-overrides/{override_id}`

Both require project-scoped `PROJECT_EDIT`, derive `tenant_id` and `actor_id`
from the verified administrator, tenant-bound project and workflow resources,
and avoid direct identity-header authority. Creation and archival write
immutable workflow audit events attributed to the verified administrator.

## Geography review mutation boundary checkpoint

The following global-reference mutations now derive tenant and actor from the
verified administrator and reject principals outside the `default` platform
tenant:

- `PATCH /geography/nwdp-boundary-candidates/{candidate_id}/review`
- `PATCH /geography/nwdp-demographic-profiles/{profile_id}/review`
- `PATCH /geography/core-lgd-mapping-review/{mapping_id}/review`
- `POST /geography/village-resolution/reviews`
- `POST /geography/village-resolution/reviews/{review_id}/second-review`

The disabled
`POST /geography/nwdp-boundary-project-matching/apply` contract now requires
project-scoped `PROJECT_EDIT`, derives verified tenant and actor identity, and
tenant-bounds the project. It remains write-free and disabled.

The trust-boundary audit no longer reports these six routes as mutations missing
tenant or actor markers.

## Soil enrichment operational mutation checkpoint

The tenant/actor audit now classifies these mutations as secured:

- `POST /api/v1/soil-profiles/enrichments/jobs/audit`
- `POST /api/v1/soil-profiles/enrichments/worker/run-queue`

Both require authenticated `EDIT` permission and derive `tenant_id` and `actor_id` from the verified administrator. The routes do not use `X-Tenant-ID` or `X-Actor-ID` as mutation authority. Optional farmer, parcel, project, and demo-target references are tenant-bounded and relationally validated.

Manual audit creation records `recorded_by` and `recorded_via=ADMIN_API`. Worker-created job-audit rows record `requested_by`, and the response reports the verified requester. Dry runs do not write audit or snapshot rows.

## Final mutation trust-boundary closure

The route audit now reports zero mutation findings.

The final classifications are:

- `POST /api/v1/tenants`: authenticated platform provisioning, restricted to a verified `ENTERPRISE_ADMIN` in tenant `default`, with immutable `CREATE_TENANT` attribution.
- `POST /api/v1/auth/device`: intentional public authentication exchange that validates device credentials before token issuance.
- `POST /api/v1/master-data/sync`: read-only reference transport using POST for a version manifest.
- project-village-resolution dry run: authenticated, project-scoped, verified-tenant and verified-actor preview with no database writes.
- workflow-draft CSV validation: authenticated, verified-tenant and verified-actor validation with no database writes.

The auditor explicitly distinguishes public authentication and read-only POST reference transport from business mutations. This classification does not exempt any state-changing business route from authentication, tenant, or actor requirements.

## Broadcast read boundary checkpoint

The campaign list/detail, delivery list, audience preview, broadcast audit, and
farmer-feed GET routes no longer appear as unauthenticated non-reference reads.
Administrator reads derive tenant and actor from a verified `VIEW` principal.
The farmer feed derives the same identity from role-neutral human
authentication and enforces linked-owner or active-assignment access. Static,
behavior, legacy broadcast, tenant-isolation, cleanup, and live route-audit
checks cover this boundary.

## Weather snapshot read boundary checkpoint

The following non-reference reads now satisfy the authenticated tenant/actor
boundary:

- `GET /api/v1/weather/snapshots`
- `GET /api/v1/weather/snapshots/latest`

Both require administrative `VIEW`, derive tenant and actor from the verified
principal, and reject identity-header impersonation or mismatch. The route audit
reports no findings for either endpoint. After this tranche, 45 unauthenticated
non-reference read findings remain and mutation findings remain at zero.

## Sync operational read boundary checkpoint

Four non-reference reads now satisfy authenticated tenant/actor boundaries:

- `GET /api/v1/sync/conflicts`
- `GET /api/v1/sync/conflicts/{conflict_id}`
- `GET /api/v1/sync/conflicts/pending`
- `GET /api/v1/dashboard/operational`

The conflict list/detail and dashboard require administrative `VIEW`. The
Android feed requires an authenticated human and filters by both verified tenant
and `SyncConflict.actor_id`. The audit reports no findings for these routes.
After this tranche, 41 unauthenticated non-reference read findings remain and
mutation findings remain at zero.

## Media asset detail read boundary checkpoint

`GET /api/v1/media/assets/{asset_id}` now requires an authenticated human,
derives tenant and actor from the verified principal, and tenant-bounds the
selected asset.

Uploader access is checked against the verified actor. Non-uploaders must pass
the existing media farmer/project persona scope. The route remains read-only and
has no trust-boundary findings. After this tranche, 40 unauthenticated
non-reference read findings remain and mutation findings remain at zero.

## Public app-bootstrap classification checkpoint

`GET /api/v1/app-config/bootstrap` is explicitly classified as an intentional
public read. The auditor uses an exact, GET-only path exception rather than a
broad public prefix.

Static and behavior regressions confirm the pre-login contract, active
tenant/project bounds, stable response fields, read-only behavior, tenant
defaults, and project overrides. After this classification, 39 unauthenticated
non-reference read findings remain and mutation findings remain at zero.
