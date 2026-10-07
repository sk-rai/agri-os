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

## Next integration checkpoint

The next bounded change will apply this resolver to media and field-event
mutations. It must preserve endpoint paths and response schemas, update Android
fixtures to use bearer authentication, derive audit actors from the verified
principal, and retain web-admin-only configuration boundaries.

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
