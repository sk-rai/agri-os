# Project-local village single-admin authorization — 2026-10-04

## Decision

A policy allowing one authenticated project administrator may authorize a village overlay for a
project that the administrator is permitted to edit. A second administrator is
not required because this operation does not change global canonical geography.

The existing two-session workflows remain available for evidence governance and
for any future global canonical mutation. They are not required for a
PROJECT_LOCAL_ADDITION.

## Why this boundary is appropriate

Village names and administrative parents experience administrative drift:
boundaries, labels, tehsil/block assignments, and operational project scope can
change at different times in different source systems. A company administrator
is the accountable authority for its own project scope.

The system permits a project-local addition when at least one parent matches
the project's canonical geography: state, district, or
tehsil/subdistrict/block. The complete match vector is stored in immutable
audit evidence. A state-only match is allowed under this explicitly authorized
policy, but remains visible as weaker evidence for later review.

## Authorization contract

The generic local-additions endpoint requires:

- project-scoped PROJECT_EDIT permission;
- a tenant-owned active project;
- an unmapped NWDP source without an active runtime mapping;
- at least one matching parent;
- the exact phrase AUTHORIZE PROJECT LOCAL VILLAGE;
- an administrator reason and rollback token;
- valid active postal evidence for every supplied PIN.

The operation writes one active PROJECT_LOCAL_ADDITION and one immutable APPLIED
event. A duplicate active overlay for the same tenant, project, and NWDP source
is rejected.

## Visibility and immutability

An active overlay is visible in the project's resolution list. It does not:

- insert or update global canonical villages;
- insert or update global village/PIN links;
- create an NWDP canonical candidate or runtime crosswalk;
- affect another tenant or project;
- alter global point lookup;
- claim Android visibility.

Project-scoped Android delivery remains a separate reader integration. Until
that reader is implemented and tested, responses explicitly report
android_visible=false.

## Retirement

The same organization's authorized project administrator can retire an active
overlay using the generic local-addition retirement route. Retirement requires
the original rollback token, an audit reason, and the exact phrase
RETIRE PROJECT LOCAL VILLAGE. It marks only the project overlay RETIRED and
appends a ROLLED_BACK event.

## Global governance boundary

This authorization does not weaken the global canonical change boundary.
Canonical LGD enrichment and any future global canonical mutation remain
separately gated and may retain two-session approval.

## Validation

- backend/scripts/test_project_local_village_single_admin_static.py
- backend/scripts/test_project_local_village_single_admin.py

The behavior regression proves single-admin authorization, parent evidence,
duplicate prevention, retirement, immutable audit history, cleanup, and
unchanged canonical, PIN, runtime, project-match, and Android state.
