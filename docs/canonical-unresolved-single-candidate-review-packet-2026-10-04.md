# Canonical unresolved single-candidate review packet — 2026-10-04

## Purpose

This gate turns the validated local-evidence delta into a bounded, read-only
admin review packet. It covers only the 140 canonical villages with exactly one
local NWDP candidate. No row is approved, applied, promoted or exposed by
creating the packet.

## Exact scope

The packet preserves three evidence-strength tiers:

| Priority | Match basis | Rows | Queue |
| --- | --- | ---: | --- |
| 1 | Exact village source code plus consistent state code or normalized state name | 51 | `DETERMINISTIC_SINGLE_REVIEW` |
| 2 | Exact normalized state, district, block and village hierarchy | 19 | `DETERMINISTIC_SINGLE_REVIEW` |
| 3 | Exact normalized village name within state and district | 70 | `HIGH_CONFIDENCE_SINGLE_REVIEW` |

The packet contains 140 distinct canonical villages and 131 distinct source features across six states. Rajasthan contributes 113 rows, Uttarakhand 14, Uttar Pradesh 7, Haryana 4, Punjab 1 and Himachal Pradesh 1.

All 140 rows already have candidate-review evidence. That evidence includes
blocked-source caveats and unpromoted rows, so its existence is not approval.

A source-uniqueness check found 131 distinct source features. Six source features are each proposed for multiple canonical villages, affecting 15 rows. Those rows are marked `CONFLICT_REVIEW_REQUIRED`; the remaining 125 are `TWO_SESSION_REVIEW_ELIGIBLE`.

## Review procedure

A primary admin may record only `ACCEPT_FOR_SECOND_REVIEW`, `REJECT` or
`HOLD`. Acceptance requires a different second reviewer. The generated CSV
leaves both reviewer identities and both decisions blank; it is an input to a
later reviewed workflow, not an approval ledger.

The 15 collision rows cannot be accepted for second review until the six shared-source conflicts are disambiguated. They may only be held or rejected in this packet.

Reviewers must compare canonical and source hierarchy, names, source codes,
prior evidence and any governed external evidence. Priority controls review
order, not acceptance.

## Outputs

The generator writes:

- `single_candidate_review_packet.csv`;
- `single_candidate_review_state_summary.csv`;
- `single_candidate_review_packet.json`.

The JSON records source hashes, exact queue counts and the no-write policy.
Generated packet artifacts contain operational identifiers and must not be committed. Store them under staged local evidence or a controlled temporary
directory.

## Safety boundary

The generator does not connect to the database. It performs no canonical,
PIN-link, NWDP candidate, runtime or project-resolution write. It does not
authorize automatic application or Android exposure.

The existing two-session project-resolution workflow is not reused to mutate
global canonical geography. Any future global reconciliation workflow needs a
separate schema, immutable review history, distinct reviewers, explicit
authorization, dry-run evidence and rollback design.

## Reproduction

    venv/bin/python       backend/scripts/build_canonical_unresolved_single_candidate_review_packet.py       --evidence-dir data/staged/core_stack/promotion_review/20261004-canonical-unresolved-local-evidence-delta-v1       --output-dir /tmp/canonical-unresolved-single-candidate-review-packet-v1
