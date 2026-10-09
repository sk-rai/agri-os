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
