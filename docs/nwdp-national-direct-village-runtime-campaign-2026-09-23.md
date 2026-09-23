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

## Normalized direct-village rehabilitation proposal

A subsequent read-only audit found that the blocked source-caveat
population used zero-padded NWDP hierarchy and village codes. Numeric
normalization recovered 57,146 structurally consistent direct matches
across eight states. A conservative deterministic name audit retained
49,606 rows:

- 34,099 exact or punctuation-normalized name matches;
- 15,507 matches differing only by a trailing parenthesized numeric or
  slash-delimited cadastral suffix;
- 7,540 remaining name mismatches reserved for manual review.

The 49,606-row proposal covers Delhi, Haryana, Himachal Pradesh, Jammu &
Kashmir, Ladakh, Punjab, Rajasthan, and Uttarakhand. Every row is pinned
to its candidate, source feature, import batch, canonical hierarchy,
source index, source geometry hash, reconstructed runtime geometry hash,
and source-file checksum.

Three invalid source geometries have previously authorized
`SHAPELY_MAKE_VALID` repairs. They are pinned individually by source
feature ID, source index, repaired geometry hash, repair proposal,
authorization, and row checksum. All three reconstruct as valid
polygons with relative area change below the authorized threshold.

The read-only manifest reconciled:

- row count: 49,606;
- state count: 8;
- existing candidate-crosswalk collisions: 0;
- existing runtime source-feature collisions: 0;
- database writes attempted: false;
- ordered national row manifest:
  `da132eb9cbf0446638d1ef060c866fc9313e02c5a934842b06f4929cb44101f5`;
- manifest checksum:
  `bf7aad382b660d5af1d91ac62d618ce1828b84e74ed4cc6abdb0d789c2ee51cc`;
- manifest file SHA-256:
  `050562fd5bd15928c567cbce5913ea370011bdd4615a010f9d4652357fc87984`.

The proposal was subsequently authorized for exactly these 49,606 rows.
The 7,540 name mismatches and all other blocked/manual-review rows remain
outside the authorization.

## Normalized direct-village inactive staging

The authorized rehabilitation engine was committed as `23cefe2` with
script SHA-256:

`72ab211e1860ee765b12269a2864405db70a9c40f3aebc21a448f5b1aca53b4f`

Authorization was pinned to:

- proposal checksum:
  `11bc682d32ea23c72403cbe374bc615e38fb6e1652a271e10692455dc8110691`;
- authorization checksum:
  `825fa696b79d24d28d86fa68e66c300b0a7c6bd0c6622af236fa422dddb117cb`;
- ordered national row manifest:
  `da132eb9cbf0446638d1ef060c866fc9313e02c5a934842b06f4929cb44101f5`;
- manifest checksum:
  `bf7aad382b660d5af1d91ac62d618ce1828b84e74ed4cc6abdb0d789c2ee51cc`.

A read-only dry run reconciled all 49,606 rows across eight states.
A rollback-only rehearsal staged all 33 Delhi rows inside a transaction,
verified inactive native geometry and exact counts, exercised the
proposal-scoped rollback path, restored 33 candidate and source rows,
deleted 33 runtime features and crosswalks plus one promotion event, and
left database state unchanged.

The guarded apply then completed eight bounded single-writer
transactions:

- 49,606 candidate review-metadata updates;
- 49,606 authorized runtime-eligibility updates;
- 49,606 inactive runtime features;
- 49,606 inactive village crosswalks;
- 8 inactive promotion events.

Post-apply reconciliation found zero active staged rows, zero candidate
activation or promotion changes, zero candidate identity changes, zero
invalid native geometries, zero duplicate villages, and zero project
matches. Existing active runtime features and crosswalks remained
unchanged at 449,899 each. The final checkpoint is complete at 49,606
rows and 8 states with checksum:

`adbc0685e9a22a91fb326c59c9d49b1f422da54fe401f330ed5d519bb621dab5`

This milestone is inactive staging only. It does not authorize or perform
runtime activation, runtime-set identity changes, lookup exposure,
project matching, source geometry/file changes, or Android changes.
The remaining 47,670 rows from the original 97,276-row blocked
population remain outside this staged cohort.
