# Authenticated human persona scope

Date: 2026-10-06

## Purpose

AgriFabric uses one authenticated `User` as the login identity while allowing
that person to hold more than one operational persona. A user can have a
personal `Farmer` profile and simultaneously act as an organisation field
agent, agronomist, dealer, manager, or enumerator through an `AgentProfile`.

Separate mobile numbers or login accounts are not required.

## Authority sources

The strict operational resolver uses the following persisted relationships:

- `Farmer.user_id` establishes authority over the user's personal farmer
  profile.
- an active `AgentProfile` establishes availability of agent mode;
- an active `ProjectRole` establishes project participation;
- an active `FarmerProjectEnrollment` containing the user in
  `assigned_user_ids` establishes authority over an assisted farmer.

A project role alone does not grant access to every farmer in that project.

Tenant, user, and device identity originate from the verified bearer principal.
Mobile-number matching and caller-supplied actor headers are not authorization
mechanisms.

## Supported persona combinations

- farmer only;
- agent or agronomist only;
- farmer and agent simultaneously;
- an agent assigned to one or more assisted farmers.

A dual-persona user can operate their personal farmer profile and separately
operate farmers explicitly assigned through active project enrollment.

## Fail-closed boundaries

The resolver excludes:

- archived or inactive farmer profiles;
- inactive agent profiles;
- inactive project roles or projects;
- assignments whose agent no longer has active access to that project;
- inactive project enrollments;
- farmers that are not explicitly assigned;
- cross-tenant projects, farmers, and assignments.

The compatibility-oriented `_actor_can_manage_farmer` helper is deliberately
not reused because it permits missing and synthetic actors for older fixtures.

## Product boundary

Organisation administration remains a web-admin capability. Project setup,
crop configuration, enrollment administration, and advisory publication remain
under admin permissions. An `AGRONOMIST` or `FIELD_AGENT` login is not treated
as a web administrator merely because an older generic permission map contains
an edit capability; operational authorization must still follow persona and
assignment scope.

Farmers and organisation agents consume operational functionality through the
Android application. Route authorization must evaluate the authenticated
person's persisted personas and assignments rather than treating the login
role as a mutually exclusive persona.

## Validation

`test_human_persona_scope_behavior.py` proves:

- farmer-only personal access;
- assigned agent access;
- dual-persona access with one identity;
- unassigned-farmer denial;
- inactive-assignment exclusion;
- inactive-agent exclusion;
- cross-tenant isolation;
- complete transaction rollback.

The existing mode-bootstrap regression remains green and continues to return
`MODE_CHOOSER` for a user with both farmer and agent capabilities.

`test_field_event_persona_behavior.py` additionally proves personal-farmer
reporting, assigned-agent reporting and review, unassigned-agent denial,
farmer review denial, verified actor history, admin-only `ADVISORY_SENT`, and
invalid backwards-transition rejection.

## Media and field-event integration

The resolver now governs media asset mutations, generic attachment creation,
and field-event creation/status mutations. Endpoint paths and response schemas
remain stable. Android-oriented fixtures use verified farmer identities for
operational capture, while organisation administration and advisory
publication remain bounded web-admin capabilities.

## Media attachment integration checkpoint

The strict persona resolver now governs generic media attachment creation and
listing for farmer, parcel, and field-event targets. A personal farmer can
attach and list media for their own records, while an organisation agent
requires an active profile, active project role, and explicit active farmer
assignment.

Possession of an authorised asset does not grant authority over another target.
The target is resolved independently, and asset/target farmer and project
identities must remain compatible.

Operational attachment reads require an exact target type and ID; broad
tenant attachment inventory remains a web-admin capability. Advisory attachment
creation and listing also remain web-admin publication capabilities. Field
agents and agronomists cannot use those paths merely because they have an
operational persona.

## Field-event persona integration checkpoint

A personal farmer may report an event for their own linked farmer profile. An
organisation agent may report for an assisted farmer only with an active agent
profile, active project role, and explicit active enrollment assignment. The
server derives `FARMER_ANDROID` or `FIELD_AGENT_ANDROID` from these persisted
relationships.

Farmers cannot perform review-state transitions. Assigned agents may perform
permitted operational transitions, but `ADVISORY_SENT` remains a web-admin
boundary because it represents publication rather than field capture.

Field-event list and detail reads use the same persona resolution. Farmer lists
contain only personal-farmer events; assigned-agent lists contain explicitly
assigned farmers; users without a readable farmer scope receive an empty list.
Inaccessible details fail closed with `404`. Explicit web administrators retain
tenant-wide operational review visibility.

## Query-thread persona integration checkpoint

The strict persona resolver now governs direct query creation, message
creation, and workflow status changes. A personal farmer may create and
continue a query for their own farmer profile. An organisation agent may
operate an assisted-farmer query only with an active profile, active project
role, and explicit active enrollment assignment.

The server derives query message sender identity from the authenticated user
and the resolved farmer or agent persona. Inline media must belong to the same
farmer and project as the thread. Farmer personas cannot perform workflow
transitions, and only explicit web administrators may change thread
assignment.

Query list and detail visibility use the same persona resolution. Farmer
lists contain only personal-farmer threads; assigned-agent lists contain
explicitly assigned farmers; users without readable farmer scope receive an
empty list. Inaccessible details fail closed with `404`, while explicit web
administrators retain tenant-wide visibility.

Sync-event authorization remains a separate checkpoint.

## Farmer and parcel mutation integration checkpoint

The strict persona resolver now governs direct farmer enrollment and update,
parcel creation and update, and parcel geometry capture. A personal farmer may
manage only their linked farmer profile and its parcels. An organisation agent
may manage an assisted farmer only through an active profile, active project
role, and explicit active enrollment assignment.

Self-enrollment verifies the authenticated user's persisted mobile identity and
links the new farmer profile to that user. Agent-assisted enrollment records the
agent as the actor without assigning the farmer profile to the agent's user
identity. Explicit web administrators retain tenant-wide administrative scope.

Geometry attribution, enrollment attribution, tenant selection, and actor
selection come from the authenticated principal. Direct behavior coverage
proves personal-farmer, assigned-agent, unassigned-agent, unrelated-farmer,
web-admin, self-enrollment, assisted-enrollment, tenant-mismatch, and verified
actor cases.

Farmer and parcel collection reads now use the same persona union. A user's
readable farmer set is the union of linked personal farmers and explicitly
assigned farmers. Parcel visibility is constrained by that same farmer set.
Operational users without either capability receive empty collections, while
explicit web administrators retain tenant-wide read scope.

## Farmer readiness and worklist persona integration checkpoint

Farmer profile-readiness summaries now apply the strict persona resolver.
Personal farmers see only their linked profile, assigned agents see only
explicitly assigned farmers with active project access, and unassigned agents
receive an empty collection. Explicit web administrators retain tenant-wide
readiness visibility.

The field-agent worklist additionally requires an active agent persona and
derives its actor from the verified principal. Its results are restricted to
the resolver's assigned farmer IDs regardless of the compatibility
`assigned_only` flag. Caller-supplied actor impersonation is rejected.

## Farmer enrollment and launch-context persona integration checkpoint

Farmer project-enrollment and Android launch-context reads now use strict
persona visibility. Personal farmers can read their own membership and launch
decision; assigned agents can read the corresponding assisted-farmer context;
unassigned and unrelated operational identities fail closed with `404`.

Explicit web administrators retain tenant-wide access. Tenant selection comes
from the authenticated principal, and joined project data is independently
tenant-bounded. Enrollment creation remains a separate mutation tranche.

## Farmer self-profile persona integration checkpoint

The Android self-profile and self-hydration reads now resolve identity from
the authenticated principal. An explicitly linked personal farmer profile
takes precedence, including when its profile mobile differs from other
candidate records.

Legacy mobile-based profile resolution remains available only through the
persisted, tenant-bounded authenticated user record. This supports older
unlinked farmer rows without treating request headers or caller-provided
mobile values as authorization evidence.

## Farmer by-mobile hydration persona checkpoint

By-mobile profile hydration now applies the same personal-farmer and
assigned-farmer visibility used by the core farmer reads. Explicit
`Farmer.user_id` linkage remains authoritative; once present, it disables the
legacy persisted-mobile fallback.

Assigned agents can hydrate only farmers in their active assignment scope,
unassigned agents cannot discover profiles by mobile, and explicit web
administrators retain tenant-wide compatibility access. The requested mobile
number never grants persona scope by itself.

## Duplicate farmer administration boundary

Duplicate-profile discovery and archival remain outside operational farmer and
agent personas. The inventory requires admin view capability, while archival
requires admin edit capability.

The server derives tenant and archive actor from the authenticated admin
principal. Possession of a personal or assigned farmer relationship does not
grant duplicate-cleanup authority because the operation can affect identity
resolution and historical profile continuity.

## Farmer project-enrollment creation authorization checkpoint

Direct project-membership attachment is an explicit web-admin capability.
The project-enrollment creation route requires verified project-edit
permission plus the established web-admin boundary. It does not grant field
agents a second path around the assisted farmer-enrollment workflow.

Tenant scope and `enrolled_by` attribution are derived from the authenticated
administrator. Farmer, project, and parcel references remain tenant-bounded,
and caller-supplied tenant or actor identity is not trusted.

## Project staffing and future freelance services

Project-agent assignment is an administrative relationship controlled by a
verified web administrator. Assignment requires an active tenant user, active
agent profile, and active role in the selected project. Assignment history
records the authenticated administrator.

This boundary does not prevent a future agricultural-services network for
independent farmers. Freelance field-agent or agronomist access will require a
separate mutual-consent engagement and revocable data grant rather than a
synthetic project assignment. That deferred model is defined in
`docs/freelance-agricultural-services-roadmap.md`.

## Farmer project-enrollment lifecycle administration

Single-enrollment lifecycle transitions are explicit web-admin operations.
Operational agents and agronomists cannot complete, cancel, archive, reactivate,
or otherwise change project membership merely because they have an operational
persona or edit-like project capability.

Tenant scope and lifecycle attribution come from the verified administrator.
This project-membership lifecycle remains separate from future freelance
specialist engagements, which will use farmer consent and revocable access
rather than project enrollment state.

## Bulk project-enrollment lifecycle administration

Bulk preview is limited to project-scoped web-admin viewers; bulk apply is
limited to explicit web administrators with project-edit permission. Tenant
scope comes from the verified principal, and the project and all affected
enrollments are tenant-bounded. Bulk audit attribution uses the authenticated
administrator.

These operations close or reopen project membership in aggregate. They do not
create freelance specialist access for independently enrolled farmers; that
future relationship remains consent-based and revocable under the separate
services roadmap.

## Soil-profile persona integration

Core soil-profile creation and update now use the persisted human persona
scope. A personal farmer can maintain soil observations for their own parcel;
an assigned project agent can maintain an assisted farmer's profile; unrelated
and unassigned identities are denied. Explicit web administrators retain
tenant-wide maintenance capability.

This access follows current farmer ownership or project assignment. It does not
grant a future freelance agronomist access: independent specialist access will
require the separate farmer-consented, revocable engagement model.

## Soil-enrichment ingestion boundary

Automated SoilGrids fetches, SHC/SLUSI captures, and direct enrichment
snapshot ingestion are trusted administrative operations. They require verified
edit-capable web-administrator identity, derive tenant and actor from that
identity, tenant-bound the target parcel, and preserve the authenticated
administrator in snapshot provenance.

Farmer and field-agent personas cannot use these ingestion routes. This
boundary is intentionally separate from the future freelance specialist model:
an independent farmer may eventually consent to a verified agronomist or field
agent providing services, but that relationship must use an explicit,
purpose-limited, time-bounded, and revocable service engagement rather than
project assignment or administrative ingestion authority.

## Crop-cycle persona integration

The crop-cycle operational loop now uses persisted human persona scope for
creation, stage transitions, activity logging, and completion. A personal
farmer can operate cycles for their linked farmer profile. An active project
agent can operate cycles only for explicitly assigned farmers with active
project access. Explicit edit-capable web administrators retain tenant-wide
operational scope.

The parcel is the authoritative farmer relationship during cycle creation.
Caller-supplied farmer identifiers must agree with the tenant-bounded parcel;
mobile-number inference and arbitrary tenant-farmer fallback are prohibited.
All lifecycle attribution is derived from the verified principal.

This authorization covers personal ownership and current project assignment
only. A future freelance agronomist or field agent must receive a separate,
farmer-consented, purpose-limited, time-bounded, and revocable service grant
before operating an independent farmer's crop cycle.

## Offline sync persona integration

Offline operational sync now follows the same persisted persona boundaries as
direct farmer, parcel, and crop-cycle operations. The bearer principal supplies
the authoritative tenant and actor. Event payloads cannot select a different
tenant or audit actor.

A farmer can sync only their linked farmer profile and related records. An
active project agent can sync explicitly assigned farmers and may enroll a new
farmer only through an accessible project. Agent-led enrollment persists the
authenticated agent assignment so subsequent offline operations remain
authorized. Edit-capable web administrators retain bounded tenant-wide
operation.

Batches remain resilient: an authorized event can commit even when another
event in the same request is denied. Persona denials use the stable
`SYNC_SCOPE_DENIED` error and do not materialize the rejected entity. Tests
cover self-enrollment, agent enrollment, personal and assigned operation,
unassigned and unrelated denial, administrator operation, mixed batches,
verified attribution, and cleanup.

Project enrollment and assignment are not substitutes for the future
freelance agricultural-services model. A freelance agronomist serving an
independent farmer will require an explicit farmer-consented service grant
with separate purpose, geography, duration, and revocation controls.

## Sync conflict-resolution administrative boundary

Conflict resolution is a tenant-governance operation rather than a farmer or
field-agent mutation. Accepting a client value, retaining the server value, or
performing a semantic merge requires a verified administrator with `EDIT`
permission. The tenant and resolver come from the persisted authenticated
identity, and resolution attribution cannot be supplied by the caller.

This boundary does not authorize project agents or future freelance
agronomists to resolve platform sync conflicts. Any future specialist service
engagement remains farmer-consented, purpose-limited, time-bounded, and
revocable, and does not inherit administrative conflict-governance authority.

## Crop-climate suitability publishing boundary

Publishing crop-climate suitability overrides is a runtime agronomic-governance
operation. It requires explicit `PUBLISH` permission and uses the verified
administrator as tenant authority and publisher. Ordinary editors,
agronomists, farmers, and field agents cannot publish these overrides through
the endpoint.

A project-scoped override must reference an active project in the authenticated
tenant. This administrative publishing authority remains separate from the
future freelance agricultural-services model: a farmer-consented specialist
engagement does not grant authority to publish tenant or project suitability
policy.

## Finance report configuration governance

Finance report configuration is an administrative governance operation, not a
farmer or field-agent operation. Edit-capable administrators may validate
configuration, while only publish-capable administrators may publish a runtime
version.

Tenant and publisher attribution derive from verified identity. Optional
project scope is tenant-bounded and active-project-bounded. Configuration may
control approved mappings, display flags, thresholds, and report layout, but it
cannot replace or execute the fixed profit-and-loss formula.

## Broadcast administration governance

Broadcast authoring and delivery administration are web-administrator
operations. Edit-capable administrators may create drafts and edit content or
audience rules. Publish-capable administrators may publish campaigns, generate
or retry deliveries, and transition campaigns to expired or cancelled states.

Tenant scope, campaign creator, campaign approver, and administrative audit
actors come from verified identity. Farmer personas retain only their separate,
farmer-scoped delivery read and acknowledgement lifecycle; they cannot author
or administer campaigns.

## Product catalog administration governance

Manufacturer, branded-product, package, and catalog-import maintenance are
tenant administrative operations requiring edit permission. Project product
approval additionally requires project-edit authority within the addressed
project.

These powers do not belong to farmer or field-agent personas. Tenant scope and
audit attribution come from verified administrator identity, and project
approval does not expand beyond persisted project membership.

## Weather administration governance

Weather provider configuration and execution are tenant administrative
operations requiring edit permission. Farmers and field agents consume
backend-normalized weather outcomes but cannot configure providers, run
adapters or workers, or create administrative snapshots.

Tenant scope and operational attribution come from verified administrator
identity. Worker and adapter execution remain backend-controlled and do not
grant direct external-provider access to Android clients.

## Identity administration governance

Identity administrators may create and update agent profiles and assign or revoke tenant-scoped project access only when their persisted role grants `MANAGE_USERS`.

Agent persona metadata and project membership never expand authority beyond the authenticated tenant. Cross-tenant users, profiles, and projects are not valid mutation targets. Administrative audit events identify both the verified administrator and the affected user.

## Runtime app configuration governance

Runtime app configuration is an administrative control-plane operation, not a
farmer or field-agent persona capability. Tenant defaults require an
enterprise administrator with `MANAGE_USERS`. Project overrides require
`PROJECT_EDIT` within the selected project scope.

Project runtime safety remains unchanged: projects with enrolled or operational
data may update display-level branding, while behavior-changing configuration
sections remain locked.

## Company-discovery CSV governance

Company-discovery CSV validation and import are administrative data-curation
operations. They are not farmer, field-agent, or self-service persona
capabilities.

An edit-capable administrator may validate external company evidence and import
it into the authenticated tenant's review queue. Imported rows remain
`PENDING_REVIEW`; import authorization does not grant automatic approval,
tenant activation, or company-profile publication.

## Project geography import-preview governance

Project geography import preview is an administrative planning capability. It
is not available to farmer or field-agent personas, and tenant-level roles must
also hold effective project-scoped `PROJECT_EDIT` access unless enterprise
administration applies.

Previewing village LGD codes does not apply scope, activate boundary
candidates, promote mappings, enable runtime lookup, or change Android
behavior. A separate authorized apply operation remains required.

## Workflow project override governance

Project workflow overrides are administrative configuration changes. A verified
administrator must have `PROJECT_EDIT` permission and access to the target
project. Tenant identity and audit attribution come from the authenticated
principal.

The shared default workflow catalog may be selected, but project overrides are
always stored in the verified tenant and project scope. Deletion is implemented
as recoverable archival, with immutable before/after audit evidence.

## Geography review governance

National geography review queues are operated by platform administrators, not
tenant or project personas. NWDP boundary review, demographic-profile review,
CoRE/LGD mapping review, and both village evidence review sessions require the
verified `default` platform tenant. The second village evidence review still
requires an enterprise administrator with `PUBLISH` and a reviewer different
from the primary reviewer.

Project matching remains tenant/project administration. Its disabled contract
requires project-scoped `PROJECT_EDIT`, but performs no database mutation and
does not authorize later activation or promotion.

## Soil enrichment operations governance

Soil-enrichment operational mutations are administrator-controlled backend operations. They are not farmer-persona or Android mutation capabilities.

The verified administrator determines the tenant and actor. Farmer, parcel, and project references must belong to that tenant and must be mutually consistent. Audit metadata records the verified administrator, while dry-run execution remains non-mutating. Provider execution policy remains separately governed and live external execution is not enabled by this authorization tranche.

## Platform provisioning and non-mutating POST governance

Tenant creation is outside ordinary tenant administration. Only a verified `ENTERPRISE_ADMIN` in the `default` platform tenant may provision another tenant, and every successful provisioning action produces immutable administrator attribution.

Device login is an authentication exchange, not an authenticated business mutation. Master-data sync, project-village-resolution dry run, and workflow-draft CSV validation use POST request bodies but are non-mutating operations. The two administrative validation routes report the verified administrator and derive all scope from the authenticated principal.

## Broadcast read governance

Broadcast administrative visibility belongs to verified tenant administrators
with `VIEW`. Farmer feed visibility belongs only to the linked farmer persona or
an active assigned project user. Possession of a farmer UUID, delivery UUID, or
tenant header does not grant visibility, and authenticated users cannot cross
tenant boundaries through broadcast read routes.

## Weather snapshot read governance

Weather snapshots are tenant-wide operational data exposed to verified
administrators with `VIEW`. The authenticated administrator determines the
tenant boundary and actor attribution for list and latest-snapshot reads.

These endpoints are read-only. Their filtering and response behavior remain
unchanged, while unauthenticated and cross-tenant access is denied.

## Sync conflict read governance

The Android pending-conflict feed is a personal operational surface rather than
a tenant-wide administration surface. A verified human may see only pending,
redacted conflict summaries attributed to that caller's `user_id` and tenant.

Tenant-wide conflict queues, full client/server payloads, and operational sync
health remain administrator-only reads requiring `VIEW`. Conflict resolution
remains a separate `EDIT` operation.

## Media asset detail governance

A media asset is visible to its verified uploader or to a caller authorized for
its farmer/project scope. Farmer owners may read personal assets, actively
assigned agents may read assisted-farmer assets, and authorized web
administrators may read tenant assets.

Unrelated farmers, unassigned agents, cross-tenant callers, and unauthenticated
callers cannot retrieve asset details.

## Pre-login app-bootstrap governance

Runtime bootstrap configuration is persona-neutral and available before login
so clients can render tenant/project branding, localization, enabled features,
and form contracts. It does not represent a farmer, agent, or administrator
operational persona.

Optional project resolution remains tenant-bounded and active-only. The route
performs no database writes and exposes only its stable client bootstrap
response.

## Crop reference-data governance

Crop categories, canonical crops, varieties, and lifecycle templates are
global reference material rather than human-persona operational records.
Their master-data GET endpoints therefore do not require a verified human
persona or tenant actor.

This boundary does not grant unauthenticated access to crop-cycle activity,
farmer crop data, project configuration, or catalog administration. Any route
that leaves the canonical read-only reference scope must enforce the
appropriate authenticated persona and tenant boundary.

## Geography reference-data governance

Canonical administrative hierarchy and postal lookup data is global reference
material rather than human-persona operational data. The hierarchy profile
and seven active geography lookup routes therefore remain usable without an
authenticated human persona.

This boundary is limited to the exact read-only GET routes. Project geography,
farmer location records, import operations, review decisions, promotion
state, and runtime-boundary administration remain outside the reference-data
exception.

## Workflow catalog read governance

Workflow runtime reads use the verified human persona rather than treating tenant and actor headers as authority.

Tenant catalog reads are available to authenticated tenant members. When a project is requested, access is limited to enterprise administrators, verified project roles, or the farmer identity associated with an active enrollment in that project. An unrelated farmer receives the stable `WORKFLOW_PROJECT_SCOPE_DENIED` response, and a foreign-tenant project is not disclosed.

Workflow draft and history views remain administrative surfaces governed by administrator permissions. Read-only governance views require `VIEW`; draft validation requires `EDIT` because validation persists an audit event attributed to the verified administrator.

Published and archived workflow rendering behavior, project enablements, version pinning, publish safeguards, legacy pin backfill, and CSV draft validation remain covered by authenticated regression callers.

## Crop-cycle read governance

Crop-cycle read visibility follows the persisted human-persona scope:

- a farmer can read personal cycles, eligible parcels, recommendations, activities, and finance summaries;
- an assigned agent can read cycles for farmers in the agent's persisted operational assignment;
- an unrelated farmer or unassigned agent is denied;
- a tenant administrator with `VIEW` can read tenant operational cycles and tenant-wide finance analytics;
- project finance configuration is available only through a verified project role or active farmer enrollment.

Selected cycles are always tenant-bounded before persona authorization. Activity-stage lookups are tenant-bounded as well. Identity headers may corroborate a token but cannot introduce a different tenant or actor.
