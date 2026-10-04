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

## Project-aware village reader

The reusable `GET
/api/v1/master-data/geography/project-village-resolutions/projects/{project_id}/available-villages`
reader returns the project's canonical LGD villages together with its active
project-local additions. Its response schema is
`project_available_villages.v1`, its declared scope is
`TENANT_PROJECT_ONLY`, and it supports bounded search and pagination.

Each item has an explicit identity type:

- `CANONICAL_LGD` supplies `submission.village_id` and a null manual name;
- `PROJECT_LOCAL` supplies `submission.village_name_manual`, a null global
  village ID, and `project_village_resolution_id` for provenance.

Retired or inactive overlays disappear from this reader immediately. They are
never copied into the global LGD village catalog or global village/PIN links.

## Android integration boundary

Android changes are required for mobile users to consume this reader. The
Android source code is not present in this repository, so this commit cannot
implement or validate that client work. The Android project should:

1. call the project-aware reader only after a project is selected;
2. render both identity types while visually distinguishing project-local rows;
3. submit a canonical `village_id` for `CANONICAL_LGD` and the supplied
   `village_name_manual` for `PROJECT_LOCAL`;
4. retain `project_village_resolution_id` as provenance where its local model
   permits it;
5. refresh the project catalog so retired overlays disappear; and
6. never insert `PROJECT_LOCAL` rows into its global LGD cache.

Until that separate Android integration is implemented and tested, mutation
responses continue to report `android_visible=false`.

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
duplicate prevention, retirement, immutable audit history, cleanup,
project-catalog visibility before retirement, removal after retirement, and
unchanged canonical, PIN, runtime, project-match, and Android state.
