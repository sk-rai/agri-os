# NWDP National Direct-Village Runtime Campaign

Status date: 2026-09-23

## Completed milestone

The checksum-pinned national V2 campaign staged and activated 449,789
reviewed direct-village runtime features and crosswalks across 30 state/UT
source batches.

The existing 110 active pilot rows were preserved, producing 449,899 active
runtime features and 449,899 active village crosswalks in runtime set:

`e5f93e27-a0bd-5c8b-bef3-d97986e14c55`

The campaign preserved these guardrails:

- runtime lookup remained disabled;
- candidates remained inactive and unpromoted;
- campaign promotion events remained inactive;
- project matches remained zero;
- source files and source geometry were not changed;
- Android behavior was not changed;
- runtime-set identity was not changed.

## Pinned campaign identities

- source proposal:
  `4040493550d62f4f2b4c380b404e80ffb8530c5c391f0497d022f2b638e2327e`
- source authorization:
  `647bf08d951feae9adc27244c73cfa9693d6afaf7cbf48a01324eede4edd9ed0`
- national source manifest:
  `3fc6bbd0162abe635339df96c5b704dec734d8f7824c44933468ede5ecaeefc3`
- completed source checkpoint:
  `a026f553c3157c5e32da425d2412c68d7fee32fb906734947f1a09bbfe68ad45`
- activation proposal:
  `09397c171a408f3ac12acb0c0a429f0f81d6a6841b3616f1f760e12b94f7c3d3`
- activation authorization:
  `e446de344a08dddd7cf46bc4a52aee8e06c6d49937187214d62ec0d35e1e35a7`
- completed activation checkpoint:
  `3842cae8dc461043e72dddeb84e9b74475bf82456e1aa5a24170c55d6b1edbe1`

## Verification evidence

Post-activation reconciliation proved:

- 449,789 V2 runtime features active;
- 449,789 V2 runtime crosswalks active;
- 110 earlier active features and crosswalks preserved;
- zero invalid native geometries;
- zero invalid crosswalks;
- zero duplicate active village groups;
- zero project matches;
- zero active campaign promotion events;
- active partial GiST index
  `idx_boundary_runtime_features_geom_active` present and used.

A representative correctness audit covered 145 points across all 30 campaign
states. Every point matched exactly one expected feature, no sampled ambiguity
was observed, and an outside point returned no match.

Endpoint-shaped database probes returned:

- 30 of 30 probes matched once;
- median latency: 2.456 ms;
- p95 latency: 4.176 ms;
- maximum latency: 6.379 ms;
- representative `EXPLAIN ANALYZE` execution time: 0.341 ms.

These measurements are local database evidence, not a production service-level
objective.

## Source inventory and active coverage

The NWDP source inventory contains:

- 654,285 source features;
- 36 state/UT import batches.

The active runtime layer contains:

- 449,789 national V2 rows;
- 110 preserved pilot rows;
- 449,899 total active runtime rows.

The inactive source population includes:

- 3,147 direct-code candidates not approved for promotion;
- 98,705 manual-review rows;
- 97,276 `BLOCKED_SOURCE_CAVEAT` rows;
- 5,258 `SPECIAL_REFERENCE_FEATURE` rows.

The national V2 campaign is therefore a high-confidence runtime subset, not
complete NWDP source coverage.

## Six omitted state/UT batches

The six omitted source jurisdictions are:

- Chandigarh;
- Delhi;
- Himachal Pradesh;
- Ladakh;
- Punjab;
- Uttarakhand.

A fail-closed state-parent audit examined their 202 apparent
`DIRECT_VLCODE_MATCH` candidates.

All 202 resolve to canonical villages in the wrong state:

| Source state/UT | Rows | Incorrect canonical state |
| --- | ---: | --- |
| Chandigarh | 1 | Meghalaya |
| Delhi | 19 | Meghalaya |
| Himachal Pradesh | 37 | Bihar |
| Himachal Pradesh | 6 | Meghalaya |
| Ladakh | 2 | Bihar |
| Punjab | 79 | Bihar |
| Punjab | 3 | Meghalaya |
| Uttarakhand | 52 | Bihar |
| Uttarakhand | 3 | Meghalaya |
| **Total** | **202** | — |

These rows are global village-code collisions, not valid state-scoped direct
matches. None is safe for promotion.

Do not create a six-state runtime campaign from these rows.

## Special reference features

`SPECIAL_REFERENCE_FEATURE` represents source geometry that is not an
administrative village.

Examples include:

- rivers;
- reservoirs;
- lakes;
- canals;
- forest beats;
- plantations;
- sentinel values such as `vlcode=999999`;
- blank or nonstandard village/block code patterns;
- other non-village reference polygons.

These shapes may be retained as reviewed map/reference context, but they must
not:

- resolve a farmer or parcel to a village;
- become a village runtime crosswalk;
- drive parcel village-boundary lookup;
- be automatically promoted;
- overwrite canonical LGD geography.

## Blocked source-caveat result

The 97,276 `BLOCKED_SOURCE_CAVEAT` rows are validated reference geometries,
but none currently resolves to a canonical village by source village code.

Observed result:

- source village codes present: 97,276;
- canonical village-code matches: 0;
- blanket rehabilitation candidates: 0.

Geometry validity alone is insufficient for rehabilitation. These rows require
canonical geography completion and a new state- and parent-scoped crosswalk.

## Manual-review policy

The 98,705 manual-review rows remain inactive.

They are reserved for explicit project-scoped admin review and assignment by
organizations using the application.

Project assignment must:

- require authorized admin action;
- preserve reviewer identity, reason, evidence, and audit history;
- remain scoped to the selected project;
- not activate a national runtime candidate;
- not change national point-lookup behavior;
- not change Android behavior as an implicit side effect.

## Next safe path

The next national-coverage step is canonical geography completion for affected
jurisdictions, followed by a state- and parent-scoped crosswalk rebuild.

Only candidates that become unique, state-consistent, parent-consistent,
geometry-valid, and separately authorized may enter a future runtime proposal.

Runtime lookup remains disabled.

Shared/distributed rate limiting and a separate lookup-enablement authorization
remain mandatory before customer, Android, public, multi-worker, or national
lookup exposure.

## Campaign engines

The completed campaign engines are:

- `backend/scripts/run_national_direct_village_runtime_state.py`
- `backend/scripts/run_national_direct_village_runtime_activation.py`

Both retain:

- dry-run mode;
- checksum-pinned authorization;
- single-writer locking;
- atomic checkpoints;
- resume validation;
- bounded transactions;
- exact reconciliation;
- rollback-only rehearsal;
- proposal-scoped rollback.
