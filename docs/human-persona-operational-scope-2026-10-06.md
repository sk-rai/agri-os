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

The strict persona resolver now governs generic media attachment creation for
farmer, parcel, and field-event targets. A personal farmer can attach their
media to their own records, while an organisation agent requires an active
profile, active project role, and explicit active farmer assignment.

Possession of an authorised asset does not grant authority over another target.
The target is resolved independently, and asset/target farmer and project
identities must remain compatible.

Advisory attachments remain a web-admin publication capability. Field agents
and agronomists cannot use the advisory path merely because they have an
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
