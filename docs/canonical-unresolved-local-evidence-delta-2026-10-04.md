# Canonical unresolved local-evidence delta — 2026-10-04

## Purpose

This report closes the gap between canonical-village resolution reporting and
existing NWDP rehabilitation. It compares 7,493 canonical villages with neither
PIN nor effective NWDP mapping against 162,229 NWDP source features without an
effective LGD mapping.

These are different populations. The earlier 14,773 unresolved result describes
held NWDP source/candidate rows; 7,493 describes canonical LGD villages without
either evidence layer. These counts must not be combined.

## Reused evidence

The generator reuses the corrected PIN × effective-NWDP classification,
project-village worklist queries, deterministic normalization, exact hierarchy
codes and prior candidate-review metadata. It also requires the current
identity-gap, authoritative-source and held-review evidence.

## Validated result

The read-only probe found 290 candidate pairs for 187 canonical villages:

| Queue | Villages | Decision |
| --- | ---: | --- |
| `DETERMINISTIC_SINGLE_REVIEW` | 70 | `REVIEW_REQUIRED` |
| `HIGH_CONFIDENCE_SINGLE_REVIEW` | 70 | `REVIEW_REQUIRED` |
| `AMBIGUOUS_MULTIPLE_CANDIDATES` | 47 | Manual comparison |
| `NO_LOCAL_CANDIDATE` | 7,306 | Await authoritative evidence |

A single candidate is not an approval. Every candidate remains review evidence.

## Matching rules

Evidence is ranked as exact source code with state consistency (matching state code or normalized state name); exact hierarchy
codes plus normalized name; exact normalized state/district/block/name; then
district-scoped exact normalized name. Fuzzy similarity, transliteration,
geometry proximity and cross-state matching are excluded.

## Outputs

The generator writes all 7,493 village classifications, all 290 candidate
pairs, a state summary and a JSON audit. Generated results belong in `/tmp`
and are not repository artifacts.

## Safety boundary

This report does not authorize canonical LGD changes, PIN-link changes, NWDP
candidate changes, runtime promotion, project-resolution activation or Android
delivery. It performs no database writes and grants no automatic resolution.

The 140 single-candidate rows may enter a later two-session admin review packet.
The 47 ambiguous rows require a separate comparison surface. The remaining
7,306 rows stay blocked until authoritative LGD, postal or other governed
evidence is available.

## Reproduction

    venv/bin/python backend/scripts/report_canonical_unresolved_local_evidence_delta.py \
      --output-dir /tmp/canonical-unresolved-local-evidence-delta-v1
