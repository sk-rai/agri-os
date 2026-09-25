# Geography coverage reconciliation — 2026-09-24

## Outcome

The local canonical LGD geography, OGD village/PIN staging, and NWDP
village-boundary source have been reconciled as different populations.
The previously compared totals are not competing counts of the same
entity set:

- `677,323` is the OGD village-to-PIN mapping-row count;
- `560,316` is the distinct OGD village/PIN-pair count;
- `560,150` is the distinct OGD village-code count;
- `654,285` is the NWDP raw village-boundary feature count;
- `576,082` is the distinct canonical village-code count;
- `576,083` is the canonical database row count because LGD village
  code `476380` is represented twice.

The canonical village-code set reconciles exactly to the union of the
available sources:

- UP LGD village master: `110,274` codes;
- OGD distinct village codes: `560,150`;
- UP/OGD overlap: `94,342`;
- exact union: `576,082`;
- canonical codes missing from the expected union: `0`;
- unexpected canonical codes: `0`.

This resolves the apparent LGD-versus-NWDP count discrepancy. It does
not establish that either source is a complete national village master;
LGD identity rows, village/PIN mappings, and NWDP boundary features have
different inclusion and duplication rules.

## Source findings

All 33 inspected `geography_lgd/*/villages.jsonl` snapshots are
byte-identical UP-only exports with SHA-256
`503932fbeec60948516cc0ba84af8335e30a3a9d01b8b2d7e2d21742c4ffe19b`.
Each contains exactly `110,274` unique UP village codes.

The original UP SpreadsheetML files independently reconcile:

- village master: `110,274` rows and unique village codes;
- village-to-Gram-Panchayat mapping: `110,274` unique village codes;
- rows without a local-body mapping: `6,441`;
- block-to-village mapping: `107,479` unique villages;
- master villages without block coverage: `2,795`;
- village statuses: `105,575` Inhabitant, `4,677` Un-Inhabitant,
  and `22` Forest.

The OGD snapshot contains `677,323` physical village/PIN mapping rows,
but only `560,316` distinct village/PIN pairs and `560,150` distinct
village codes. The difference includes `117,007` repeated mapping rows
and villages associated with multiple PIN codes. Chandigarh is absent
from the OGD source.

Canonical LGD code `476380`, Bhicholi Mardana (Og), is duplicated in the
database and has an OGD identity conflict across subdistrict codes
`3543` and `7013`. This should be corrected through a separate canonical
identity cleanup; it did not block the inactive NWDP staging work.

## NWDP raw-source coverage

The 36 pinned NWDP GeoJSON files contain `654,285` raw features, and
staging contains the same `654,285` source features. Raw-to-staging loss
is therefore zero.

Haryana is not evidence of a truncated NWDP raw file:

- NWDP source features: `7,010`;
- distinct numeric NWDP village codes: `7,008`;
- canonical LGD villages: `4,126`.

Its lower runtime count was caused by identity and hierarchy matching
constraints, not by fewer raw NWDP records. State-level comparisons must
also account for boundary features that exceed canonical village counts,
duplicate/reference features, parent drift, and sources that contain
village codes absent from the local canonical master.

## Completed inactive staging

The active runtime baseline remains unchanged at `449,899` features and
`449,899` crosswalks.

Two separately authorized cohorts are staged inactive:

1. normalized direct-village rehabilitation: `49,606` rows;
2. deterministic parent-drift rehabilitation: `11,676` rows;
3. deterministic district-drift rehabilitation: `3,723` rows.

The combined inactive runtime total is therefore `65,005` features and
`65,005` crosswalks.

The parent-drift cohort contains:

- `11,564` canonical-block mismatches;
- `112` source-subdistrict mismatches;
- `7,095` exact or punctuation-normalized names;
- `4,581` names differing only by an accepted trailing numeric suffix.

All `11,676` target villages are unique. Post-apply reconciliation found
zero active staged rows, zero candidate identity changes, zero candidate
activation or promotion changes, zero invalid native geometries, zero
project matches, and no change to active runtime totals.

Parent-drift execution pins:

- proposal checksum:
  `277bc7d767daa68111b26cc4de8157d87fc4796ebb649eac119eb7d87d815af0`;
- authorization checksum:
  `c90b3ff07c0228b0122488db433d9d69eeca957ad1bcd4c48ef2fea4575f81e6`;
- manifest checksum:
  `50fd3c9dc2d1a7251793d41927f116cc5e32612793e6cc606199d517d5cb55a0`;
- ordered national row manifest:
  `b9748e503dc0ee0412c350125039bf163b63b4f596896904b5ba23db88d2f5db`;
- final checkpoint checksum:
  `e2cfba583631a1b271a15063dcfb8933769f65a23019798fab94c989e88815e2`.

## District-drift inactive rehabilitation

The no-canonical-village audit found `3,908` NWDP village codes that are
present in canonical LGD within the same state but under a different
district. Deterministic name validation retained `3,723` rows:

- `3,581` exact or punctuation-normalized names;
- `142` names differing only by an accepted trailing numeric suffix;
- six states;
- `3,723` unique candidate, source-feature, and target-village identities;
- zero active or inactive runtime collisions.

The remaining `185` district-drift name mismatches remain held for
manual review. The authorized engine passed a read-only dry run and a
61-row Delhi transactional apply/rollback rehearsal before completing
six state transactions.

Post-apply reconciliation found `3,723` inactive runtime features,
`3,723` inactive crosswalks, six inactive promotion events, zero active
staged rows, zero duplicate targets, zero invalid native geometries,
zero candidate identity changes, and zero project matches. Active
runtime totals remained `449,899` features and crosswalks.

The final district-drift checkpoint checksum is:

`2c548a99ee7c8d3bef1f29eea9ecf76db799025d39311fe0917b13b59fc11f37`

## Remaining blocked population

After all three inactive rehabilitation cohorts, `32,271` rows remain
outside authorization:

| Reason | Rows |
| --- | ---: |
| Absent from canonical LGD globally | 22,219 |
| Normal hierarchy-matched name mismatch requiring review | 7,540 |
| Canonical block mismatch with unsafe name disposition | 2,272 |
| District drift with unsafe name disposition | 185 |
| Source subdistrict mismatch with unsafe name disposition | 32 |
| Missing canonical state — Chandigarh | 12 |
| Missing canonical district — Delhi | 11 |
| **Total** | **32,271** |

The `10,029` name-review rows remain held rather than deterministically
approved. The `22,219` globally absent village codes require a current
authoritative national LGD village master or an explicit unmatched-
boundary policy. Chandigarh requires
a canonical state and hierarchy before its 12 rows can be reconsidered.

## Readiness decision

Geography identity and source-count interpretation are now documented and
reproducible. Inactive boundary staging is complete for all currently
authorized deterministic cohorts.

Geography is not fully closed for runtime use:

- the remaining `32,271` rows are unresolved;
- all `65,005` rehabilitation rows remain inactive;
- lookup remains disabled;
- activation requires a separate checksum-pinned authorization;
- shared gateway/distributed rate limiting remains required before wider
  lookup exposure;
- canonical duplicate code `476380` remains a cleanup item;
- Chandigarh canonical hierarchy coverage remains incomplete.

No source file, canonical geography row, project match, runtime
activation state, lookup behavior, or Android behavior was changed by
the reconciliation work.

## Evidence

Primary evidence is stored under:

`data/staged/core_stack/promotion_review/20260924-geography-coverage-reconciliation-v1/`

Key implementation files:

- `backend/scripts/nwdp_parent_drift_selector.py`;
- `backend/scripts/build_nwdp_parent_drift_manifest.py`;
- `backend/scripts/run_nwdp_parent_drift_rehabilitation.py`.
